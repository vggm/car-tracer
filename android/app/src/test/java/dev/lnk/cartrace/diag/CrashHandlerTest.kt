package dev.lnk.cartrace.diag

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CrashHandlerTest {
    @Test
    fun crashTextStripsDeviceAndStoragePaths() {
        val store = object : PendingDiagStore {
            val l = mutableListOf<Pair<String, String>>()
            override fun add(code: String, text: String) { l.add(code to text) }
            override fun drain() = l.toList().also { l.clear() }
        }
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        try {
            installCrashHandler(store, null)
            Thread.getDefaultUncaughtExceptionHandler()!!.uncaughtException(
                Thread.currentThread(),
                RuntimeException("cannot open /data/user/0/dev.lnk/files/x and /storage/emulated/0/y"),
            )
        } finally {
            Thread.setDefaultUncaughtExceptionHandler(prev)
        }
        val t = store.l.single().second
        assertFalse(t.contains("/data/user"))
        assertFalse(t.contains("/storage/emulated"))
        assertTrue(t.contains("RuntimeException"))
    }
}
