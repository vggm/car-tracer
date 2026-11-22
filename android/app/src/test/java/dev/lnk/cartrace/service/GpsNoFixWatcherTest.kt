package dev.lnk.cartrace.service

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class GpsNoFixWatcherTest {
    private var now = 0L
    private val w = GpsNoFixWatcher({ now })

    @Test
    fun firesOncePerStreakAfterThreshold() {
        now = 120_000
        assertFalse(w.tick())
        now = 120_001
        assertTrue(w.tick())
        now = 500_000
        assertFalse(w.tick())
    }

    @Test
    fun rearmsAfterFix() {
        now = 130_000
        assertTrue(w.tick())
        now = 140_000
        w.onFix()
        assertFalse(w.tick())
        now = 140_000 + 120_001
        assertTrue(w.tick())
    }

    @Test
    fun fixKeepsItQuiet() {
        for (t in 0..600_000L step 10_000) {
            now = t
            w.onFix()
            assertFalse(w.tick())
        }
    }

    @Test
    fun fixAgeIsNullWithoutFixThenSeconds() {
        assertNull(w.fixAgeS())
        now = 5_000
        w.onFix()
        now = 12_500
        assertEquals(7L, w.fixAgeS())
    }

    @Test
    fun resumeAfterSleepDoesNotFireAndRearms() {
        now = 10_000
        w.onFix()
        now = 10_000 + 3_600_000 // slept an hour
        w.onResume()
        assertFalse(w.tick())
        assertEquals(3600L, w.fixAgeS())
        now += 120_001
        assertTrue(w.tick())
    }
}
