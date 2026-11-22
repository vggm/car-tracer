package dev.lnk.cartrace.service

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class SupervisorTest {
    @Before fun reset() = Status.reset()

    @Test
    fun supervisorRestartsCrashedChild() = runTest {
        var runs = 0
        val job = Supervisor(this).launch("child") {
            runs++
            if (runs < 3) throw IllegalStateException("boom")
            kotlinx.coroutines.awaitCancellation()
        }
        runCurrent()
        assertEquals(1, runs)
        advanceTimeBy(4_999); runCurrent()
        assertEquals(1, runs)
        advanceTimeBy(1); runCurrent()
        assertEquals(2, runs)
        advanceTimeBy(5_000); runCurrent()
        assertEquals(3, runs)
        job.cancel()
    }

    @Test
    fun crashCallsOnCrash() = runTest {
        var runs = 0
        val crashes = mutableListOf<Pair<String, Throwable>>()
        val job = Supervisor(this, onCrash = { n, e -> crashes += n to e }).launch("child") {
            runs++
            if (runs == 1) throw IllegalStateException("boom")
            kotlinx.coroutines.awaitCancellation()
        }
        runCurrent()
        assertEquals(1, crashes.size)
        assertEquals("child", crashes[0].first)
        assertEquals("boom", crashes[0].second.message)
        job.cancel()
    }

    @Test
    fun throwingOnCrashDoesNotKillSupervisor() = runTest {
        var runs = 0
        val job = Supervisor(this, onCrash = { _, _ -> error("diag broke") }).launch("child") {
            runs++
            if (runs == 1) throw IllegalStateException("boom")
            kotlinx.coroutines.awaitCancellation()
        }
        runCurrent()
        advanceTimeBy(5_000); runCurrent()
        assertEquals(2, runs)
        job.cancel()
    }

    @Test
    fun supervisorDoesNotRestartOnCancel() = runTest {
        var runs = 0
        val job = Supervisor(this).launch("child") {
            runs++
            throw CancellationException("cancelled")
        }
        runCurrent()
        advanceTimeBy(20_000); runCurrent()
        assertEquals(1, runs)
        assertTrue(job.isCancelled)
        assertTrue(Status.errors.value.isEmpty())
    }

    @Test
    fun supervisorRecordsError() = runTest {
        var runs = 0
        val job = Supervisor(this).launch("gps") {
            runs++
            if (runs == 1) throw IllegalStateException("boom")
            kotlinx.coroutines.awaitCancellation()
        }
        runCurrent()
        assertEquals(1, Status.errors.value.size)
        assertTrue(Status.errors.value[0].contains("gps"))
        assertTrue(Status.errors.value[0].contains("boom"))
        job.cancel()
    }

    @Test
    fun errorsKeepOnlyLast20() {
        repeat(25) { Status.addError("e$it") }
        assertEquals(20, Status.errors.value.size)
        assertEquals("e5", Status.errors.value.first())
        assertEquals("e24", Status.errors.value.last())
    }
}
