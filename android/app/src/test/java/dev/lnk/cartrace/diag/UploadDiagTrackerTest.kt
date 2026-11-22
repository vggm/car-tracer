package dev.lnk.cartrace.diag

import dev.lnk.cartrace.upload.UploadOutcome
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class UploadDiagTrackerTest {
    private val t = UploadDiagTracker()
    private val sent = UploadOutcome.Sent(1, 0, 0)

    @Test
    fun onlyFirstRetryOfStreakReportsFailing() {
        assertEquals("upload.failing" to "boom", t.onOutcome(UploadOutcome.Retry("boom")))
        assertNull(t.onOutcome(UploadOutcome.Retry("boom")))
    }

    @Test
    fun sentAfterFailuresReportsRecoveredOnce() {
        t.onOutcome(UploadOutcome.Retry("a"))
        t.onOutcome(UploadOutcome.Retry("a"))
        assertEquals("upload.recovered" to "recuperado tras 2 fallos", t.onOutcome(sent))
        assertNull(t.onOutcome(sent))
        assertEquals("upload.failing", t.onOutcome(UploadOutcome.Retry("b"))!!.first)
    }

    @Test
    fun unauthorizedAndTooLargeHaveOwnCodesAndCountAsFailures() {
        assertEquals("upload.unauthorized", t.onOutcome(UploadOutcome.Unauthorized)!!.first)
        assertEquals("upload.too_large", t.onOutcome(UploadOutcome.TooLarge)!!.first)
        assertEquals(2, t.takeFailures())
        assertEquals(0, t.takeFailures())
        assertEquals("upload.recovered", t.onOutcome(sent)!!.first)
    }

    @Test
    fun idleIsSilent() {
        assertNull(t.onOutcome(UploadOutcome.Idle))
        assertEquals(0, t.takeFailures())
    }

    @Test
    fun discardedReportsReasonWithoutCountingAsFailure() {
        val r = t.onOutcome(UploadOutcome.Discarded(400, "bad record"))!!
        assertEquals("upload.discarded", r.first)
        assertTrue(r.second.contains("400") && r.second.contains("bad record"))
        assertEquals("upload.discarded", t.onOutcome(UploadOutcome.Discarded(422))!!.first)
        assertEquals(0, t.takeFailures())
    }
}
