package dev.lnk.cartrace.diag

import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

// Mirrors MAX_DIAG_DETAIL (contract/Records.kt, added by Task 3).
private const val MAX_DETAIL = 500

private val MAC_RE = Regex("([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")
private val TOKEN_RE = Regex("token=\\S+", RegexOption.IGNORE_CASE)
private val BEARER_RE = Regex("Bearer\\s+\\S+", RegexOption.IGNORE_CASE)

fun sanitize(text: String): String = text
    .replace(MAC_RE, "<mac>")
    .replace(TOKEN_RE, "token=<redacted>")
    .replace(BEARER_RE, "Bearer <redacted>")

class Diagnostics(
    private val nowMs: () -> Long,
    private val emit: suspend (code: String, text: String) -> Unit,
    private val windowMs: Long = 600_000,
) {
    private class Entry(var lastEmitMs: Long, var suppressed: Int)

    private val mutex = Mutex()
    private val entries = HashMap<String, Entry>()

    suspend fun report(code: String, text: String) {
        val out = mutex.withLock {
            val now = nowMs()
            val e = entries[code]
            if (e == null) {
                entries[code] = Entry(now, 0)
                format(code, 0, text)
            } else if (now - e.lastEmitMs < windowMs) {
                e.suppressed++
                null
            } else {
                val n = e.suppressed
                e.lastEmitMs = now
                e.suppressed = 0
                format(code, n, text)
            }
        }
        if (out != null) emit(code, out)
    }

    private fun format(code: String, n: Int, text: String): String =
        "$code${if (n > 0) " x$n" else ""} ${sanitize(text)}".take(MAX_DETAIL)
}

suspend fun Diagnostics.flushPending(store: PendingDiagStore) {
    for ((code, text) in store.drain()) report(code, text)
}
