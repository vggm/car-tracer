package dev.lnk.cartrace.diag

private val PATH_RE = Regex("(/data/|/storage/)\\S*")

fun installCrashHandler(store: PendingDiagStore, previous: Thread.UncaughtExceptionHandler?) {
    Thread.setDefaultUncaughtExceptionHandler { thread, e ->
        try {
            val stack = e.stackTrace.take(5).joinToString(" | ") { it.toString() }
            val text = sanitize("${e.javaClass.name}: ${e.message} @ $stack")
                .replace(PATH_RE, "<path>")
            store.add("app.crash", text)
        } catch (_: Throwable) {
        }
        previous?.uncaughtException(thread, e)
    }
}
