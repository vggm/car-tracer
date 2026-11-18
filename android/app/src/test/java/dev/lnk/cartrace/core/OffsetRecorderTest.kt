package dev.lnk.cartrace.core

import dev.lnk.cartrace.queue.BootOffset
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Test

class OffsetRecorderTest {
    private val min = 1_700_000_000_000L
    private val good = 1_800_000_000_000L
    private val saved = mutableListOf<BootOffset>()
    private val clock = SessionClock(min)
    private val rec = OffsetRecorder(clock) { saved.add(it) }

    @Test fun realFixIsRecordedAndPersisted() = runBlocking {
        rec.onFix(boot = 3, utcMs = good, elapsedMs = 1_000L, simulated = false)
        assertEquals(mapOf(3 to good - 1_000L), clock.offsets())
        assertEquals(listOf(BootOffset(3, good - 1_000L)), saved)
    }

    @Test fun simulatedFixNeverRecordsAnOffset() = runBlocking {
        rec.onFix(boot = 3, utcMs = good, elapsedMs = 1_000L, simulated = true)
        assertEquals(emptyMap<Int, Long>(), clock.offsets())
        assertEquals(emptyList<BootOffset>(), saved)
    }

    @Test fun simulatedThenRealStillRecordsRealOffset() = runBlocking {
        rec.onFix(3, good, 1_000L, simulated = true)
        rec.onFix(3, good + 50_000L, 2_000L, simulated = false)
        assertEquals(mapOf(3 to good + 48_000L), clock.offsets())
    }

    @Test fun implausibleTimeNotPersisted() = runBlocking {
        rec.onFix(3, min - 1, 1_000L, simulated = false)
        assertEquals(emptyList<BootOffset>(), saved)
        assertEquals(emptyMap<Int, Long>(), clock.offsets())
    }

    @Test fun onlyFirstOffsetPerBootPersisted() = runBlocking {
        rec.onFix(3, good, 1_000L, false)
        rec.onFix(3, good + 5_000L, 2_000L, false)
        assertEquals(1, saved.size)
    }

    @Test fun unknownBootCountKeptInMemoryOnly() = runBlocking {
        rec.onFix(0, good, 1_000L, false)
        assertEquals(mapOf(0 to good - 1_000L), clock.offsets())
        assertEquals(emptyList<BootOffset>(), saved)
    }

    @Test fun persistedOffsetsWithUnknownBootAreIgnored() {
        val db = listOf(BootOffset(0, 5L), BootOffset(-1, 6L), BootOffset(4, 7L))
        assertEquals(mapOf(4 to 7L), OffsetRecorder.usablePersisted(db))
    }
}
