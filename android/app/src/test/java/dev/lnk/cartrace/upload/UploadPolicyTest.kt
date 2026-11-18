package dev.lnk.cartrace.upload

import org.junit.Assert.assertEquals
import org.junit.Test

class UploadPolicyTest {
    @Test fun backoffSequence() {
        assertEquals(listOf(30, 60, 120, 240, 480, 600, 600).map { it * 1000L }, (0..6).map { UploadPolicy.nextDelayMs(it) })
        assertEquals(600_000L, UploadPolicy.nextDelayMs(1000))
    }

    @Test fun classify() {
        assertEquals(UploadOutcomeKind.SENT, UploadPolicy.classify(200))
        assertEquals(UploadOutcomeKind.SENT, UploadPolicy.classify(299))
        assertEquals(UploadOutcomeKind.DISCARD, UploadPolicy.classify(400))
        assertEquals(UploadOutcomeKind.UNAUTHORIZED, UploadPolicy.classify(401))
        assertEquals(UploadOutcomeKind.TOO_LARGE, UploadPolicy.classify(413))
        for (c in listOf(408, 429, 500, 503, 599)) assertEquals(UploadOutcomeKind.RETRY, UploadPolicy.classify(c))
        for (c in listOf(404, 403, 301, 422)) assertEquals(UploadOutcomeKind.DISCARD, UploadPolicy.classify(c))
    }
}
