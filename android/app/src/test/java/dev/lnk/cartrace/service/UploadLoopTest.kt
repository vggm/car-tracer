package dev.lnk.cartrace.service

import dev.lnk.cartrace.upload.UploadOutcome
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

class UploadLoopTest {
    private val sent = UploadOutcome.Sent(1, 0, 0)

    /** Runs the loop over scripted outcomes; returns the recorded waits. */
    private fun waitsFor(outcomes: List<UploadOutcome>, remaining: Int = 0 /* number of 'more rows' answers */): List<Long> {
        val waits = mutableListOf<Long>()
        val seen = mutableListOf<UploadOutcome>()
        val it = outcomes.iterator()
        var rem = remaining
        val loop = UploadLoop(
            uploadOnce = { if (it.hasNext()) it.next() else throw CancellationException("end") },
            remaining = { if (rem-- > 0) 1 else 0 },
            onOutcome = { o -> seen += o },
            wait = { waits += it },
        )
        runTest { try { loop.run() } catch (_: CancellationException) {} }
        assertEquals(outcomes, seen)
        return waits
    }

    @Test fun idleAndDiscardedWaitThirtySeconds() {
        assertEquals(listOf(30_000L, 30_000L), waitsFor(listOf(UploadOutcome.Idle, UploadOutcome.Discarded(400))))
    }

    @Test fun sentWithMoreRowsContinuesImmediately() {
        assertEquals(listOf(30_000L), waitsFor(listOf(sent, sent), remaining = 1))
    }

    @Test fun failuresBackOffAndResetOnSent() {
        val r = UploadOutcome.Retry("x")
        val waits = waitsFor(listOf(r, UploadOutcome.Unauthorized, r, sent, r))
        assertEquals(listOf(30_000L, 60_000L, 120_000L, 30_000L, 30_000L), waits)
    }
}
