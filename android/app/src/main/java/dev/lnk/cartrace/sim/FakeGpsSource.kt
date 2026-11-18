package dev.lnk.cartrace.sim

import android.content.Context
import dev.lnk.cartrace.gps.GpsFix
import dev.lnk.cartrace.gps.GpsSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot

data class LatLon(val lat: Double, val lon: Double)

/** Walks a polyline at [speedKmh], going back and forth, emitting a fix every 3 s. */
class FakeGpsSource(
    private val route: List<LatLon>,
    private val scope: CoroutineScope,
    private val speedKmh: Double = 50.0,
    private val nowMs: () -> Long = System::currentTimeMillis,
) : GpsSource {
    private var job: Job? = null
    private val segLen = DoubleArray((route.size - 1).coerceAtLeast(0)) { dist(route[it], route[it + 1]) }
    private val total = segLen.sum()

    override fun start(onFix: (GpsFix) -> Unit) {
        stop()
        if (route.size < 2 || total <= 0.0) return
        val t0 = nowMs()
        job = scope.launch {
            while (isActive) {
                val now = nowMs()
                onFix(fixAt(travelled = (now - t0) / 1000.0 * speedKmh / 3.6, utcMs = now))
                delay(PERIOD_MS)
            }
        }
    }

    override fun stop() {
        job?.cancel()
        job = null
    }

    private fun fixAt(travelled: Double, utcMs: Long): GpsFix {
        val cycle = travelled % (2 * total)
        val forward = cycle <= total
        var d = if (forward) cycle else 2 * total - cycle
        var i = 0
        while (i < segLen.lastIndex && d > segLen[i]) { d -= segLen[i]; i++ }
        val f = (d / segLen[i]).coerceIn(0.0, 1.0)
        val a = route[i]
        val b = route[i + 1]
        val dy = b.lat - a.lat
        val dx = (b.lon - a.lon) * cos(Math.toRadians(a.lat))
        var bearing = Math.toDegrees(atan2(dx, dy))
        if (!forward) bearing += 180.0
        return GpsFix(
            utcMs = utcMs,
            lat = a.lat + (b.lat - a.lat) * f,
            lon = a.lon + (b.lon - a.lon) * f,
            accM = 5.0,
            speedMps = speedKmh / 3.6,
            bearing = (bearing + 360.0) % 360.0,
            altM = 400.0,
            simulated = true,
        )
    }

    companion object {
        private const val PERIOD_MS = 3000L
        const val ASSET = "sim/route.json"

        private fun dist(a: LatLon, b: LatLon): Double {
            val dy = (b.lat - a.lat) * 111_320.0
            val dx = (b.lon - a.lon) * 111_320.0 * cos(Math.toRadians(a.lat))
            return hypot(dx, dy)
        }

        /** Parses `{"points": [[lat, lon], ...]}`. */
        fun parseRoute(json: String): List<LatLon> =
            Json.parseToJsonElement(json).jsonObject["points"]!!.jsonArray.map {
                val p = it.jsonArray
                LatLon(p[0].jsonPrimitive.double, p[1].jsonPrimitive.double)
            }

        fun fromAssets(context: Context, scope: CoroutineScope): FakeGpsSource {
            val text = context.assets.open(ASSET).bufferedReader().use { it.readText() }
            return FakeGpsSource(parseRoute(text), scope)
        }
    }
}
