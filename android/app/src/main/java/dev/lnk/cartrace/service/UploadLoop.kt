package dev.lnk.cartrace.service

import dev.lnk.cartrace.upload.UploadOutcome
import dev.lnk.cartrace.upload.UploadPolicy
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.selects.select

/** The single uploader loop: pacing and backoff policy around one upload attempt. */
class UploadLoop(
    private val uploadOnce: suspend () -> UploadOutcome,
    private val remaining: suspend () -> Int,
    private val onOutcome: (UploadOutcome) -> Unit,
    private val wait: suspend (Long) -> Unit = { delay(it) },
) {
    private val resets = Channel<Unit>(Channel.CONFLATED)

    /** Forget the backoff and try again now (e.g. the server URL or token changed). */
    fun resetBackoff() {
        resets.trySend(Unit)
    }

    suspend fun run() {
        var failures = 0
        resets.tryReceive()
        while (true) {
            val outcome = try {
                uploadOnce()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                UploadOutcome.Retry("${e.javaClass.simpleName}: ${e.message ?: ""}".trim())
            }
            onOutcome(outcome)
            val reset = when (outcome) {
                is UploadOutcome.Sent -> {
                    failures = 0
                    if (remaining() > 0) continue
                    pause(IDLE_MS)
                }
                is UploadOutcome.Discarded, UploadOutcome.Idle -> pause(IDLE_MS)
                is UploadOutcome.Retry, UploadOutcome.Unauthorized, UploadOutcome.TooLarge -> {
                    val r = pause(UploadPolicy.nextDelayMs(failures))
                    failures++
                    r
                }
            }
            if (reset) failures = 0
        }
    }

    /** Waits [ms]; returns true if cut short by [resetBackoff]. */
    private suspend fun pause(ms: Long): Boolean = coroutineScope {
        val r = async { resets.receive(); true }
        val w = async { wait(ms); false }
        val res = select<Boolean> {
            r.onAwait { it }
            w.onAwait { it }
        }
        r.cancel()
        w.cancel()
        res
    }

    companion object { const val IDLE_MS = 30_000L }
}
