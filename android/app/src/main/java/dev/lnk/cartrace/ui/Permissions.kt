package dev.lnk.cartrace.ui

import android.Manifest
import dev.lnk.cartrace.upload.UploadOutcome
import java.net.URI
import java.net.URISyntaxException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

enum class OnboardingStep { FINE_LOCATION, BACKGROUND_LOCATION, BLUETOOTH_CONNECT, POST_NOTIFICATIONS, BATTERY, AUTOSTART_INFO }

object Permissions {
    const val FINE_LOCATION = Manifest.permission.ACCESS_FINE_LOCATION
    const val BACKGROUND_LOCATION = Manifest.permission.ACCESS_BACKGROUND_LOCATION
    const val BLUETOOTH_CONNECT = Manifest.permission.BLUETOOTH_CONNECT
    const val POST_NOTIFICATIONS = Manifest.permission.POST_NOTIFICATIONS

    /** Pseudo-permission: the user acknowledged the autostart hint. */
    const val AUTOSTART_SEEN = "car-trace.AUTOSTART_SEEN"

    /** First pending onboarding step, or null when everything is done. [granted] holds granted permissions + AUTOSTART_SEEN. */
    fun nextStep(
        granted: Set<String>,
        batteryExempt: Boolean,
        skipped: Set<OnboardingStep> = emptySet(),
    ): OnboardingStep? = when {
        FINE_LOCATION !in granted -> OnboardingStep.FINE_LOCATION
        BACKGROUND_LOCATION !in granted -> OnboardingStep.BACKGROUND_LOCATION
        BLUETOOTH_CONNECT !in granted -> OnboardingStep.BLUETOOTH_CONNECT
        POST_NOTIFICATIONS !in granted && OnboardingStep.POST_NOTIFICATIONS !in skipped -> OnboardingStep.POST_NOTIFICATIONS
        !batteryExempt && OnboardingStep.BATTERY !in skipped -> OnboardingStep.BATTERY
        AUTOSTART_SEEN !in granted && OnboardingStep.AUTOSTART_INFO !in skipped -> OnboardingStep.AUTOSTART_INFO
        else -> null
    }

    /** Steps the user may skip (optional for the service to run). */
    val SKIPPABLE = setOf(OnboardingStep.POST_NOTIFICATIONS, OnboardingStep.BATTERY, OnboardingStep.AUTOSTART_INFO)

    /** Runtime permission requested by a step, or null for non-permission steps. */
    fun permissionFor(step: OnboardingStep): String? = when (step) {
        OnboardingStep.FINE_LOCATION -> FINE_LOCATION
        OnboardingStep.BACKGROUND_LOCATION -> BACKGROUND_LOCATION
        OnboardingStep.BLUETOOTH_CONNECT -> BLUETOOTH_CONNECT
        OnboardingStep.POST_NOTIFICATIONS -> POST_NOTIFICATIONS
        else -> null
    }

    /** The service needs FINE + BACKGROUND location, and Bluetooth unless simulated. */
    fun canStartService(granted: Set<String>, simulated: Boolean): Boolean =
        FINE_LOCATION in granted && BACKGROUND_LOCATION in granted && (simulated || BLUETOOTH_CONNECT in granted)
}

object Formatters {
    fun outcome(o: UploadOutcome): String = when (o) {
        is UploadOutcome.Sent -> "Enviado · ${o.accepted}/${o.duplicates}/${o.rejected}"
        is UploadOutcome.Discarded -> "Descartado"
        UploadOutcome.Unauthorized -> "Token incorrecto"
        UploadOutcome.TooLarge -> "Reintentando: lote demasiado grande"
        is UploadOutcome.Retry -> "Reintentando: ${o.reason}"
        UploadOutcome.Idle -> "Sin datos"
    }

    /** Error-log line for outcomes that lose data (never contains the token); null otherwise. */
    fun uploadError(o: UploadOutcome): String? = when (o) {
        is UploadOutcome.Sent ->
            if (o.rejected > 0) "Servidor rechazó ${o.rejected} registros" + (o.firstError?.let { ": $it" } ?: "") else null
        is UploadOutcome.Discarded ->
            "Lote descartado (HTTP ${o.status})" + (o.reason?.let { ": $it" } ?: "")
        else -> null
    }

    fun isValidUrl(raw: String): Boolean {
        val u = raw.trim()
        if (u.isEmpty() || u.any { it.isWhitespace() }) return false
        return try {
            val uri = URI(u)
            (uri.scheme == "http" || uri.scheme == "https") && !uri.host.isNullOrEmpty()
        } catch (e: URISyntaxException) {
            false
        }
    }

    fun time(ms: Long): String = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date(ms))
}
