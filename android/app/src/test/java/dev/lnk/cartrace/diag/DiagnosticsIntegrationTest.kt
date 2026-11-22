package dev.lnk.cartrace.diag

import dev.lnk.cartrace.contract.ContractJson
import dev.lnk.cartrace.contract.EventRecord
import dev.lnk.cartrace.contract.Events
import dev.lnk.cartrace.contract.HealthRecord
import dev.lnk.cartrace.contract.Record
import dev.lnk.cartrace.core.FakeClocks
import dev.lnk.cartrace.core.Session
import dev.lnk.cartrace.obd.ObdSource
import dev.lnk.cartrace.obd.ObdState
import dev.lnk.cartrace.sim.FakeElmTransport
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** ObdSource + TraceRecorder + Diagnostics + health, wired like the service does, with fakes. */
@OptIn(ExperimentalCoroutinesApi::class)
class DiagnosticsIntegrationTest {
    @Test
    fun obdTraceDiagAndHealthAreEmittedAndSerializable() = runTest {
        val records = mutableListOf<Record>()
        val session = Session("s1")
        val diag = Diagnostics(
            nowMs = { currentTime },
            emit = { _, text -> records += EventRecord("d${records.size}", session.id, session.nextSeq(), 0, Events.DIAG, text) },
        )
        val src = ObdSource(
            transportFactory = { FakeElmTransport { currentTime } },
            clocks = FakeClocks(),
            emit = { r, _ -> records += r },
            sessionProvider = { session },
            nowMs = { currentTime },
            delayFn = {},
        )
        val job = launch { src.run() }
        advanceTimeBy(1_000)
        assertTrue(src.state.value is ObdState.Connected)

        diag.report("gps.no_fix", "no GPS fix for more than 120 s at AA:BB:CC:DD:EE:FF")
        val values = healthValues(
            HealthInputs(queuePending = 3, uploadFailures = 0, obdState = obdStateCode(src.state.value), serviceUptimeS = 12),
        )
        records += HealthRecord("h1", session.id, session.nextSeq(), 0, values)

        val events = records.filterIsInstance<EventRecord>().map { it.event }
        assertTrue(Events.OBD_TRACE in events)
        assertTrue(Events.DIAG in events)
        val health = records.filterIsInstance<HealthRecord>().single()
        assertEquals(2.0, health.values["obd_state"]!!, 0.0)
        for (r in records) {
            val json = ContractJson.encodeToString(Record.serializer(), r)
            assertEquals(r, ContractJson.decodeFromString(Record.serializer(), json))
        }
        val diagText = records.filterIsInstance<EventRecord>().first { it.event == Events.DIAG }.detail!!
        assertTrue(diagText.startsWith("gps.no_fix "))
        assertTrue("<mac>" in diagText)
        job.cancel()
    }
}
