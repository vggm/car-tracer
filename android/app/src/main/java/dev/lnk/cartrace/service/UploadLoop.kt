package dev.lnk.cartrace.service

import dev.lnk.cartrace.upload.UploadOutcome
import dev.lnk.cartrace.upload.UploadPolicy
import kotlinx.coroutines.delay

/** The single uploader loop: pacing and backoff policy around one upload attempt. */
class UploadLoop(
    private val uploadOnce: suspend () -> UploadOutcome,
    private val remaining: suspend () -> Int,
    private val onOutcome: (UploadOutcome) -> Unit,
    private val wait: suspend (Long) -> Unit = { delay(it) },
) {
    suspend fun run() {
        var failures = 0
        while (true) {
            val outcome = uploadOnce()
            onOutcome(outcome)
            when (outcome) {
                is UploadOutcome.Sent -> {
                    failures = 0
                    if (remaining() > 0) continue
                    wait(IDLE_MS)
                }
                is UploadOutcome.Discarded, UploadOutcome.Idle -> wait(IDLE_MS)
                is UploadOutcome.Retry, UploadOutcome.Unauthorized, UploadOutcome.TooLarge -> {
                    wait(UploadPolicy.nextDelayMs(failures))
                    failures++
                }
            }
        }
    }

    companion object { const val IDLE_MS = 30_000L }
}
