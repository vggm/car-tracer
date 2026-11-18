package dev.lnk.cartrace.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SleepDetectorTest {
    @Test fun sleepDetectedWhenElapsedJumps() {
        val clk = FakeClocks()
        val d = SleepDetector(clk)
        assertFalse(d.tick())
        clk.elapsed += 120_000; clk.uptime += 5_000
        assertTrue(d.tick())
    }

    @Test fun noSleepOnNormalTick() {
        val clk = FakeClocks()
        val d = SleepDetector(clk)
        d.tick()
        clk.elapsed += 5_000; clk.uptime += 5_000
        assertFalse(d.tick())
    }

    @Test fun seqIsMonotonic() {
        val s = Session()
        assertEquals(listOf(0L, 1L, 2L), List(3) { s.nextSeq() })
    }
}
