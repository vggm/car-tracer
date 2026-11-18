package dev.lnk.cartrace.service

import dev.lnk.cartrace.upload.UploadOutcome
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test

class StatusRecordTest {
    @Before fun reset() = Status.reset()

    @Test fun discardedIsRecordedInErrors() {
        Status.recordUpload(1_000L, UploadOutcome.Discarded(400, "bad json"))
        assertEquals(1_000L to UploadOutcome.Discarded(400, "bad json"), Status.lastUpload.value)
        assertEquals(listOf("Lote descartado (HTTP 400): bad json"), Status.errors.value)
    }

    @Test fun sentWithRejectedIsRecordedInErrors() {
        Status.recordUpload(1_000L, UploadOutcome.Sent(4, 0, 2, "ts out of range"))
        assertEquals(listOf("Servidor rechazó 2 registros: ts out of range"), Status.errors.value)
    }

    @Test fun cleanSentAndRetriesAddNoErrors() {
        Status.recordUpload(1L, UploadOutcome.Sent(4, 1, 0))
        Status.recordUpload(2L, UploadOutcome.Retry("http 500"))
        Status.recordUpload(3L, UploadOutcome.Idle)
        assertEquals(emptyList<String>(), Status.errors.value)
    }
}
