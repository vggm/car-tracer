package dev.lnk.cartrace.service

import dev.lnk.cartrace.upload.UploadOutcome
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

@kotlinx.coroutines.ExperimentalCoroutinesApi
class UploadLoopTest {
    private val sent = UploadOutcome.Sent(1, 0, 0)

    /** Runs the loop over scripted outcomes; returns the recorded waits. */
    private fun waitsFor(
        outcomes: List<UploadOutcome>,
        remaining: Int = 0, /* number of 'more rows' answers */
        idleMs: () -> Long = { UploadLoop.IDLE_MS },
    ): List<Long> {
        val waits = mutableListOf<Long>()
        val seen = mutableListOf<UploadOutcome>()
        val it = outcomes.iterator()
        var rem = remaining
        val loop = UploadLoop(
            uploadOnce = { if (it.hasNext()) it.next() else throw CancellationException("end") },
            remaining = { if (rem-- > 0) 1 else 0 },
            onOutcome = { o -> seen += o },
            wait = { waits += it },
            idleMs = idleMs,
        )
        runTest { try { loop.run() } catch (_: CancellationException) {} }
        assertEquals(outcomes, seen)
        return waits
    }

    @Test fun idleAndDiscardedWaitThirtySeconds() {
        assertEquals(listOf(30_000L, 30_000L), waitsFor(listOf(UploadOutcome.Idle, UploadOutcome.Discarded(400))))
    }

    @Test fun idlePauseUsesIdleMsAtThatMoment() {
        val answers = ArrayDeque(listOf(10_000L, 30_000L, 10_000L))
        val waits = waitsFor(listOf(sent, UploadOutcome.Idle, UploadOutcome.Discarded(400)), idleMs = { answers.removeFirst() })
        assertEquals(listOf(10_000L, 30_000L, 10_000L), waits)
    }

    @Test fun sentWithMoreRowsDoesNotAskIdleMs() {
        var asked = 0
        val waits = waitsFor(listOf(sent, sent), remaining = 1, idleMs = { asked++; 10_000L })
        assertEquals(listOf(10_000L), waits)
        assertEquals(1, asked)
    }

    @Test fun backoffIgnoresIdleMs() {
        val r = UploadOutcome.Retry("x")
        assertEquals(listOf(30_000L, 60_000L), waitsFor(listOf(r, r), idleMs = { 10_000L }))
    }

    @Test fun sentWithMoreRowsContinuesImmediately() {
        assertEquals(listOf(30_000L), waitsFor(listOf(sent, sent), remaining = 1))
    }

    @Test fun failuresBackOffAndResetOnSent() {
        val r = UploadOutcome.Retry("x")
        val waits = waitsFor(listOf(r, UploadOutcome.Unauthorized, r, sent, r))
        assertEquals(listOf(30_000L, 60_000L, 120_000L, 30_000L, 30_000L), waits)
    }

    @Test fun resetBackoffRestartsFromBaseDelay() = runTest {
        val waits = mutableListOf<Long>()
        var calls = 0
        val loop = UploadLoop(
            uploadOnce = { calls++; UploadOutcome.Retry("x") },
            remaining = { 0 },
            onOutcome = {},
            wait = { waits += it; awaitCancellation() },
        )
        val job = backgroundScope.launch { loop.run() }
        runCurrent()
        assertEquals(listOf(30_000L), waits)
        loop.resetBackoff(); runCurrent()
        assertEquals(2, calls)
        assertEquals(listOf(30_000L, 30_000L), waits)
        job.cancel()
    }

    @Test fun uploadExceptionIsRetryWithBackoff() {
        val waits = mutableListOf<Long>()
        val seen = mutableListOf<UploadOutcome>()
        var n = 0
        val loop = UploadLoop(
            uploadOnce = { if (n++ < 2) throw java.io.IOException("disk") else throw CancellationException("end") },
            remaining = { 0 },
            onOutcome = { seen += it },
            wait = { waits += it },
        )
        runTest { try { loop.run() } catch (_: CancellationException) {} }
        assertEquals(listOf(30_000L, 60_000L), waits)
        assertEquals(2, seen.size)
        assertEquals(true, seen.all { it is UploadOutcome.Retry })
    }
}
