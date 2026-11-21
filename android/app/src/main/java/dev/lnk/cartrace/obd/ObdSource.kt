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
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.ConcurrentHashMap

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
    private val protocolStore: ProtocolStore = NoProtocolStore,
    private val adapterAddress: String = "",
    private val protocolPreference: String = "0",
    /** Scan ids already answered; the service shares one set across ObdSource instances. */
    private val handledScans: MutableSet<String> = ConcurrentHashMap.newKeySet(),
) {
    private val _state = MutableStateFlow<ObdState>(ObdState.Connecting)
    val state: StateFlow<ObdState> = _state

    private val pendingScans = ConcurrentLinkedQueue<String>()
    /**
     * Server asked for a DTC read. Thread-safe; ids already handled are ignored. While Connected the scan
     * runs between poll cycles, otherwise `dtc_scan_failed` is emitted right away.
     */
    suspend fun requestDtcScan(id: String) {
        if (!handledScans.add(id)) return
        pendingScans.add(id)
        if (_state.value !is ObdState.Connected) failPendingScans()
    }

    private suspend fun failPendingScans() {
        while (true) {
            val id = pendingScans.poll() ?: return
            send(Events.DTC_SCAN_FAILED, "$id obd_not_connected")
        }
    }

    private suspend fun runPendingScans(t: ElmTransport) {
        while (true) {
            val id = pendingScans.poll() ?: return
            try {
                readDtcs(t)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                send(Events.DTC_SCAN_FAILED, "$id obd_error")
                throw e
            }
            send(Events.DTC_SCAN, id)
        }
    }

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
                val protocol = initializeWithStoredProtocol(transport)
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
            failPendingScans()
            delay(wait)
        }
    }

    /**
     * Manual preference: only that protocol. Automatic: stored protocol, then the ELM search (0),
     * then the K-line protocols the search often misses on clones. Rethrows the last failure.
     */
    private suspend fun initializeWithStoredProtocol(t: ElmTransport): String {
        val candidates = if (protocolPreference != "0") {
            listOf(protocolPreference)
        } else {
            val stored = protocolStore.get(adapterAddress)?.takeIf { PROTOCOL_NUMBER.matches(it) }
            listOfNotNull(stored, "0", "5", "4", "3").distinct()
        }
        var last: InitFailure? = null
        for (candidate in candidates) {
            try {
                return initialize(t, candidate)
            } catch (e: InitFailure) {
                last = e
            }
        }
        throw last!!
    }

    private suspend fun initialize(t: ElmTransport, protocolNumber: String): String {
        t.command("ATZ", LONG_TIMEOUT)
        val setup = mutableListOf("ATE0", "ATL0", "ATS0", "ATH0", "ATSP$protocolNumber")
        // Some PSA ECUs send non-standard key bytes on K-line; replies (clones answer "?") are ignored.
        if (protocolNumber in K_LINE) setup += "ATKW0"
        for (c in setup) t.command(c)
        supported = emptySet()
        var next: String? = "0100"
        val found = linkedSetOf<String>()
        var first = true
        while (next != null) {
            // The first request may run the whole protocol search (K-line inits take > 10 s).
            val raw = t.command(next, if (first) FIRST_PID_TIMEOUT else LONG_TIMEOUT)
            if (ElmParser.isError(raw)) {
                val unable = ElmParser.isUnableToConnect(raw)
                val busInit = ElmParser.isBusInitError(raw)
                if (first || unable) {
                    throw InitFailure(
                        when {
                            unable -> "UNABLE TO CONNECT"
                            busInit -> "BUS INIT ERROR"
                            else -> "init error: ${ElmParser.clean(raw).joinToString(" ")}"
                        },
                        unable || busInit,
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
        // Ignition in ACC (ECU unpowered) can answer nothing readable: not a connection.
        if (found.isEmpty()) throw InitFailure("no supported PIDs", true)
        supported = found
        // After the first OBD request, so the protocol has already been resolved.
        val dpn = ElmParser.clean(t.command("ATDPN")).firstOrNull().orEmpty()
        val number = dpn.removePrefix("A")
        if (PROTOCOL_NUMBER.matches(number)) protocolStore.put(adapterAddress, number)
        return dpn
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
            runPendingScans(t)
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
        safeEmit(EventRecord(newId(), s.id, s.nextSeq(), 0, event, detail?.take(MAX_DETAIL)))
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
        const val FIRST_PID_TIMEOUT = 30_000L
        const val MAX_DETAIL = 200
        val K_LINE = setOf("3", "4", "5")
        val PROTOCOL_NUMBER = Regex("[1-9A-C]")
    }
}
