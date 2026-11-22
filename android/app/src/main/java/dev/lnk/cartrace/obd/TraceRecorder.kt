package dev.lnk.cartrace.obd

import kotlinx.coroutines.CancellationException

/** Decorator that records every raw ELM327 exchange of one connection attempt for diagnostics. */
class TraceRecorder(private val inner: ElmTransport, private val nowMs: () -> Long) : ElmTransport {
    private val lines = ArrayList<String>()
    private var header = ""
    private var startMs = nowMs()

    /** Resets the recorded lines and starts the attempt clock. */
    fun begin(header: String) {
        synchronized(lines) {
            this.header = header
            lines.clear()
            startMs = nowMs()
        }
    }

    /** Appends a free-form line, e.g. `glued=1`. */
    fun note(text: String) {
        synchronized(lines) { lines.add("+${nowMs() - startMs} # ${escapeRaw(text)}") }
    }

    fun lastExchanges(n: Int): List<String> = synchronized(lines) { lines.takeLast(n) }

    /** Header plus lines; when over [maxChars] the middle is cut, keeping head and tail. */
    fun render(maxChars: Int = DEFAULT_MAX_CHARS): String {
        val (head, all) = synchronized(lines) { header to lines.toList() }
        val full = (listOf(head) + all).joinToString("\n")
        if (full.length <= maxChars) return full

        fun build(keepHead: Int, keepTail: Int): String {
            val omitted = all.size - keepHead - keepTail
            return (listOf(head) + all.take(keepHead) + "…($omitted líneas omitidas)…" + all.takeLast(keepTail))
                .joinToString("\n")
        }
        // Grow head and tail alternately while it still fits; the last line is always kept.
        var h = 0
        var t = if (all.isEmpty()) 0 else 1
        while (h + t < all.size) {
            if (build(h + 1, t).length > maxChars) break
            h++
            if (h + t >= all.size) break
            if (build(h, t + 1).length > maxChars) break
            t++
        }
        return build(h, t).take(maxChars)
    }

    override suspend fun open() {
        val t0 = nowMs()
        try {
            inner.open()
            add(t0, "open", "OK", null)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            add(t0, "open", "", e.message ?: e::class.java.simpleName)
            throw e
        }
    }

    override suspend fun command(cmd: String, timeoutMs: Long): String {
        val t0 = nowMs()
        try {
            val response = inner.command(cmd, timeoutMs)
            add(t0, cmd, escapeRaw(response), null)
            return response
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            add(t0, cmd, "", e.message ?: e::class.java.simpleName)
            throw e
        }
    }

    override fun close() = inner.close()

    private fun add(t0: Long, cmd: String, response: String, err: String?) {
        val line = "+${t0 - startMs} > $cmd | $response | ${nowMs() - t0}" + (err?.let { " | ERR $it" } ?: "")
        synchronized(lines) { lines.add(line) }
    }

    companion object {
        const val DEFAULT_MAX_CHARS = 4000
    }
}

internal fun escapeRaw(s: String): String = buildString {
    for (c in s) when {
        c == '\r' -> append('⏎')
        c == '\n' -> append('↵')
        c.code < 0x20 || c.code == 0x7f -> append("\\x%02X".format(c.code))
        else -> append(c)
    }
}
