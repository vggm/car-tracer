package dev.lnk.cartrace.obd

import dev.lnk.cartrace.contract.DtcRecord
import dev.lnk.cartrace.contract.Events
import dev.lnk.cartrace.contract.EventRecord
import dev.lnk.cartrace.contract.ObdRecord
import dev.lnk.cartrace.contract.Record
import dev.lnk.cartrace.core.FakeClocks
import dev.lnk.cartrace.core.Session
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

private const val MASK_0100 = "41 00 18 38 80 01\r\r>"
private const val MASK_0120 = "41 20 00 00 00 01\r\r>"
private const val MASK_0140 = "41 40 00 00 00 00\r\r>"

/** Scripted transport: [failAfter] commands succeed, then every command throws IOException. */
private class ScriptedTransport(
    val log: MutableList<String>,
    val failAfter: Int = Int.MAX_VALUE,
    val openError: IOException? = null,
    val on0100: String = MASK_0100,
    val dpn: String = "A6",
    val failOnSp: String? = null,
    val failSps: Set<String> = emptySet(),
    val lostMessage: String = "link lost",
    val timeouts: MutableMap<String, Long> = mutableMapOf(),
    val atrv: String = "12.6V\r\r>",
    val timeoutOn0100: String? = null,
) : ElmTransport {
    var closed = false
    var failOn03 = false
    var answer03: String? = null
    var answer04: String = "44\r\r>"
    var failOn04 = false
    var rpmAnswer = "41 0C 1A F8\r\r>"
    private var count = 0
    private var lastSp = ""
    override suspend fun open() { openError?.let { throw it } }
    override suspend fun command(cmd: String, timeoutMs: Long): String {
        if (count++ >= failAfter) throw IOException(lostMessage)
        if (failOn03 && cmd == "03") throw IOException("link lost mid-scan")
        if (failOn04 && cmd == "04") throw IOException("link lost mid-clear")
        log += cmd
        timeouts.putIfAbsent(cmd, timeoutMs)
        if (cmd.startsWith("ATSP")) lastSp = cmd
        return when (cmd) {
            "ATZ" -> "ELM327 v1.5\r\r>"
            "ATDPN" -> "$dpn\r\r>"
            "0100" -> if (timeoutOn0100 != null) throw IOException(timeoutOn0100) else if (lastSp == failOnSp || lastSp in failSps) "UNABLE TO CONNECT\r\r>" else on0100
            "0120" -> MASK_0120
            "0140" -> MASK_0140
            "03" -> answer03 ?: "43 01 33 00 00 00 00\r\r>"
            "07" -> "47 02 00 00 00 00 00\r\r>"
            "ATRV" -> atrv
            "04" -> answer04
            "010C" -> rpmAnswer
            "010D" -> "41 0D 32\r\r>"
            "0105" -> "41 05 5A\r\r>"
            "010B" -> "41 0B 63\r\r>"
            "0104" -> "41 04 40\r\r>"
            "0111" -> "41 11 33\r\r>"
            "015E" -> "NO DATA\r\r>"
            else -> "OK\r\r>"
        }
    }
    override fun close() { closed = true }
}

@OptIn(ExperimentalCoroutinesApi::class)
class ObdSourceTest {
    private val records = mutableListOf<Record>()
    private val session = Session("s1")

    private fun TestScope.source(factory: () -> ElmTransport) = ObdSource(
        transportFactory = factory,
        clocks = FakeClocks(),
        emit = { r, _ -> records += r },
        sessionProvider = { session },
        nowMs = { currentTime },
        delayFn = {},
    )

    private fun events() = records.filterIsInstance<EventRecord>().filter { it.event != Events.OBD_TRACE }

    private fun traces() = records.filterIsInstance<EventRecord>().filter { it.event == Events.OBD_TRACE }.map { it.detail!! }

    @Test
    fun initSequenceAndConnectedEvent() = runTest {
        val log = mutableListOf<String>()
        val src = source { ScriptedTransport(log) }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertEquals(
            listOf("ATI", "AT@1", "ATDP", "ATDPN", "ATRV", "ATPPS", "ATZ", "ATE0", "ATL0", "ATS0", "ATH0", "ATSP0", "0100", "0120", "0140", "ATDPN"),
            log.take(16),
        )
        assertEquals(ObdState.Connected("A6"), src.state.value)
        assertEquals(listOf(Events.OBD_CONNECTED), events().map { it.event })
        job.cancel()
    }

    @Test
    fun emitsDtcOnConnect() = runTest {
        val src = source { ScriptedTransport(mutableListOf()) }
        val job = launch { src.run() }
        advanceTimeBy(100)
        val dtc = records.filterIsInstance<DtcRecord>().single()
        assertEquals(listOf("P0133"), dtc.active)
        assertEquals(listOf("P0200"), dtc.pending)
        assertEquals("s1", dtc.session_id)
        job.cancel()
    }

