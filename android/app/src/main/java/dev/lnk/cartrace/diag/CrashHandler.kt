package dev.lnk.cartrace.diag

import dev.lnk.cartrace.contract.MAX_DIAG_DETAIL

private class CrashHandler(
    private val store: PendingDiagStore,
    private val previous: Thread.UncaughtExceptionHandler?,
) : Thread.UncaughtExceptionHandler {
    override fun uncaughtException(thread: Thread, e: Throwable) {
        try {
            val msg = e.message?.take(MAX_DIAG_DETAIL)
            val stack = e.stackTrace.take(5).joinToString(" | ") { it.toString() }
            val text = sanitize("${e.javaClass.name}: $msg @ $stack".take(MAX_DIAG_DETAIL * 2))
            store.add("app.crash", text.take(MAX_DIAG_DETAIL))
        } catch (_: Throwable) {
        }
        previous?.uncaughtException(thread, e)
    }
}

fun installCrashHandler(store: PendingDiagStore, previous: Thread.UncaughtExceptionHandler?) {
    if (Thread.getDefaultUncaughtExceptionHandler() is CrashHandler) return
    Thread.setDefaultUncaughtExceptionHandler(CrashHandler(store, previous))
}
