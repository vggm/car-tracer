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
) : ElmTransport {
    var closed = false
    private var count = 0
    override suspend fun open() { openError?.let { throw it } }
    override suspend fun command(cmd: String, timeoutMs: Long): String {
        if (count++ >= failAfter) throw IOException("link lost")
        log += cmd
        return when (cmd) {
            "ATZ" -> "ELM327 v1.5\r\r>"
            "ATDPN" -> "A6\r\r>"
            "0100" -> on0100
            "0120" -> MASK_0120
            "0140" -> MASK_0140
            "03" -> "43 01 33 00 00 00 00\r\r>"
            "07" -> "47 02 00 00 00 00 00\r\r>"
            "ATRV" -> "12.6V\r\r>"
            "010C" -> "41 0C 1A F8\r\r>"
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
    )

    private fun events() = records.filterIsInstance<EventRecord>()

    @Test
    fun initSequenceAndConnectedEvent() = runTest {
        val log = mutableListOf<String>()
        val src = source { ScriptedTransport(log) }
        val job = launch { src.run() }
        advanceTimeBy(100)
        assertEquals(
            listOf("ATZ", "ATE0", "ATL0", "ATS0", "ATH0", "ATSP0", "0100", "0120", "0140", "ATDPN"),
            log.take(10),
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
        assertEquals(3, log.count { it == "ATRV" })
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
        assertEquals(listOf(Events.OBD_CONNECTED, Events.OBD_LOST), events().map { it.event })
        val first = src.state.value as ObdState.Retrying
        assertEquals(5_000L, first.nextInMs)
        advanceTimeBy(5_100)
        assertEquals(10_000L, (src.state.value as ObdState.Retrying).nextInMs)
        // never connected again: no extra obd_lost
        assertEquals(2, events().size)
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
        assertTrue(events().isEmpty())
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
}
