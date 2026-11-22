package dev.lnk.cartrace.sim

import dev.lnk.cartrace.obd.ElmParser
import kotlinx.coroutines.test.runTest
import dev.lnk.cartrace.contract.Events
import dev.lnk.cartrace.contract.EventRecord
import dev.lnk.cartrace.contract.Record
import dev.lnk.cartrace.core.FakeClocks
import dev.lnk.cartrace.core.Session
import dev.lnk.cartrace.obd.InitVariant
import dev.lnk.cartrace.obd.ObdSource
import dev.lnk.cartrace.obd.ObdState
import dev.lnk.cartrace.obd.variantFor
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.currentTime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Locale

@OptIn(ExperimentalCoroutinesApi::class)
class FakeElmTransportTest {
    @Test
    fun everyKwpVariantConnectsThroughObdSource() = runTest {
        for (v in InitVariant.entries) {
            val sid = (1..500).map { "f$it" }.first { variantFor(it, 1) == v }
            val records = mutableListOf<Record>()
            val src = ObdSource(
                transportFactory = { FakeElmTransport(nowMs = { currentTime }) },
                clocks = FakeClocks(),
                emit = { r, _ -> records += r },
                sessionProvider = { Session(sid) },
                nowMs = { currentTime },
                protocolPreference = "5",
                delayFn = {},
            )
            val job = launch { src.run() }
            advanceTimeBy(200)
            assertTrue("variant $v", src.state.value is ObdState.Connected)
            val connected = records.filterIsInstance<EventRecord>().first { it.event == Events.OBD_CONNECTED }
            assertTrue(connected.detail!!.endsWith(" var=$v"))
            job.cancel()
        }
    }

    @Test
    fun voltageIsLocaleIndependent() = runTest {
        val old = Locale.getDefault()
        Locale.setDefault(Locale("es", "ES"))
        try {
            val t = FakeElmTransport(nowMs = { 0L })
            t.open()
            val v = ElmParser.voltage(t.command("ATRV"))
            assertEquals(13.6, v!!, 0.3)
        } finally {
            Locale.setDefault(old)
        }
    }
}
