package dev.lnk.cartrace.obd

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.IOException

class TraceRecorderTest {
    private class Fake(
        val response: String = "",
        val error: Throwable? = null,
        val advance: (Long) -> Unit = {},
        val step: Long = 800,
    ) : ElmTransport {
        override suspend fun open() {}
        override suspend fun command(cmd: String, timeoutMs: Long): String {
            advance(step)
            error?.let { throw it }
            return response
        }
        override fun close() {}
    }

    @Test
    fun escapesControlCharacters() {
        assertEquals("OK⏎41 00↵>", escapeRaw("OK\r41 00\n>"))
        assertEquals("\\x01", escapeRaw("\u0001"))
    }

    @Test
    fun recordsCommandResponseAndDuration() = runTest {
        var now = 0L
        val rec = TraceRecorder(Fake("ELM327 v1.5\r\r>", advance = { now += it }), { now })
        rec.begin("H")
        rec.command("ATZ")
        assertEquals("+0 > ATZ | ELM327 v1.5⏎⏎> | 800", rec.lastExchanges(1).single())
        assertEquals("H\n+0 > ATZ | ELM327 v1.5⏎⏎> | 800", rec.render())
    }

    @Test
    fun recordsErrors() = runTest {
        var now = 0L
        val rec = TraceRecorder(
            Fake(error = IOException("timeout after 2000ms"), advance = { now += it }, step = 2000),
            { now },
        )
        rec.begin("H")
        try {
            rec.command("ATZ")
            fail("expected IOException")
        } catch (e: IOException) {
            assertEquals("timeout after 2000ms", e.message)
        }
        assertTrue(rec.lastExchanges(1).single().endsWith("| ERR timeout after 2000ms"))
    }

    @Test
    fun truncatesMiddleKeepingHeadAndTail() = runTest {
        val rec = TraceRecorder(Fake("x".repeat(80)), { 0L })
        rec.begin("HEADER")
        repeat(200) { rec.command("CMD$it") }
        val out = rec.render()
        assertTrue(out.length <= 4000)
        assertTrue(out.startsWith("HEADER"))
        assertTrue(out.contains("…(") && out.contains("líneas omitidas)…"))
        assertEquals(rec.lastExchanges(1).single(), out.lines().last())
    }
}
