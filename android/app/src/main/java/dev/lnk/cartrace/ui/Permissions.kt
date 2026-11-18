package dev.lnk.cartrace.ui

import android.Manifest
import dev.lnk.cartrace.upload.UploadOutcome
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
    fun nextStep(granted: Set<String>, batteryExempt: Boolean): OnboardingStep? = when {
        FINE_LOCATION !in granted -> OnboardingStep.FINE_LOCATION
        BACKGROUND_LOCATION !in granted -> OnboardingStep.BACKGROUND_LOCATION
        BLUETOOTH_CONNECT !in granted -> OnboardingStep.BLUETOOTH_CONNECT
        POST_NOTIFICATIONS !in granted -> OnboardingStep.POST_NOTIFICATIONS
        !batteryExempt -> OnboardingStep.BATTERY
        AUTOSTART_SEEN !in granted -> OnboardingStep.AUTOSTART_INFO
        else -> null
    }
}

object Formatters {
    fun outcome(o: UploadOutcome): String = when (o) {
        is UploadOutcome.Sent -> "Enviado"
        is UploadOutcome.Discarded -> "Descartado"
        UploadOutcome.Unauthorized -> "Token incorrecto"
        UploadOutcome.TooLarge -> "Reintentando: lote demasiado grande"
        is UploadOutcome.Retry -> "Reintentando: ${o.reason}"
        UploadOutcome.Idle -> "Sin datos"
    }

    fun isValidUrl(raw: String): Boolean {
        val u = raw.trim()
        return (u.startsWith("https://") && u.length > 8) || (u.startsWith("http://") && u.length > 7)
    }

    fun time(ms: Long): String = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date(ms))
}
