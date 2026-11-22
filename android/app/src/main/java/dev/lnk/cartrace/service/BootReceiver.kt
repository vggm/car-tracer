package dev.lnk.cartrace.service

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log
import dev.lnk.cartrace.diag.PendingDiagStore
import dev.lnk.cartrace.diag.PrefsPendingDiagStore

/** Starts the telemetry service after boot or app update, if the needed permissions are granted. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action !in ACTIONS) return
        val pending = PrefsPendingDiagStore(context)
        try {
            start(context, pending)
        } catch (e: Exception) {
            Log.w(TAG, "boot start failed", e)
            pending.add("boot.not_started", "${e.javaClass.simpleName}: ${e.message ?: ""}".trim())
        }
    }

    private fun start(context: Context, pending: PendingDiagStore) {
        val simulated = AppGraph.get(context).settings.simulated
        val required = buildList {
            add(Manifest.permission.ACCESS_FINE_LOCATION)
            add(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
            if (!simulated) add(Manifest.permission.BLUETOOTH_CONNECT)
        }
        val missing = required.filter {
            context.checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            Log.w(TAG, "not starting service, missing permissions: $missing")
            pending.add("boot.not_started", "missing permissions: ${missing.joinToString { it.substringAfterLast('.') }}")
            return
        }
        try {
            context.startForegroundService(Intent(context, TelemetryService::class.java))
        } catch (e: Exception) {
            Log.w(TAG, "could not start service", e)
            pending.add("boot.not_started", "startForegroundService: ${e.javaClass.simpleName}: ${e.message ?: ""}".trim())
        }
    }

    private companion object {
        const val TAG = "CarTrace"
        val ACTIONS = setOf(
            Intent.ACTION_BOOT_COMPLETED,
            "android.intent.action.QUICKBOOT_POWERON",
            "com.htc.intent.action.QUICKBOOT_POWERON",
            Intent.ACTION_MY_PACKAGE_REPLACED,
        )
    }
}
