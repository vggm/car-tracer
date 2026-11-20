package dev.lnk.cartrace.obd

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.IOException

class LoggingElmTransportTest {
    private class Fake(
        var response: String = "",
        var error: Throwable? = null,
        var openError: Throwable? = null,
    ) : ElmTransport {
        var closed = false
        override suspend fun open() { openError?.let { throw it } }
        override suspend fun command(cmd: String, timeoutMs: Long): String {
            error?.let { throw it }
            return response
        }
        override fun close() { closed = true }
    }

    private val lines = mutableListOf<String>()
    private fun log(capacity: Int = 40) = ElmLog(capacity, nowMs = { 0L }) { lines.clear(); lines.addAll(it) }

    /** Lines without the leading `HH:mm:ss ` so the assertions are time zone independent. */
    private fun bodies() = lines.map { it.substring(9) }

    @Test
    fun linesStartWithTime() = runTest {
        LoggingElmTransport(Fake("OK\r>"), log()).command("ATZ")
        assertTrue(Regex("""\d\d:\d\d:\d\d > ATZ""").matches(lines[0]))
    }

    @Test
    fun logsCommandAndNormalisedResponse() = runTest {
        LoggingElmTransport(Fake("41 00 BE 3F A8 13\r\r>"), log()).command("0100")
        assertEquals(listOf("> 0100", "< 41 00 BE 3F A8 13"), bodies())
    }

    @Test
    fun collapsesLineBreaks() = runTest {
        LoggingElmTransport(Fake("SEARCHING...\rUNABLE TO CONNECT\r\r>"), log()).command("0100")
        assertEquals("< SEARCHING... | UNABLE TO CONNECT", bodies()[1])
    }

    @Test
    fun emptyResponse() = runTest {
        LoggingElmTransport(Fake("\r>"), log()).command("ATZ")
        assertEquals("< (vacío)", bodies()[1])
    }

    @Test
    fun truncatesLongResponse() = runTest {
        LoggingElmTransport(Fake("A".repeat(300) + "\r>"), log()).command("X")
        assertEquals("< " + "A".repeat(120) + "…", bodies()[1])
    }

    @Test
    fun logsExceptionAndRethrowsSame() = runTest {
        val ex = IOException("timeout")
        try {
            LoggingElmTransport(Fake(error = ex), log()).command("0100")
            fail()
        } catch (e: IOException) {
            assertTrue(e === ex)
        }
        assertEquals(listOf("> 0100", "! timeout"), bodies())
    }

    @Test
    fun exceptionWithoutMessageUsesClassName() = runTest {
        try {
            LoggingElmTransport(Fake(error = IOException()), log()).command("0100")
        } catch (_: IOException) {
        }
        assertEquals("! IOException", bodies()[1])
    }

    @Test
    fun cancellationIsNotLogged() = runTest {
        try {
            LoggingElmTransport(Fake(error = CancellationException("x")), log()).command("0100")
            fail()
        } catch (_: CancellationException) {
        }
        assertEquals(listOf("> 0100"), bodies())
    }

    @Test
    fun openLogsSuccess() = runTest {
        LoggingElmTransport(Fake(), log()).open()
        assertEquals(listOf("abriendo conexión", "conexión abierta"), lines.map { it.substring(11) })
    }

    @Test
    fun openFailureLoggedAndRethrown() = runTest {
        val ex = IOException("no socket")
        try {
            LoggingElmTransport(Fake(openError = ex), log()).open()
            fail()
        } catch (e: IOException) {
            assertTrue(e === ex)
        }
        assertEquals("! no socket", bodies()[1])
    }

    @Test
    fun closeDelegates() {
        val inner = Fake()
        LoggingElmTransport(inner, log()).close()
        assertTrue(inner.closed)
    }

    @Test
    fun ringBufferKeepsLastCapacityLines() = runTest {
        val t = LoggingElmTransport(Fake("OK\r>"), log(capacity = 4))
        repeat(3) { t.command("C$it") } // 6 lines
        assertEquals(listOf("> C1", "< OK", "> C2", "< OK"), bodies())
    }
}
