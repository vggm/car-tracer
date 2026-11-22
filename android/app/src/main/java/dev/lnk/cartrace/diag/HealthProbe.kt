package dev.lnk.cartrace.diag

import android.Manifest
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.location.LocationManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Environment
import android.os.StatFs
import android.os.SystemClock

/**
 * Reads the Android-dependent parts of [HealthInputs]. Never throws: every reading is
 * wrapped and yields null when it cannot be read.
 */
class HealthProbe(private val context: Context) {

    fun read(): HealthInputs {
        val battery = safe {
            context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        }
        return HealthInputs(
            gpsEnabled = safe {
                val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
                lm.isLocationEnabled
            },
            gpsPermission = safe {
                context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) ==
                    PackageManager.PERMISSION_GRANTED
            },
            btEnabled = safe {
                val bm = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
                bm.adapter?.isEnabled
            },
            net = safe { networkCode() },
            batteryPct = safe {
                val level = battery?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
                val scale = battery?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
                if (level >= 0 && scale > 0) level * 100 / scale else null
            },
            charging = safe {
                val status = battery?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
                if (status < 0) null
                else status == BatteryManager.BATTERY_STATUS_CHARGING ||
                    status == BatteryManager.BATTERY_STATUS_FULL
            },
            storageFreeMb = safe {
                StatFs(Environment.getDataDirectory().path).availableBytes / (1024 * 1024)
            },
            uptimeS = safe { SystemClock.elapsedRealtime() / 1000 },
        )
    }

    /** 0 no network, 1 wifi, 2 mobile, 3 other. */
    private fun networkCode(): Int {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return 0
        return when {
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> 1
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> 2
            else -> 3
        }
    }

    private inline fun <T> safe(block: () -> T?): T? =
        try {
            block()
        } catch (_: Exception) {
            null
        }
}
