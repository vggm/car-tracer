package dev.lnk.cartrace.sim

import dev.lnk.cartrace.obd.ElmParser
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test
import java.util.Locale

class FakeElmTransportTest {
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
