package dev.lnk.cartrace.diag

import dev.lnk.cartrace.contract.MAX_DIAG_DETAIL
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

private val MAC_RE = Regex("(?<![0-9A-Za-z])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Za-z])")
private val MAC_BARE_RE = Regex("(?<![0-9A-Za-z])[0-9A-Fa-f]{12}(?![0-9A-Za-z])")
private val AUTH_RE = Regex("Authorization:\\s*\\S+(?:\\s+\\S+)?", RegexOption.IGNORE_CASE)
private val BEARER_RE = Regex("Bearer\\s+\\S+", RegexOption.IGNORE_CASE)
private val TOKEN_RE = Regex("(?:access_|refresh_|id_)?token\\W+\\S+", RegexOption.IGNORE_CASE)
private val KEY_RE = Regex("(?<![0-9A-Za-z])(?:api_?)?key=[^&\\s]+", RegexOption.IGNORE_CASE)
private val PATH_RE = Regex("(?<![0-9A-Za-z:/.])/(?:data|storage|sdcard|mnt|home|Users)/\\S*")

fun sanitize(text: String): String = text
    .replace(AUTH_RE, "Authorization: <redacted>")
    .replace(BEARER_RE, "Bearer <redacted>")
    .replace(TOKEN_RE, "token=<redacted>")
    .replace(KEY_RE, "key=<redacted>")
    .replace(MAC_RE, "<mac>")
    .replace(MAC_BARE_RE, "<mac>")
    .replace(PATH_RE, "<path>")

class Diagnostics(
    private val nowMs: () -> Long,
    private val emit: suspend (code: String, text: String) -> Unit,
    private val windowMs: Long = 600_000,
) {
    private class Entry(var lastEmitMs: Long, var suppressed: Int)

    private val mutex = Mutex()
    private val entries = HashMap<String, Entry>()

    suspend fun report(code: String, text: String) {
        var restore: (() -> Unit)? = null
        val out = mutex.withLock {
            val now = nowMs()
            val e = entries[code]
            if (e == null) {
                entries[code] = Entry(now, 0)
                restore = { entries.remove(code) }
                format(code, 0, text)
            } else if (now - e.lastEmitMs < windowMs) {
                e.suppressed++
                null
            } else {
                val n = e.suppressed
                val last = e.lastEmitMs
                e.lastEmitMs = now
                e.suppressed = 0
                restore = { e.lastEmitMs = last; e.suppressed += n }
                format(code, n, text)
            }
        }
        if (out != null) {
            try {
                emit(code, out)
            } catch (t: Throwable) {
                mutex.withLock { restore?.invoke() }
                throw t
            }
        }
    }

    private fun format(code: String, n: Int, text: String): String =
        "$code${if (n > 0) " x$n" else ""} ${sanitize(text)}".take(MAX_DIAG_DETAIL)
}

suspend fun Diagnostics.flushPending(store: PendingDiagStore) {
    for ((code, text) in store.drain()) report(code, text)
}
