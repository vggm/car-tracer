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

    @Test
    fun boundsMemoryOverLongSessions() = runTest {
        val rec = TraceRecorder(Fake("OK>", step = 0), { 0L })
        rec.begin("HEADER")
        repeat(10_000) { rec.command("C$it") }
        assertTrue(rec.storedLineCount() <= 120)
        assertEquals((9_980 until 10_000).map { "+0 > C$it | OK> | 0" }, rec.lastExchanges(20))
        val out = rec.render()
        assertTrue(out.length <= 4000)
        assertTrue(out.startsWith("HEADER"))
        assertEquals("+0 > C9999 | OK> | 0", out.lines().last())
        val omitted = Regex("""…\((\d+) líneas omitidas\)…""").find(out)!!.groupValues[1].toInt()
        val shown = out.lines().count { it.startsWith("+") }
        assertEquals(10_000, shown + omitted)
    }

    @Test
    fun capsLongLinesAndEscapesCommand() = runTest {
        val rec = TraceRecorder(Fake("y".repeat(2000)), { 0L })
        rec.begin("H")
        rec.command("A\rT")
        val line = rec.lastExchanges(1).single()
        assertTrue(line.length <= 600 && line.contains("…"))
        assertTrue(line.startsWith("+0 > A⏎T | "))
    }

    @Test
    fun noteAndBeginReset() = runTest {
        var now = 5L
        val rec = TraceRecorder(Fake("OK>", step = 0), { now })
        rec.begin("H1")
        rec.command("A")
        now = 12
        rec.note("glued=1")
        assertEquals("+7 # glued=1", rec.lastExchanges(1).single())
        rec.begin("H2")
        assertEquals("H2", rec.render())
        assertEquals(emptyList<String>(), rec.lastExchanges(5))
    }

    @Test
    fun openRecordsOkAndErr() = runTest {
        val ok = TraceRecorder(Fake(), { 0L })
        ok.begin("H")
        ok.open()
        assertEquals("+0 > open | OK | 0", ok.lastExchanges(1).single())
        val bad = TraceRecorder(object : ElmTransport {
            override suspend fun open() { throw IOException("no route") }
            override suspend fun command(cmd: String, timeoutMs: Long) = ""
            override fun close() {}
        }, { 0L })
        bad.begin("H")
        try { bad.open(); fail("expected") } catch (e: IOException) { }
        assertTrue(bad.lastExchanges(1).single().endsWith("| ERR no route"))
    }
}
