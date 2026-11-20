package dev.lnk.cartrace.obd

import dev.lnk.cartrace.ui.Formatters
import kotlinx.coroutines.CancellationException

/** Ring buffer of the last [capacity] log lines; every append pushes the full list (oldest first) to [sink]. */
class ElmLog(
    private val capacity: Int = 40,
    private val nowMs: () -> Long = System::currentTimeMillis,
    private val sink: (List<String>) -> Unit,
) {
    private val lines = ArrayDeque<String>()

    /** Appends `HH:mm:ss <text>`. */
    fun add(text: String) {
        val snapshot = synchronized(lines) {
            lines.addLast("${Formatters.time(nowMs())} $text")
            while (lines.size > capacity) lines.removeFirst()
            lines.toList()
        }
        sink(snapshot)
    }
}

/** Decorator that records the raw ELM327 conversation in an [ElmLog] for on-screen diagnostics. */
class LoggingElmTransport(private val inner: ElmTransport, private val log: ElmLog) : ElmTransport {
    override suspend fun open() {
        log.add("· abriendo conexión")
        try {
            inner.open()
            log.add("· conexión abierta")
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            log.add("! ${describe(e)}")
            throw e
        }
    }

    override suspend fun command(cmd: String, timeoutMs: Long): String {
        log.add("> $cmd")
        try {
            val response = inner.command(cmd, timeoutMs)
            log.add("< ${display(response)}")
            return response
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) {
            log.add("! ${describe(e)}")
            throw e
        }
    }

    override fun close() = inner.close()

    private fun describe(e: Throwable) = e.message ?: e::class.java.simpleName

    private fun display(raw: String): String {
        val s = raw.trim().removeSuffix(">").trim().replace(Regex("[\r\n]+"), " | ")
        return when {
            s.isEmpty() -> "(vacío)"
            s.length > MAX_LEN -> s.take(MAX_LEN) + "…"
            else -> s
        }
    }

    private companion object {
        const val MAX_LEN = 120
    }
}
