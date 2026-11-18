package dev.lnk.cartrace.core

import org.junit.Assert.assertEquals
import org.junit.Test

class SessionClockTest {
    private val min = 1_700_000_000_000L

    @Test fun gpsOffsetWins() {
        val c = SessionClock(min)
        c.onGpsFix(1, 1_800_000_000_000L, 1_000L)
        val r = c.resolve(Stamp(1, 5_000L, min + 1), c.offsets(), 1)
        assertEquals(Resolution.Ts(1_800_000_004_000L), r)
    }

    @Test fun wallUsedWhenPlausible() {
        val c = SessionClock(min)
        val r = c.resolve(Stamp(1, 5_000L, min + 10), emptyMap(), 1)
        assertEquals(Resolution.Ts(min + 10), r)
    }

    @Test fun waitsInCurrentBootWithoutTime() {
        val c = SessionClock(min)
        assertEquals(Resolution.Wait, c.resolve(Stamp(2, 5_000L, 1_000L), emptyMap(), 2))
    }

    @Test fun dropsPreviousBootWithoutTime() {
        val c = SessionClock(min)
        assertEquals(Resolution.Drop, c.resolve(Stamp(1, 5_000L, 1_000L), emptyMap(), 2))
    }

    @Test fun firstOffsetKept() {
        val c = SessionClock(min)
        c.onGpsFix(1, 1_800_000_000_000L, 1_000L)
        c.onGpsFix(1, 1_800_000_999_000L, 2_000L)
        assertEquals(mapOf(1 to 1_799_999_999_000L), c.offsets())
    }

    @Test fun implausibleGpsTimeIgnored() {
        val c = SessionClock(min)
        assertEquals(false, c.onGpsFix(1, min - 1, 1_000L))
        assertEquals(emptyMap<Int, Long>(), c.offsets())
        // a later good fix is still accepted (the bad one did not pin the boot)
        assertEquals(true, c.onGpsFix(1, 1_800_000_000_000L, 1_000L))
        assertEquals(mapOf(1 to 1_799_999_999_000L), c.offsets())
    }

    @Test fun onGpsFixReportsOnlyTheFirstAcceptedOffset() {
        val c = SessionClock(min)
        assertEquals(true, c.onGpsFix(1, 1_800_000_000_000L, 1_000L))
        assertEquals(false, c.onGpsFix(1, 1_800_000_999_000L, 2_000L))
    }
}
