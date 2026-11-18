package dev.lnk.cartrace.upload

enum class UploadOutcomeKind { SENT, DISCARD, UNAUTHORIZED, TOO_LARGE, RETRY }

sealed interface UploadOutcome {
    data class Sent(
        val accepted: Int,
        val duplicates: Int,
        val rejected: Int,
        /** Server error text of the first rejected record, if any. */
        val firstError: String? = null,
    ) : UploadOutcome
    data class Discarded(val status: Int, val reason: String? = null) : UploadOutcome
    data object Unauthorized : UploadOutcome
    data object TooLarge : UploadOutcome
    data class Retry(val reason: String) : UploadOutcome
    data object Idle : UploadOutcome
}

object UploadPolicy {
    private const val BASE_MS = 30_000L
    private const val MAX_MS = 600_000L

    fun classify(code: Int): UploadOutcomeKind = when (code) {
        in 200..299 -> UploadOutcomeKind.SENT
        400 -> UploadOutcomeKind.DISCARD
        401 -> UploadOutcomeKind.UNAUTHORIZED
        413 -> UploadOutcomeKind.TOO_LARGE
        else -> UploadOutcomeKind.RETRY
    }

    fun nextDelayMs(failures: Int): Long {
        val n = failures.coerceIn(0, 16)
        return minOf(BASE_MS shl n, MAX_MS)
    }
}
