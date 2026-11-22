package dev.lnk.cartrace.diag

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DiagnosticsHardeningTest {
    @Test
    fun sanitizeVariants() {
        val s = sanitize(
            "a AA-BB-CC-DD-EE-FF b aabbccddeeff c access_token: s3cr3t d refresh_token=r3f e " +
                "?api_key=K1&key=K2 Authorization: Basic QWxhZGRpbg== at /sdcard/x /home/u/y " +
                "/Users/z/w /mnt/q https://example.com/home/page",
        )
        for (bad in listOf("AA-BB", "aabbccddeeff", "s3cr3t", "r3f", "K1", "K2", "QWxhZGRpbg", "/sdcard", "/home/u", "/Users/z", "/mnt/q")) {
            assertFalse("leaked $bad in $s", s.contains(bad))
        }
        assertTrue(s, s.contains("https://example.com/home/page"))
    }

    @Test
    fun boundedStoreKeepsLast20AndTruncates() {
        var raw: String? = null
        val store = JsonPendingDiagStore({ raw }, { raw = it })
        repeat(25) { store.add("c$it", "x".repeat(900)) }
        val d = store.drain()
        assertEquals(20, d.size)
        assertEquals("c5", d.first().first)
        assertEquals(500, d.first().second.length)
        assertTrue(store.drain().isEmpty())
    }

    @Test
    fun corruptStorageNeverThrows() {
        var raw: String? = "{not json["
        val store = JsonPendingDiagStore({ raw }, { raw = it })
        assertTrue(store.drain().isEmpty())
        raw = "[1,2"
        store.add("a", "b")
        assertEquals(listOf("a" to "b"), store.drain())
    }

    @Test
    fun crashHandlerChainsWhenStoreThrowsOrPreviousNull() {
        val bad = object : PendingDiagStore {
            override fun add(code: String, text: String) = throw RuntimeException("x")
            override fun drain() = emptyList<Pair<String, String>>()
        }
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        try {
            var called = false
            installCrashHandler(bad) { _, _ -> called = true }
            Thread.getDefaultUncaughtExceptionHandler()!!.uncaughtException(Thread.currentThread(), RuntimeException("e"))
            assertTrue(called)
            Thread.setDefaultUncaughtExceptionHandler(prev)
            installCrashHandler(bad, null)
            Thread.getDefaultUncaughtExceptionHandler()!!.uncaughtException(Thread.currentThread(), RuntimeException("e"))
        } finally {
            Thread.setDefaultUncaughtExceptionHandler(prev)
        }
    }

    @Test
    fun secondInstallIsNoOp() {
        var n = 0
        val store = object : PendingDiagStore {
            override fun add(code: String, text: String) { n++ }
            override fun drain() = emptyList<Pair<String, String>>()
        }
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        try {
            installCrashHandler(store, null)
            installCrashHandler(store, null)
            Thread.getDefaultUncaughtExceptionHandler()!!.uncaughtException(Thread.currentThread(), RuntimeException("e"))
            assertEquals(1, n)
        } finally {
            Thread.setDefaultUncaughtExceptionHandler(prev)
        }
    }

    @Test
    fun emitFailureKeepsSuppressedCount() = runBlocking {
        var now = 0L
        var fail = false
        val out = mutableListOf<String>()
        val d = Diagnostics({ now }, { _, t -> if (fail) throw RuntimeException("net"); out.add(t) })
        d.report("a.b", "1"); now = 1; d.report("a.b", "2"); now = 2; d.report("a.b", "3")
        now = 600_000; fail = true
        try { d.report("a.b", "4") } catch (_: RuntimeException) {}
        fail = false; now = 600_001
        d.report("a.b", "5")
        assertEquals("a.b x2 5", out.last())
    }
}
