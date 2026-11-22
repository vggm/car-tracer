package dev.lnk.cartrace.service

import android.util.Log
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Launches long-running children and relaunches them 5 s after a crash. */
class Supervisor(
    private val scope: CoroutineScope,
    private val onCrash: suspend (name: String, e: Throwable) -> Unit = { _, _ -> },
) {
    fun launch(name: String, block: suspend () -> Unit): Job = scope.launch {
        while (true) {
            try {
                block()
                return@launch
            } catch (e: CancellationException) {
                throw e
            } catch (e: Throwable) {
                val msg = "$name: ${e.javaClass.simpleName}: ${e.message ?: ""}".trim()
                runCatching { Log.w("CarTrace", "child crashed, restarting in 5 s: $msg", e) }
                Status.addError(msg)
                try {
                    onCrash(name, e)
                } catch (c: CancellationException) {
                    throw c
                } catch (_: Throwable) {
                }
            }
            delay(RESTART_DELAY_MS)
        }
    }

    private companion object { const val RESTART_DELAY_MS = 5_000L }
}