    @Test
    fun emitsObdEvery3s() = runTest {
        val src = source { ScriptedTransport(mutableListOf()) }
        val job = launch { src.run() }
        advanceTimeBy(9_050)
        val obd = records.filterIsInstance<ObdRecord>()
        assertEquals(3, obd.size)
        assertEquals(1726.0, obd[0].values["rpm"]!!, 0.01)
        assertEquals(50.0, obd[0].values["speed_kmh"]!!, 0.01)
        assertEquals(50.0, obd[0].values["coolant_c"]!!, 0.01)
        assertFalse(obd[0].values.containsKey("fuel_rate_lph"))
        assertEquals(3, obd.map { it.seq }.distinct().size)
        job.cancel()
    }

    @Test
    fun voltageEvery60s() = runTest {
        val log = mutableListOf<String>()
        val src = source { ScriptedTransport(log) }
        val job = launch { src.run() }
        advanceTimeBy(125_000)
        assertEquals(4, log.count { it == "ATRV" }) // 1 probe + 3 polls
        val obd = records.filterIsInstance<ObdRecord>()
        val withV = obd.count { it.values.containsKey("voltage_v") }
        assertEquals(3, withV)
        assertEquals(12.6, obd.first { it.values.containsKey("voltage_v") }.values["voltage_v"]!!, 0.01)
        job.cancel()
    }

    @Test
    fun skipsUnsupportedPid() = runTest {
        val log = mutableListOf<String>()
        val src = source { ScriptedTransport(log) }
        val job = launch { src.run() }
        advanceTimeBy(10_000)
        assertTrue(log.contains("010C"))
        assertFalse(log.contains("015E"))
        job.cancel()
    }

    @Test
    fun ioErrorEmitsLostAndBacksOff() = runTest {
        var calls = 0
        val src = source {
            when (calls++) {
                0 -> ScriptedTransport(mutableListOf(), failAfter = 20)
                else -> ScriptedTransport(mutableListOf(), openError = IOException("gone"))
            }
        }
        val job = launch { src.run() }
        advanceTimeBy(500)
        assertEquals(
            listOf(Events.OBD_CONNECTED, Events.OBD_LOST),
            events().map { it.event }.filter { it != Events.OBD_ATTEMPT_FAILED },
        )
        val first = src.state.value as ObdState.Retrying
        assertEquals(5_000L, first.nextInMs)
        advanceTimeBy(5_100)
        assertEquals(10_000L, (src.state.value as ObdState.Retrying).nextInMs)
        // never connected again: no extra obd_lost
        assertEquals(1, events().count { it.event == Events.OBD_LOST })
        assertEquals(2, events().count { it.event != Events.OBD_ATTEMPT_FAILED })
        job.cancel()
    }

