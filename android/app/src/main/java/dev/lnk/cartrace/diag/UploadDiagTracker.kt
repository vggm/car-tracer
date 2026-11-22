package dev.lnk.cartrace.diag

import dev.lnk.cartrace.upload.UploadOutcome
import java.util.concurrent.atomic.AtomicInteger

/** Pure state machine turning upload outcomes into diag reports and a per-heartbeat failure count. */
class UploadDiagTracker {
    private var failStreak = 0
    private val sinceBeat = AtomicInteger(0)

    /** Returns the (code, text) to report for [o], or null. Call from the upload loop only. */
    fun onOutcome(o: UploadOutcome): Pair<String, String>? = when (o) {
        is UploadOutcome.Sent -> {
            val n = failStreak
            failStreak = 0
            if (n > 0) "upload.recovered" to "recuperado tras $n fallos" else null
        }
        is UploadOutcome.Retry -> {
            sinceBeat.incrementAndGet()
            if (++failStreak == 1) "upload.failing" to o.reason else null
        }
        UploadOutcome.Unauthorized -> {
            sinceBeat.incrementAndGet()
            failStreak++
            "upload.unauthorized" to "server answered 401"
        }
        UploadOutcome.TooLarge -> {
            sinceBeat.incrementAndGet()
            failStreak++
            "upload.too_large" to "server answered 413"
        }
        is UploadOutcome.Discarded -> "upload.discarded" to "server answered ${o.status}" + (o.reason?.let { ": $it" } ?: "")
        UploadOutcome.Idle -> null
    }

    /** Failures since the previous call (the heartbeat's `upload_failures`). */
    fun takeFailures(): Int = sinceBeat.getAndSet(0)
}
