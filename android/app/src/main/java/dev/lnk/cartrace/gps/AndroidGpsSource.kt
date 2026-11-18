package dev.lnk.cartrace.gps

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Looper
import android.util.Log

/** GPS_PROVIDER every 3 s. Needs ACCESS_FINE_LOCATION; without it no fixes are produced. */
@SuppressLint("MissingPermission")
class AndroidGpsSource(context: Context) : GpsSource {
    private val manager = context.applicationContext.getSystemService(LocationManager::class.java)
    private var listener: LocationListener? = null

    override fun start(onFix: (GpsFix) -> Unit) {
        stop()
        val l = LocationListener { loc -> onFix(loc.toFix()) }
        try {
            manager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 3000L, 0f, l, Looper.getMainLooper())
            listener = l
        } catch (e: SecurityException) {
            Log.w(TAG, "ACCESS_FINE_LOCATION not granted, no GPS fixes", e)
        } catch (e: IllegalArgumentException) {
            Log.w(TAG, "GPS provider unavailable", e)
        }
    }

    override fun stop() {
        listener?.let { manager.removeUpdates(it) }
        listener = null
    }

    private fun Location.toFix() = GpsFix(
        utcMs = time,
        lat = latitude,
        lon = longitude,
        accM = if (hasAccuracy()) accuracy.toDouble() else 0.0,
        speedMps = if (hasSpeed()) speed.toDouble() else null,
        bearing = if (hasBearing()) bearing.toDouble() else null,
        altM = if (hasAltitude()) altitude else null,
    )

    private companion object { const val TAG = "AndroidGpsSource" }
}