    @Test
    fun transportOpenFailsKeepsRetrying() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), openError = IOException("not paired")) }
        val job = launch { src.run() }
        advanceTimeBy(100)
        val st = src.state.value as ObdState.Retrying
        assertTrue(st.error.contains("not paired"))
        assertEquals(5_000L, st.nextInMs)
        assertTrue(job.isActive)
        assertEquals(listOf(Events.OBD_ATTEMPT_FAILED), events().map { it.event })
        job.cancel()
    }

    @Test
    fun backoffCapsAtTwoMinutes() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), openError = IOException("x")) }
        val job = launch { src.run() }
        advanceTimeBy(5_000 + 10_000 + 20_000 + 40_000 + 80_000 + 120_000 + 1_000)
        assertEquals(120_000L, (src.state.value as ObdState.Retrying).nextInMs)
        job.cancel()
    }

    @Test
    fun emitFailureDoesNotStopSource() = runTest {
        var thrown = false
        val src = ObdSource(
            transportFactory = { ScriptedTransport(mutableListOf()) },
            clocks = FakeClocks(),
            emit = { r, _ ->
                if (!thrown) { thrown = true; throw IllegalStateException("disk full") }
                records += r
            },
            sessionProvider = { session },
            nowMs = { currentTime },
        )
        val job = launch { src.run() }
        advanceTimeBy(7_000)
        assertTrue(thrown)
        assertTrue(src.state.value is ObdState.Connected)
        assertTrue(records.filterIsInstance<ObdRecord>().isNotEmpty())
        assertTrue(job.isActive)
        job.cancel()
    }

    @Test
    fun factoryThrowingKeepsRetrying() = runTest {
        var calls = 0
        val src = source {
            if (calls++ == 0) throw IllegalStateException("boom")
            ScriptedTransport(mutableListOf())
        }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertTrue(src.state.value is ObdState.Retrying)
        advanceTimeBy(5_100)
        assertTrue(src.state.value is ObdState.Connected)
        job.cancel()
    }

    @Test
    fun unableToConnectThreeTimesEmitsObdError() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), on0100 = "UNABLE TO CONNECT\r\r>") }
        val job = launch { src.run() }
        advanceTimeBy(5_000 + 10_000 + 1_000)
        assertEquals(1, events().count { it.event == Events.OBD_ERROR })
        advanceTimeBy(20_000 + 40_000 + 80_000 + 1_000) // more failures: still just one obd_error
        val errs = events().filter { it.event == Events.OBD_ERROR }
        assertEquals(1, errs.size)
        assertTrue(errs[0].detail!!.contains("UNABLE TO CONNECT"))
        assertTrue(src.state.value is ObdState.Retrying)
        assertTrue(events().none { it.event == Events.OBD_CONNECTED })
        job.cancel()
    }

    private fun attempts() = events().filter { it.event == Events.OBD_ATTEMPT_FAILED }.map { it.detail!! }

    @Test
    fun openFailureIsReportedAsAttempt() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), openError = IOException("connect failed")) }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertTrue(attempts().single().startsWith("n=1 t=0s v=? | open: connect failed"))
        job.cancel()
    }

    @Test
    fun unableOnEveryCandidateListsThemAndVoltage() = runTest {
        val src = source {
            ScriptedTransport(mutableListOf(), on0100 = "UNABLE TO CONNECT\r\r>", atrv = "12.4V\r\r>")
        }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertEquals(
            "n=1 t=0s v=12.4V | 0: UNABLE TO CONNECT | 5: UNABLE TO CONNECT | 4: UNABLE TO CONNECT | 3: UNABLE TO CONNECT var=V1",
            attempts().first(),
        )
        job.cancel()
    }

    @Test
    fun noSupportedPidsKeepsRawResponse() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), on0100 = "7F0112\r\r>") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertTrue(attempts().first().contains("| 0: no supported PIDs [7F0112] |"))
        job.cancel()
    }

    @Test
    fun firstPidTimeoutEndsLoopAndSkipsVoltage() = runTest {
        val log = mutableListOf<String>()
        val src = source {
            ScriptedTransport(log, timeoutOn0100 = "timeout after 30000ms waiting for 0100")
        }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertEquals(
            "n=1 t=0s v=? | 0: timeout after 30000ms waiting for 0100 var=V1",
            attempts().single(),
        )
        assertEquals(1, log.count { it == "ATRV" }) // only the probe's
        job.cancel()
    }

    @Test
    fun secondAttemptCountsAndUsesVirtualTime() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), openError = IOException("connect failed")) }
        val job = launch { src.run() }
        advanceTimeBy(5_100)
        val a = attempts()
        assertEquals(2, a.size)
        assertTrue(a[1].startsWith("n=2 t=5s v=? | open:"))
        job.cancel()
    }

    @Test
    fun connectedDetailCarriesAttemptAndRestartsAfterLoss() = runTest {
        var created = 0
        val src = source {
            when (++created) {
                1 -> ScriptedTransport(mutableListOf(), on0100 = "UNABLE TO CONNECT\r\r>")
                2 -> ScriptedTransport(mutableListOf(), failAfter = 20)
                else -> ScriptedTransport(mutableListOf())
            }
        }
        val job = launch { src.run() }
        advanceTimeBy(20_000)
        val connected = events().filter { it.event == Events.OBD_CONNECTED }.map { it.detail!! }
        assertEquals("A6 n=2 t=5s var=V1", connected[0])
        assertTrue(connected[1].startsWith("A6 n=1 t="))
        job.cancel()
    }

    @Test
    fun attemptEventPrecedesObdError() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), on0100 = "UNABLE TO CONNECT\r\r>") }
        val job = launch { src.run() }
        advanceTimeBy(5_000 + 10_000 + 1_000)
        val names = events().map { it.event }
        assertEquals(3, names.count { it == Events.OBD_ATTEMPT_FAILED })
        assertEquals(listOf(Events.OBD_ATTEMPT_FAILED, Events.OBD_ATTEMPT_FAILED, Events.OBD_ATTEMPT_FAILED, Events.OBD_ERROR), names)
        job.cancel()
    }

    private class MemStore(val map: MutableMap<String, String> = mutableMapOf()) : ProtocolStore {
        override fun get(address: String) = map[address]
        override fun put(address: String, protocol: String) { map[address] = protocol }
    }

    private fun TestScope.sourceWith(
        store: ProtocolStore,
        pref: String = "0",
        factory: () -> ElmTransport,
    ) = ObdSource(
        transportFactory = factory,
        clocks = FakeClocks(),
        emit = { r, _ -> records += r },
        sessionProvider = { session },
        nowMs = { currentTime },
        protocolStore = store,
        adapterAddress = "AA:BB",
        protocolPreference = pref,
        delayFn = {},
    )

    @Test
    fun storesProtocolFromAtdpnWithoutAutoPrefix() = runTest {
        val store = MemStore()
        val src = sourceWith(store) { ScriptedTransport(mutableListOf()) }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertEquals("6", store.get("AA:BB"))
        assertEquals(ObdState.Connected("A6"), src.state.value)
        job.cancel()
    }

    @Test
    fun usesStoredProtocolInsteadOfAuto() = runTest {
        val log = mutableListOf<String>()
        val src = sourceWith(MemStore(mutableMapOf("AA:BB" to "6"))) { ScriptedTransport(log, dpn = "6") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertTrue(log.contains("ATSP6"))
        assertFalse(log.contains("ATSP0"))
        assertTrue(src.state.value is ObdState.Connected)
        job.cancel()
    }

    @Test
    fun fallsBackToAutoWhenStoredProtocolFails() = runTest {
        val log = mutableListOf<String>()
        val store = MemStore(mutableMapOf("AA:BB" to "9"))
        val src = sourceWith(store) { ScriptedTransport(log, failOnSp = "ATSP9") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertTrue(src.state.value is ObdState.Connected)
        assertTrue(log.indexOf("ATSP9") in 0 until log.indexOf("ATSP0"))
        assertEquals("6", store.get("AA:BB"))
        job.cancel()
    }

    @Test
    fun autoFallsBackToKwpFastWhenSearchFails() = runTest {
        val log = mutableListOf<String>()
        val store = MemStore()
        val src = sourceWith(store) { ScriptedTransport(log, failSps = setOf("ATSP0"), dpn = "5") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertEquals(ObdState.Connected("5"), src.state.value)
        assertTrue(log.indexOf("ATSP0") in 0 until log.indexOf("ATSP5"))
        assertEquals("ATKW0", log[log.indexOf("ATSP5") + 1])
        assertFalse(log.contains("ATSP4"))
        assertEquals("5", store.get("AA:BB"))
        job.cancel()
    }

    @Test
    fun autoSearchDoesNotSendAtkw0() = runTest {
        val log = mutableListOf<String>()
        val src = sourceWith(MemStore()) { ScriptedTransport(log) }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertFalse(log.contains("ATKW0"))
        job.cancel()
    }

    @Test
    fun manualProtocolTriesOnlyThatOne() = runTest {
        val log = mutableListOf<String>()
        val src = sourceWith(MemStore(), pref = "5") { ScriptedTransport(log, dpn = "5") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertTrue(src.state.value is ObdState.Connected)
        assertEquals(1, log.count { it.startsWith("ATSP") })
        assertEquals("ATSP5", log.first { it.startsWith("ATSP") })
        assertTrue(log.contains("ATKW0"))
        job.cancel()
    }

    @Test
    fun manualProtocolIgnoresStoredAndDoesNotFallBack() = runTest {
        val log = mutableListOf<String>()
        val src = sourceWith(MemStore(mutableMapOf("AA:BB" to "6")), pref = "5") {
            ScriptedTransport(log, failSps = setOf("ATSP5"))
        }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertEquals(listOf("ATSP5"), log.filter { it.startsWith("ATSP") })
        val st = src.state.value as ObdState.Retrying
        assertTrue(st.error.contains("UNABLE TO CONNECT"))
        job.cancel()
    }

    @Test
    fun canProtocolDoesNotGetAtkw0() = runTest {
        val log = mutableListOf<String>()
        val src = sourceWith(MemStore(), pref = "6") { ScriptedTransport(log, dpn = "6") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertTrue(src.state.value is ObdState.Connected)
        assertFalse(log.contains("ATKW0"))
        job.cancel()
    }

    @Test
    fun storedProtocolIsTriedFirstThenAutoSequence() = runTest {
        val log = mutableListOf<String>()
        val src = sourceWith(MemStore(mutableMapOf("AA:BB" to "3"))) {
            ScriptedTransport(log, failSps = setOf("ATSP3", "ATSP0", "ATSP5"), dpn = "4")
        }
        val job = launch { src.run() }
        advanceTimeBy(100)
        // stored 3 first, then 0, 5, 4 (3 not repeated)
        assertEquals(listOf("ATSP3", "ATSP0", "ATSP5", "ATSP4"), log.filter { it.startsWith("ATSP") })
        assertTrue(src.state.value is ObdState.Connected)
        job.cancel()
    }

    @Test
    fun allCandidatesFailKeepsObdErrorBehaviour() = runTest {
        val log = mutableListOf<String>()
        val src = sourceWith(MemStore()) { ScriptedTransport(log, on0100 = "UNABLE TO CONNECT\r\r>") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertEquals(listOf("ATSP0", "ATSP5", "ATSP4", "ATSP3"), log.filter { it.startsWith("ATSP") })
        val st = src.state.value as ObdState.Retrying
        assertTrue(st.error.contains("UNABLE TO CONNECT"))
        advanceTimeBy(5_000 + 10_000 + 1_000)
        assertEquals(1, events().count { it.event == Events.OBD_ERROR })
        assertTrue(events().none { it.event == Events.OBD_CONNECTED })
        job.cancel()
    }

    @Test
    fun lastInitFailureIsRethrown() = runTest {
        // ATSP0/5/4 say UNABLE TO CONNECT, ATSP3 (last) gives a non-connection error: that one is reported
        val src = sourceWith(MemStore()) {
            object : ElmTransport {
                var sp = ""
                override suspend fun open() {}
                override suspend fun command(cmd: String, timeoutMs: Long): String {
                    if (cmd.startsWith("ATSP")) sp = cmd
                    return if (cmd == "0100") {
                        if (sp == "ATSP3") "?\r\r>" else "UNABLE TO CONNECT\r\r>"
                    } else "OK\r\r>"
                }
                override fun close() {}
            }
        }
        val job = launch { src.run() }
        advanceTimeBy(100)
        val st = src.state.value as ObdState.Retrying
        assertTrue(st.error.startsWith("init error"))
        job.cancel()
    }

    @Test
    fun ioErrorDuringFirstCandidatePropagatesWithoutFallback() = runTest {
        val log = mutableListOf<String>()
        val src = sourceWith(MemStore()) { ScriptedTransport(log, failAfter = 8, lostMessage = "gone") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertEquals(1, log.count { it == "ATZ" })
        assertTrue((src.state.value as ObdState.Retrying).error.contains("gone"))
        job.cancel()
    }

    @Test
    fun firstPidSearchGetsThirtySeconds() = runTest {
        val timeouts = mutableMapOf<String, Long>()
        val src = source { ScriptedTransport(mutableListOf(), timeouts = timeouts) }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertEquals(30_000L, timeouts["0100"])
        job.cancel()
    }

    @Test
    fun emptyPidSearchIsInitFailure() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), on0100 = "\r\r>") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertTrue(src.state.value is ObdState.Retrying)
        assertTrue(events().none { it.event == Events.OBD_CONNECTED })
        advanceTimeBy(5_000 + 10_000 + 1_000)
        assertEquals(1, events().count { it.event == Events.OBD_ERROR })
        job.cancel()
    }

    @Test
    fun busInitErrorIsInitFailure() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), on0100 = "BUS INIT: ...ERROR\r\r>") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertTrue(src.state.value is ObdState.Retrying)
        assertTrue(events().none { it.event == Events.OBD_CONNECTED })
        job.cancel()
    }

    @Test
    fun busInitUnableToConnectIsClassified() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), on0100 = "BUS INIT: UNABLE TO CONNECT\r\r>") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        val state = src.state.value as ObdState.Retrying
        assertEquals("UNABLE TO CONNECT", state.error)
        job.cancel()
    }

    @Test
    fun dtcScanWhileConnectedEmitsDtcThenEventAndDedupes() = runTest {
        val src = source { ScriptedTransport(mutableListOf()) }
        val job = launch { src.run() }
        advanceTimeBy(100)
        records.clear()
        src.requestDtcScan("x")
        advanceTimeBy(500)
        val relevant = records.filter { it is DtcRecord || (it is EventRecord && it.event == Events.DTC_SCAN) }
        assertEquals(2, relevant.size)
        val dtc = relevant[0] as DtcRecord
        assertEquals(listOf("P0133"), dtc.active)
        val ev = relevant[1] as EventRecord
        assertEquals("x", ev.detail)
        records.clear()
        src.requestDtcScan("x")
        advanceTimeBy(500)
        assertTrue(records.none { it is DtcRecord })
        assertTrue(events().isEmpty())
        job.cancel()
    }

    @Test
    fun dtcScanWhenNotConnectedEmitsFailureImmediately() = runTest {
        val src = source { ScriptedTransport(mutableListOf()) }
        src.requestDtcScan("x")
        val ev = events().single()
        assertEquals(Events.DTC_SCAN_FAILED, ev.event)
        assertEquals("x obd_not_connected", ev.detail)
        src.requestDtcScan("x")
        assertEquals(1, events().size)
    }

    @Test
    fun dtcScanFailingMidReadEmitsObdError() = runTest {
        val transport = ScriptedTransport(mutableListOf())
        val src = source { transport }
        val job = launch { src.run() }
        advanceTimeBy(100)
        transport.failOn03 = true
        src.requestDtcScan("x")
        advanceTimeBy(500)
        val failed = events().filter { it.event == Events.DTC_SCAN_FAILED }
        assertEquals(listOf("x obd_error"), failed.map { it.detail })
        assertTrue(events().none { it.event == Events.DTC_SCAN })
        assertTrue(src.state.value is ObdState.Retrying)
        job.cancel()
    }

    @Test
    fun dtcScanWithElmErrorEmitsObdErrorAndKeepsLink() = runTest {
        val transport = ScriptedTransport(mutableListOf())
        val src = source { transport }
        val job = launch { src.run() }
        advanceTimeBy(100)
        val before = records.size
        transport.answer03 = "STOPPED\r\r>"
        src.requestDtcScan("x")
        advanceTimeBy(500)
        val after = records.drop(before)
        assertEquals(listOf("x obd_error"), events().filter { it.event == Events.DTC_SCAN_FAILED }.map { it.detail })
        assertTrue(events().none { it.event == Events.DTC_SCAN })
        assertTrue(after.none { it is DtcRecord })
        assertTrue(src.state.value is ObdState.Connected)
        job.cancel()
    }

    @Test
    fun dtcScanWithNoDataIsAValidEmptyScan() = runTest {
        val transport = ScriptedTransport(mutableListOf())
        val src = source { transport }
        val job = launch { src.run() }
        advanceTimeBy(100)
        transport.answer03 = "NO DATA\r\r>"
        src.requestDtcScan("x")
        advanceTimeBy(500)
        assertEquals(listOf("x"), events().filter { it.event == Events.DTC_SCAN }.map { it.detail })
        job.cancel()
    }

    @Test
    fun sharedHandledIdsAreNotAnsweredTwice() = runTest {
        val shared: MutableSet<String> = java.util.concurrent.ConcurrentHashMap.newKeySet()
        val a = ObdSource({ ScriptedTransport(mutableListOf()) }, FakeClocks(), { r, _ -> records += r }, { session }, { currentTime }, handledScans = shared)
        val b = ObdSource({ ScriptedTransport(mutableListOf()) }, FakeClocks(), { r, _ -> records += r }, { session }, { currentTime }, handledScans = shared)
        a.requestDtcScan("x")
        b.requestDtcScan("x")
        assertEquals(1, events().count { it.event == Events.DTC_SCAN_FAILED })
    }

    private val engineOff = "41 0C 00 00\r\r>"

    private fun TestScope.connectedStopped(configure: (ScriptedTransport) -> Unit = {}): Triple<ObdSource, ScriptedTransport, kotlinx.coroutines.Job> {
        val transport = ScriptedTransport(mutableListOf())
        transport.rpmAnswer = engineOff
        configure(transport)
        val src = source { transport }
        val job = launch { src.run() }
        return Triple(src, transport, job)
    }

    private fun clearFailures() = events().filter { it.event == Events.DTC_CLEAR_FAILED }.map { it.detail }

    @Test
    fun dtcClearAcceptedRereadsThenEmitsEvent() = runTest {
        val (src, transport, job) = connectedStopped()
        advanceTimeBy(100)
        records.clear()
        src.requestDtcClear("x")
        advanceTimeBy(500)
        val relevant = records.filter { it is DtcRecord || (it is EventRecord && it.event == Events.DTC_CLEAR) }
        assertEquals(2, relevant.size)
        assertTrue(relevant[0] is DtcRecord)
        assertEquals("x", (relevant[1] as EventRecord).detail)
        assertEquals(session.id, (relevant[0] as DtcRecord).session_id)
        assertEquals(10_000L, transport.timeouts["04"])
        assertTrue(clearFailures().isEmpty())
        job.cancel()
    }

    @Test
    fun dtcClearNegativeResponseIsRejected() = runTest {
        val (src, _, job) = connectedStopped { it.answer04 = "7F 04 22\r\r>" }
        advanceTimeBy(100)
        src.requestDtcClear("x")
        advanceTimeBy(500)
        assertEquals(listOf("x rejected"), clearFailures())
        assertTrue(events().none { it.event == Events.DTC_CLEAR })
        job.cancel()
    }

    @Test
    fun dtcClearElmErrorIsRejected() = runTest {
        val (src, _, job) = connectedStopped { it.answer04 = "?\r\r>" }
        advanceTimeBy(100)
        src.requestDtcClear("x")
        advanceTimeBy(500)
        assertEquals(listOf("x rejected"), clearFailures())
        assertTrue(events().none { it.event == Events.DTC_CLEAR })
        job.cancel()
    }

    @Test
    fun dtcClearWithEngineRunningNeverSendsMode04() = runTest {
        val log = mutableListOf<String>()
        val transport = ScriptedTransport(log)
        val src = source { transport }
        val job = launch { src.run() }
        advanceTimeBy(100)
        src.requestDtcClear("x")
        advanceTimeBy(500)
        assertEquals(listOf("x engine_running"), clearFailures())
        assertFalse("04" in log)
        assertTrue(events().none { it.event == Events.DTC_CLEAR })
        job.cancel()
    }

    @Test
    fun dtcClearWhenNotConnectedEmitsFailureImmediately() = runTest {
        val src = source { ScriptedTransport(mutableListOf()) }
        src.requestDtcClear("x")
        assertEquals(listOf("x obd_not_connected"), clearFailures())
        src.requestDtcClear("x")
        assertEquals(1, events().size)
    }

    @Test
    fun dtcClearLinkFailureEmitsObdErrorAndDropsLink() = runTest {
        val (src, transport, job) = connectedStopped()
        advanceTimeBy(100)
        transport.failOn04 = true
        src.requestDtcClear("x")
        advanceTimeBy(500)
        assertEquals(listOf("x obd_error"), clearFailures())
        assertTrue(src.state.value is ObdState.Retrying)
        job.cancel()
    }

    @Test
    fun dtcClearRereadErrorStillEmitsEventWithoutDtcRecord() = runTest {
        val (src, transport, job) = connectedStopped()
        advanceTimeBy(100)
        records.clear()
        transport.answer03 = "STOPPED\r\r>"
        src.requestDtcClear("x")
        advanceTimeBy(500)
        assertEquals(listOf("x"), events().filter { it.event == Events.DTC_CLEAR }.map { it.detail })
        assertTrue(records.none { it is DtcRecord })
        job.cancel()
    }

    @Test
    fun dtcClearSameIdTwiceIsHandledOnce() = runTest {
        val (src, _, job) = connectedStopped()
        advanceTimeBy(100)
        records.clear()
        src.requestDtcClear("x")
        src.requestDtcClear("x")
        advanceTimeBy(500)
        assertEquals(1, events().count { it.event == Events.DTC_CLEAR })
        job.cancel()
    }

    @Test
    fun clearAndScanWithDifferentIdsAreBothHandled() = runTest {
        val (src, _, job) = connectedStopped()
        advanceTimeBy(100)
        records.clear()
        src.requestDtcClear("c")
        src.requestDtcScan("s")
        advanceTimeBy(500)
        assertEquals(listOf("c"), events().filter { it.event == Events.DTC_CLEAR }.map { it.detail })
        assertEquals(listOf("s"), events().filter { it.event == Events.DTC_SCAN }.map { it.detail })
        job.cancel()
    }

    @Test
    fun dtcClearReadsRpmFreshAndRefusesWhenRunning() = runTest {
        val log = mutableListOf<String>()
        val transport = ScriptedTransport(log)
        transport.rpmAnswer = engineOff
        val src = source { transport }
        val job = launch { src.run() }
        advanceTimeBy(100)
        transport.rpmAnswer = "41 0C 0C 80\r\r>" // started after the last poll sample
        src.requestDtcClear("x")
        advanceTimeBy(500)
        assertEquals(listOf("x engine_running"), clearFailures())
        assertFalse("04" in log)
        job.cancel()
    }

    @Test
    fun dtcClearWithoutRpmValueIsObdErrorAndNeverSends04() = runTest {
        val log = mutableListOf<String>()
        val transport = ScriptedTransport(log)
        transport.rpmAnswer = "NO DATA\r\r>"
        val src = source { transport }
        val job = launch { src.run() }
        advanceTimeBy(100)
        src.requestDtcClear("x")
        advanceTimeBy(500)
        assertEquals(listOf("x obd_error"), clearFailures())
        assertFalse("04" in log)
        assertTrue(src.state.value is ObdState.Connected)
        job.cancel()
    }

    @Test
    fun dtcClearWithRpmZeroSends04() = runTest {
        val log = mutableListOf<String>()
        val transport = ScriptedTransport(log)
        transport.rpmAnswer = engineOff
        val src = source { transport }
        val job = launch { src.run() }
        advanceTimeBy(100)
        src.requestDtcClear("x")
        advanceTimeBy(500)
        assertTrue("04" in log)
        assertEquals(1, events().count { it.event == Events.DTC_CLEAR })
        job.cancel()
    }

    @Test
    fun queuedClearIsFailedWhenLinkDropsBeforeItRuns() = runTest {
        val (src, transport, job) = connectedStopped()
        advanceTimeBy(100)
        transport.failOn04 = true
        src.requestDtcClear("a")
        src.requestDtcClear("b")
        advanceTimeBy(500)
        assertEquals(listOf("a obd_error", "b obd_not_connected"), clearFailures())
        job.cancel()
    }

    @Test
    fun eventDetailTruncatedTo200() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), failAfter = 20, lostMessage = "x".repeat(500)) }
        val job = launch { src.run() }
        advanceTimeBy(500)
        val lost = events().first { it.event == Events.OBD_LOST }
        assertEquals(200, lost.detail!!.length)
        job.cancel()
    }

    // ---- probe, variants and trace (app 0.1.7) ----

    private fun TestScope.prefSource(pref: String, factory: () -> ElmTransport) = sourceWith(MemStore(), pref, factory)

    @Test
    fun probeRunsBeforeAtz() = runTest {
        val log = mutableListOf<String>()
        val src = source { ScriptedTransport(log) }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertEquals(listOf("ATI", "AT@1", "ATDP", "ATDPN", "ATRV", "ATPPS", "ATZ"), log.take(7))
        job.cancel()
    }

    @Test
    fun probeUsesTwoSecondTimeout() = runTest {
        val timeouts = mutableMapOf<String, Long>()
        val src = source { ScriptedTransport(mutableListOf(), timeouts = timeouts) }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertEquals(2_000L, timeouts["ATI"])
        assertEquals(2_000L, timeouts["ATPPS"])
        job.cancel()
    }

    @Test
    fun atppsOnlyOnFirstAttempt() = runTest {
        val logs = mutableListOf<MutableList<String>>()
        val src = source {
            val l = mutableListOf<String>()
            logs += l
            ScriptedTransport(l, on0100 = "UNABLE TO CONNECT\r\r>")
        }
        val job = launch { src.run() }
        advanceTimeBy(5_100)
        assertTrue(logs.size >= 2)
        assertTrue(logs[0].contains("ATPPS"))
        assertFalse(logs[1].contains("ATPPS"))
        job.cancel()
    }

    @Test
    fun probe0100OnlyWhenProtocolFixed() = runTest {
        val auto = mutableListOf<String>()
        val fixed = mutableListOf<String>()
        var n = 0
        val src = source { if (n++ == 0) ScriptedTransport(auto, dpn = "A5", failAfter = 9) else ScriptedTransport(fixed, dpn = "5", failAfter = 9) }
        val job = launch { src.run() }
        advanceTimeBy(5_100)
        assertFalse(auto.take(7).contains("0100"))
        assertTrue(fixed.take(7).contains("0100"))
        job.cancel()
    }

    @Test
    fun probeFailureDoesNotAbortAttempt() = runTest {
        val log = mutableListOf<String>()
        val src = source {
            object : ElmTransport {
                val inner = ScriptedTransport(log)
                override suspend fun open() = inner.open()
                override suspend fun command(cmd: String, timeoutMs: Long): String {
                    if (cmd == "ATI" || cmd == "ATPPS") throw IOException("probe timeout")
                    return inner.command(cmd, timeoutMs)
                }
                override fun close() = inner.close()
            }
        }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertTrue(src.state.value is ObdState.Connected)
        assertTrue(log.contains("ATZ"))
        job.cancel()
    }

    @Test
    fun traceEmittedForFailedAndSuccessfulAttempts() = runTest {
        var n = 0
        val src = source { if (n++ == 0) ScriptedTransport(mutableListOf(), on0100 = "UNABLE TO CONNECT\r\r>") else ScriptedTransport(mutableListOf()) }
        val job = launch { src.run() }
        advanceTimeBy(5_100)
        val t = traces()
        assertTrue(t[0].lineSequence().first().let { it.startsWith("attempt n=1 variant=V1 session_age=0s") && it.contains("result=fail") })
        assertTrue(t[1].lineSequence().first().let { it.startsWith("attempt n=2 variant=V1") && it.contains("result=ok") })
        assertTrue(t[0].contains("> ATZ"))
        assertTrue(t[0].length <= 4000)
        job.cancel()
    }

    @Test
    fun gluedDataIsFlaggedInTraceHeader() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), on0100 = "BUS INIT: ...OK41 00 18 38 80 01\r\r>") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertTrue(traces().first().lineSequence().first().contains("glued=1"))
        job.cancel()
    }

    @Test
    fun attemptEventsCarryVariant() = runTest {
        var n = 0
        val src = prefSource("5") { if (n++ == 0) ScriptedTransport(mutableListOf(), dpn = "5", on0100 = "UNABLE TO CONNECT\r\r>") else ScriptedTransport(mutableListOf(), dpn = "5") }
        val job = launch { src.run() }
        advanceTimeBy(5_100)
        val v1 = variantFor("s1", 1)
        val v2 = variantFor("s1", 2)
        assertTrue(attempts().first().endsWith(" var=$v1"))
        assertTrue(events().first { it.event == Events.OBD_CONNECTED }.detail!!.endsWith(" var=$v2"))
        assertTrue(traces()[0].startsWith("attempt n=1 variant=$v1"))
        job.cancel()
    }

    @Test
    fun longAttemptDetailKeepsVariantWithin200() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), on0100 = "7F0112".repeat(30) + "\r\r>") }
        val job = launch { src.run() }
        advanceTimeBy(100)
        val d = attempts().first()
        assertEquals(200, d.length)
        assertTrue(d.endsWith(" var=V1"))
        job.cancel()
    }

    @Test
    fun lostEmitsTraceBeforeObdLost() = runTest {
        val src = source { ScriptedTransport(mutableListOf(), failAfter = 30, lostMessage = "link lost") }
        val job = launch { src.run() }
        advanceTimeBy(500)
        val all = records.filterIsInstance<EventRecord>().map { it.event }
        val lostIdx = all.indexOf(Events.OBD_LOST)
        assertEquals(Events.OBD_TRACE, all[lostIdx - 1])
        val trace = traces().last()
        assertEquals("lost", trace.lineSequence().first())
        assertTrue(trace.lines().size - 1 <= 20)
        assertTrue(trace.contains("ERR link lost"))
        job.cancel()
    }

    @Test
    fun variantV5SendsPhysicalHeaderAfterFastInit() = runTest {
        val sid = (1..200).map { "sess$it" }.first { variantFor(it, 1) == InitVariant.V5 }
        val log = mutableListOf<String>()
        val src = ObdSource(
            transportFactory = { ScriptedTransport(log, dpn = "5") },
            clocks = FakeClocks(),
            emit = { r, _ -> records += r },
            sessionProvider = { Session(sid) },
            nowMs = { currentTime },
            protocolPreference = "5",
            delayFn = {},
        )
        val job = launch { src.run() }
        advanceTimeBy(100)
        val fi = log.indexOf("ATFI")
        assertTrue(fi > 0)
        assertEquals("ATSH 81 10 F1", log[fi + 1])
        assertEquals("0100", log[fi + 2])
        job.cancel()
    }

    @Test
    fun atfiErrorFailsTheAttempt() = runTest {
        val sid = (1..200).map { "sess$it" }.first { variantFor(it, 1) == InitVariant.V2 }
        val log = mutableListOf<String>()
        val src = ObdSource(
            transportFactory = {
                object : ElmTransport {
                    val inner = ScriptedTransport(log, dpn = "5")
                    override suspend fun open() = inner.open()
                    override suspend fun command(cmd: String, timeoutMs: Long) =
                        if (cmd == "ATFI") "BUS INIT: ...ERROR\r\r>" else inner.command(cmd, timeoutMs)
                    override fun close() = inner.close()
                }
            },
            clocks = FakeClocks(),
            emit = { r, _ -> records += r },
            sessionProvider = { Session(sid) },
            nowMs = { currentTime },
            protocolPreference = "5",
            delayFn = {},
        )
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertTrue(attempts().first().contains("5: BUS INIT ERROR"))
        assertTrue(traces().first().contains("result=fail"))
        job.cancel()
    }
}
