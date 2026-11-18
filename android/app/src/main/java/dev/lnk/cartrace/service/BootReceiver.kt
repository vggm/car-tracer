package dev.lnk.cartrace.service

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log

/** Starts the telemetry service after boot or app update, if the needed permissions are granted. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action !in ACTIONS) return
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
            return
        }
        try {
            context.startForegroundService(Intent(context, TelemetryService::class.java))
        } catch (e: Exception) {
            Log.w(TAG, "could not start service", e)
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
