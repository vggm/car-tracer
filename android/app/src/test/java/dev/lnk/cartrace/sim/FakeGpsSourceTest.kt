package dev.lnk.cartrace.sim

import dev.lnk.cartrace.gps.GpsFix
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.cos
import kotlin.math.hypot

@OptIn(ExperimentalCoroutinesApi::class)
class FakeGpsSourceTest {
    // ~11 km straight line north
    private val route = (0..100).map { LatLon(40.47 + it * 0.001, -3.77) }

    private fun meters(a: GpsFix, b: GpsFix): Double {
        val dy = (b.lat - a.lat) * 111_320.0
        val dx = (b.lon - a.lon) * 111_320.0 * cos(Math.toRadians(a.lat))
        return hypot(dx, dy)
    }

    @Test
    fun fakeGpsMovesAlongRoute() = runTest {
        val fixes = mutableListOf<GpsFix>()
        val src = FakeGpsSource(route, this, nowMs = { 1_000_000L + currentTime })
        src.start { fixes += it }
        advanceTimeBy(9_100)
        src.stop()
        assertEquals(4, fixes.size)
        assertEquals(3_000L, fixes[1].utcMs - fixes[0].utcMs)
        // 50 km/h for 3 s = 41.7 m
        assertEquals(41.7, meters(fixes[0], fixes[1]), 3.0)
        assertEquals(125.0, meters(fixes[0], fixes[3]), 6.0)
        assertTrue(fixes.all { it.speedMps!! in 13.8..13.9 })
    }

    @Test
    fun parsesRouteJson() {
        val pts = FakeGpsSource.parseRoute("""{"points":[[39.1,-6.2],[39.2,-6.3]]}""")
        assertEquals(listOf(LatLon(39.1, -6.2), LatLon(39.2, -6.3)), pts)
    }
}
