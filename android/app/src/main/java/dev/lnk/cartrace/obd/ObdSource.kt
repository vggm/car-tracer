package dev.lnk.cartrace.obd

import dev.lnk.cartrace.contract.DtcRecord
import dev.lnk.cartrace.contract.EventRecord
import dev.lnk.cartrace.contract.Events
import dev.lnk.cartrace.contract.ObdRecord
import dev.lnk.cartrace.contract.Record
import dev.lnk.cartrace.core.Clocks
import dev.lnk.cartrace.core.Session
import dev.lnk.cartrace.core.Stamp
import dev.lnk.cartrace.core.stamp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import android.util.Log
import java.io.IOException
import java.util.UUID

sealed interface ObdState {
    data object Connecting : ObdState
    data class Connected(val protocol: String) : ObdState
    data class Retrying(val error: String, val nextInMs: Long) : ObdState
}

/**
 * Reads an ELM327 forever: connect, init, read supported PIDs and DTCs, then poll.
 * Never returns until cancelled; every failure becomes a Retrying state with backoff.
 * [nowMs] is a monotonic ms clock used for the 3 s / 60 s cadences (virtual time in tests).
 */
class ObdSource(
    private val transportFactory: () -> ElmTransport,
    private val clocks: Clocks,
    private val emit: suspend (Record, Stamp) -> Unit,
    private val sessionProvider: () -> Session,
    private val nowMs: () -> Long = { clocks.elapsedMs() },
    private val cycleDelayMs: Long = 100,
) {
    private val _state = MutableStateFlow<ObdState>(ObdState.Connecting)
    val state: StateFlow<ObdState> = _state

    private class InitFailure(message: String, val unableToConnect: Boolean) : Exception(message)

    suspend fun run() {
        var backoffIdx = 0
        var unableCount = 0
        while (true) {
            var connected = false
            var error: String
            var transport: ElmTransport? = null
            try {
                transport = transportFactory()
                _state.value = ObdState.Connecting
                transport.open()
                val protocol = initialize(transport)
                connected = true
                backoffIdx = 0
                unableCount = 0
                _state.value = ObdState.Connected(protocol)
                send(Events.OBD_CONNECTED, protocol)
                readDtcs(transport)
                poll(transport) // only returns by throwing
                error = "poll ended"
            } catch (e: CancellationException) {
                throw e
            } catch (e: InitFailure) {
                error = e.message ?: "init failed"
                if (e.unableToConnect) {
                    if (++unableCount == UNABLE_LIMIT) send(Events.OBD_ERROR, error)
                } else {
                    unableCount = 0
                }
            } catch (e: Exception) {
                error = e.message ?: e.javaClass.simpleName
                if (e !is IOException) error = "${e.javaClass.simpleName}: $error"
                unableCount = 0
            } finally {
                transport?.close()
            }
            if (connected) send(Events.OBD_LOST, error)
            val wait = BACKOFF_MS[minOf(backoffIdx++, BACKOFF_MS.lastIndex)]
            _state.value = ObdState.Retrying(error, wait)
            delay(wait)
        }
    }

    private suspend fun initialize(t: ElmTransport): String {
        t.command("ATZ", LONG_TIMEOUT)
        for (c in listOf("ATE0", "ATL0", "ATS0", "ATH0", "ATSP0")) t.command(c)
        supported = emptySet()
        var next: String? = "0100"
        val found = linkedSetOf<String>()
        var first = true
        while (next != null) {
            val raw = t.command(next, LONG_TIMEOUT)
            if (ElmParser.isError(raw)) {
                val unable = ElmParser.clean(raw).any { it.contains("UNABLETOCONNECT") }
                if (first || unable) {
                    throw InitFailure(
                        if (unable) "UNABLE TO CONNECT" else "init error: ${ElmParser.clean(raw).joinToString(" ")}",
                        unable,
                    )
                }
                break
            }
            first = false
            val pids = ElmParser.supportedPids(listOf(raw))
            found += pids
            next = when (next) {
                "0100" -> "0120".takeIf { it in pids }
                "0120" -> "0140".takeIf { it in pids }
                else -> null
            }
        }
        supported = found
        // After the first OBD request, so ATSP0 has already resolved the protocol.
        return ElmParser.clean(t.command("ATDPN")).firstOrNull().orEmpty()
    }

    private var supported: Set<String> = emptySet()

    private suspend fun readDtcs(t: ElmTransport) {
        val active = ElmParser.dtcs(t.command("03"), '3')
        val pending = ElmParser.dtcs(t.command("07"), '7')
        val s = sessionProvider()
        safeEmit(DtcRecord(newId(), s.id, s.nextSeq(), 0, active, pending))
    }

    private suspend fun poll(t: ElmTransport) {
        val pids = Pid.entries.filter { it.cmd in supported }
        val fresh = linkedMapOf<String, Double>()
        var lastEmit = nowMs()
        var lastVoltage = Long.MIN_VALUE
        while (true) {
            for (pid in pids) ElmParser.value(pid, t.command(pid.cmd))?.let { fresh[pid.key] = it }
            val now = nowMs()
            if (lastVoltage == Long.MIN_VALUE || now - lastVoltage >= VOLTAGE_EVERY_MS) {
                lastVoltage = now
                ElmParser.voltage(t.command("ATRV"))?.let { fresh["voltage_v"] = it }
            }
            if (now - lastEmit >= EMIT_EVERY_MS && fresh.isNotEmpty()) {
                lastEmit = now
                val s = sessionProvider()
                safeEmit(ObdRecord(newId(), s.id, s.nextSeq(), 0, fresh.toMap()))
                fresh.clear()
            }
            delay(cycleDelayMs)
        }
    }

    private suspend fun send(event: String, detail: String?) {
        val s = sessionProvider()
        safeEmit(EventRecord(newId(), s.id, s.nextSeq(), 0, event, detail))
    }

    /** Emit failures (queue/disk) must neither end the loop nor look like a link loss. */
    private suspend fun safeEmit(record: Record) {
        try {
            emit(record, clocks.stamp())
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            runCatching { Log.w("ObdSource", "emit failed, record dropped", e) }
        }
    }

    private fun newId() = UUID.randomUUID().toString()

    private companion object {
        val BACKOFF_MS = longArrayOf(5_000, 10_000, 20_000, 40_000, 80_000, 120_000)
        const val EMIT_EVERY_MS = 3_000L
        const val VOLTAGE_EVERY_MS = 60_000L
        const val UNABLE_LIMIT = 3
        const val LONG_TIMEOUT = 10_000L
    }
}
