package dev.lnk.cartrace.diag

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DiagnosticsTest {
    private var now = 0L
    private val out = mutableListOf<Pair<String, String>>()
    private val diag = Diagnostics({ now }, { c, t -> out.add(c to t) })

    @Test
    fun dedupesWithinWindowAndReportsCount() = runBlocking {
        diag.report("gps.no_fix", "a")
        now = 30_000; diag.report("gps.no_fix", "b")
        now = 60_000; diag.report("gps.no_fix", "c")
        assertEquals(listOf("gps.no_fix" to "gps.no_fix a"), out)
        now = 600_000; diag.report("gps.no_fix", "d")
        assertEquals(2, out.size)
        assertEquals("gps.no_fix x2 d", out[1].second)
    }

    @Test
    fun differentCodesIndependent() = runBlocking {
        diag.report("a.x", "1"); diag.report("b.y", "2")
        assertEquals(2, out.size)
    }

    @Test
    fun truncatesTo500() = runBlocking {
        diag.report("a.x", "z".repeat(900))
        assertEquals(500, out[0].second.length)
    }

    @Test
    fun pendingCrashEmittedOnceOnNextStart() = runBlocking {
        val store = object : PendingDiagStore {
            val l = mutableListOf<Pair<String, String>>()
            override fun add(code: String, text: String) { l.add(code to text) }
            override fun drain() = l.toList().also { l.clear() }
        }
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        var called = false
        try {
            installCrashHandler(store) { _, _ -> called = true }
            Thread.getDefaultUncaughtExceptionHandler()!!
                .uncaughtException(Thread.currentThread(), IllegalStateException("boom"))
        } finally {
            Thread.setDefaultUncaughtExceptionHandler(prev)
        }
        assertTrue(called)
        diag.flushPending(store)
        assertEquals(1, out.size)
        assertTrue(out[0].second.startsWith("app.crash java.lang.IllegalStateException: boom"))
        diag.flushPending(store)
        assertEquals(1, out.size)
    }

    @Test
    fun sanitizeRemovesMacAndTokens() {
        val s = sanitize("dev AA:BB:CC:DD:EE:FF url?token=abc123 Authorization: Bearer xyz.789")
        assertFalse(s.contains("AA:BB"))
        assertFalse(s.contains("abc123"))
        assertFalse(s.contains("xyz.789"))
    }
}
