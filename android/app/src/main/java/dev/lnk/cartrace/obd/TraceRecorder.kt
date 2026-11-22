package dev.lnk.cartrace.obd

import dev.lnk.cartrace.contract.MAX_TRACE_DETAIL
import kotlinx.coroutines.CancellationException

/** Decorator that records every raw ELM327 exchange of one connection attempt for diagnostics. */
class TraceRecorder(private val inner: ElmTransport, private val nowMs: () -> Long) : ElmTransport {
    private val lock = Any()
    private val headLines = ArrayList<String>()
    private val tailLines = ArrayDeque<String>()
    private var dropped = 0
    private var header = ""
    private var startMs = nowMs()

    /** Resets the recorded lines and starts the attempt clock. */
    fun begin(header: String) {
        synchronized(lock) {
            this.header = header
            headLines.clear()
            tailLines.clear()
            dropped = 0
            startMs = nowMs()
        }
    }

    /** Appends a free-form line, e.g. `glued=1`. */
    fun note(text: String) {
        synchronized(lock) { store("+${offset(nowMs())} # ${escapeRaw(text)}") }
    }

    fun lastExchanges(n: Int): List<String> = synchronized(lock) { (headLines + tailLines).takeLast(n) }

    internal fun storedLineCount(): Int = synchronized(lock) { headLines.size + tailLines.size }

    /** Header plus lines; when lines were dropped or the text exceeds [maxChars] the middle is cut. */
    fun render(maxChars: Int = MAX_TRACE_DETAIL): String {
        val (head, all, headSize, droppedNow) = synchronized(lock) {
            Snapshot(header, headLines + tailLines, headLines.size, dropped)
        }
        return renderParts(head, all, headSize, droppedNow, maxChars)
    }

    /** [customHeader] plus the last [n] lines, cut in the middle (last line kept) when over [maxChars]. */
    fun renderLast(customHeader: String, n: Int, maxChars: Int = MAX_TRACE_DETAIL): String =
        renderParts(customHeader, lastExchanges(n), 0, 0, maxChars)

    private fun renderParts(head: String, all: List<String>, headSize: Int, droppedNow: Int, maxChars: Int): String {
        if (droppedNow == 0) {
            val full = (listOf(head) + all).joinToString("\n")
            if (full.length <= maxChars) return full
        }
        val maxH = if (droppedNow > 0) headSize else all.size
        val maxT = if (droppedNow > 0) all.size - headSize else all.size

        fun build(keepHead: Int, keepTail: Int): String {
            val omitted = droppedNow + all.size - keepHead - keepTail
            return (listOf(head) + all.take(keepHead) + "…($omitted líneas omitidas)…" + all.takeLast(keepTail))
                .joinToString("\n")
        }
        // Grow head and tail alternately while it still fits; the last line is always kept.
        var h = 0
        var t = if (maxT > 0) 1 else 0
        while (h + t < all.size) {
            if (h < maxH && build(h + 1, t).length <= maxChars) h++ else if (h >= maxH) { /* head full */ } else break
            if (h + t >= all.size) break
            if (t < maxT && build(h, t + 1).length <= maxChars) t++ else if (t >= maxT) { if (h >= maxH) break } else break
        }
        return build(h, t).take(maxChars)
    }

    private data class Snapshot(val header: String, val all: List<String>, val headSize: Int, val dropped: Int)

    private fun offset(at: Long) = maxOf(0L, at - startMs)

    /** Must be called holding [lock]. */
    private fun store(line: String) {
        val capped = if (line.length > MAX_LINE) line.take(MAX_LINE - 1) + "…" else line
        if (headLines.size < KEEP) {
            headLines.add(capped)
        } else {
            tailLines.addLast(capped)
            if (tailLines.size > KEEP) {
                tailLines.removeFirst()
                dropped++
            }
        }
    }

    override suspend fun open() {
        val t0 = nowMs()
        try {
            inner.open()
            add(t0, "open", "OK", null)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            add(t0, "open", "", escapeRaw(e.message ?: e::class.java.simpleName))
            throw e
        }
    }

    override suspend fun command(cmd: String, timeoutMs: Long): String {
        val t0 = nowMs()
        try {
            val response = inner.command(cmd, timeoutMs)
            add(t0, escapeRaw(cmd), escapeRaw(response), null)
            return response
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            add(t0, escapeRaw(cmd), "", escapeRaw(e.message ?: e::class.java.simpleName))
            throw e
        }
    }

    override fun close() = inner.close()

    private fun add(t0: Long, cmd: String, response: String, err: String?) {
        val dur = maxOf(0L, nowMs() - t0)
        synchronized(lock) {
            store("+${offset(t0)} > $cmd | $response | $dur" + (err?.let { " | ERR $it" } ?: ""))
        }
    }

    private companion object {
        const val KEEP = 60
        const val MAX_LINE = 600
    }
}

internal fun escapeRaw(s: String): String = buildString {
    for (c in s) when {
        c == '\r' -> append('⏎')
        c == '\n' -> append('↵')
        c.code < 0x20 || c.code == 0x7f -> append("\\x").append(HEX[c.code shr 4]).append(HEX[c.code and 15])
        else -> append(c)
    }
}

private const val HEX = "0123456789ABCDEF"
