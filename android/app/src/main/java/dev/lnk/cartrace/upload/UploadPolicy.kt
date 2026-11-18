package dev.lnk.cartrace.upload

enum class UploadOutcomeKind { SENT, DISCARD, UNAUTHORIZED, TOO_LARGE, RETRY }

sealed interface UploadOutcome {
    data class Sent(val accepted: Int, val duplicates: Int, val rejected: Int) : UploadOutcome
    data class Discarded(val status: Int) : UploadOutcome
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
        408, 429, in 500..599 -> UploadOutcomeKind.RETRY
        else -> UploadOutcomeKind.DISCARD
    }

    fun nextDelayMs(failures: Int): Long {
        val n = failures.coerceIn(0, 16)
        return minOf(BASE_MS shl n, MAX_MS)
    }
}
