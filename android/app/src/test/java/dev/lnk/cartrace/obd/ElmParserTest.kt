package dev.lnk.cartrace.obd

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ElmParserTest {
    @Test fun rpm() = assertEquals(1726.0, ElmParser.value(Pid.RPM, "41 0C 1A F8")!!, 0.001)
    @Test fun speed() = assertEquals(50.0, ElmParser.value(Pid.SPEED, "410D32")!!, 0.001)
    @Test fun coolant() = assertEquals(83.0, ElmParser.value(Pid.COOLANT, "41 05 7B")!!, 0.001)
    @Test fun otherFormulas() {
        assertEquals(100.0, ElmParser.value(Pid.LOAD, "4104FF")!!, 0.001)
        assertEquals(100.0, ElmParser.value(Pid.THROTTLE, "4111FF")!!, 0.001)
        assertEquals(101.0, ElmParser.value(Pid.INTAKE, "410B65")!!, 0.001)
        assertEquals(1.0, ElmParser.value(Pid.FUEL_RATE, "415E0014")!!, 0.001)
    }

    @Test fun supportedPids() {
        val s = ElmParser.supportedPids(listOf("41 00 BE 3E B8 13"))
        assertTrue("010C" in s)
        assertTrue("010D" in s)
        assertTrue("0101" in s)
        assertFalse("0102" in s)
        assertTrue("0120" in s)
    }

    @Test fun supportedPidsRelativeToBase() {
        val s = ElmParser.supportedPids(listOf("4120 80000000", "SEARCHING...\r41 40 00 00 00 01\r>"))
        assertEquals(setOf("0121", "0160"), s)
    }

    @Test fun dtcP0133() = assertEquals(listOf("P0133"), ElmParser.dtcs("43 01 33 00 00 00 00", '3'))
    @Test fun dtcC() = assertTrue(ElmParser.dtcs("43 41 23 00 00 00 00", '3').first().startsWith("C"))
    @Test fun dtcLetters() =
        assertEquals(listOf("B0123", "U0123"), ElmParser.dtcs("4381230000\r43C123", '3'))
    @Test fun dtcMultiLineMode7() =
        assertEquals(listOf("P0133", "P0204"), ElmParser.dtcs("47 01 33 00 00\r47 02 04 00 00\r>", '7'))
    @Test fun dtcNoCodes() = assertEquals(emptyList<String>(), ElmParser.dtcs("43 00 00 00 00 00 00", '3'))
    @Test fun dtcGarbage() {
        assertEquals(emptyList<String>(), ElmParser.dtcs("NO DATA", '3'))
        assertEquals(emptyList<String>(), ElmParser.dtcs("", '3'))
        assertEquals(emptyList<String>(), ElmParser.dtcs("43 01 33", 'x'))
        assertEquals(emptyList<String>(), ElmParser.dtcs("43 ZZ 33", '3'))
    }

    @Test fun voltage() = assertEquals(12.6, ElmParser.voltage("12.6V")!!, 0.001)
    @Test fun voltageNoise() {
        assertEquals(12.6, ElmParser.voltage("ATRV\r12.6V\r\r>")!!, 0.001)
        assertNull(ElmParser.voltage("?"))
    }

    @Test fun noisyResponses() {
        val ok = mapOf(
            "SEARCHING...\r41 0C 1A F8\r\r>" to 1726.0,
            "BUS INIT: ...OK\r41 0D 00" to 0.0,
        )
        assertEquals(1726.0, ElmParser.value(Pid.RPM, "SEARCHING...\r41 0C 1A F8\r\r>")!!, 0.001)
        assertEquals(0.0, ElmParser.value(Pid.SPEED, "BUS INIT: ...OK\r41 0D 00")!!, 0.001)
        assertEquals(1726.0, ElmParser.value(Pid.RPM, "010C\r\n410C1AF8\r\n\r\n>")!!, 0.001)
        assertEquals(2, ok.size)
        for (raw in listOf("NO DATA", "?", "UNABLE TO CONNECT", "", "41 0C 1A", "41 0C 1A ZZ", ">", "41")) {
            assertNull(raw, ElmParser.value(Pid.RPM, raw))
        }
        assertNull(ElmParser.value(Pid.SPEED, "41 0C 1A F8"))
    }

    @Test fun multiEcuLinesTakesFirstValid() {
        assertEquals(1726.0, ElmParser.value(Pid.RPM, "41 0C 1A\r41 0C 1A F8\r41 0C 00 00")!!, 0.001)
        assertEquals(50.0, ElmParser.value(Pid.SPEED, "NO DATA\r410D32\r410D64")!!, 0.001)
    }

    @Test fun isError() {
        for (e in listOf("NO DATA", "UNABLE TO CONNECT", "?", "STOPPED", "CAN ERROR", "BUS ERROR", "ERROR", "\rNO DATA\r\r>")) {
            assertTrue(e, ElmParser.isError(e))
        }
        assertFalse(ElmParser.isError("41 0C 1A F8"))
        assertFalse(ElmParser.isError(""))
    }

    @Test fun cleanStripsNoise() {
        assertEquals(
            listOf("410C1AF8"),
            ElmParser.clean("SEARCHING...\rBUS INIT: ...OK\r41 0C 1A F8\r\r>"),
        )
    }

    @Test fun busInitErrorIsError() {
        assertTrue(ElmParser.isError("BUS INIT: ...ERROR\r\r>"))
        assertTrue(ElmParser.isError("BUS INIT: ERROR"))
        assertTrue(ElmParser.isError("BUS INIT: UNABLE TO CONNECT\r\r>"))
        assertTrue(ElmParser.isUnableToConnect("BUS INIT: UNABLE TO CONNECT\r\r>"))
        assertTrue(ElmParser.isUnableToConnect("UNABLE TO CONNECT\r\r>"))
        assertFalse(ElmParser.isUnableToConnect("BUS INIT: ...OK\r41 00 BE 3E B8 13\r\r>"))
        assertFalse(ElmParser.isError("BUS INIT: ...OK\r41 00 BE 3E B8 13\r\r>"))
    }

    @Test fun gluedDataAfterBusInitOkIsKept() {
        assertTrue(ElmParser.supportedPids(listOf("BUS INIT: ...OK41 00 BE 3E B8 13\r\r>")).isNotEmpty())
        assertEquals(listOf("4100BE3EB813"), ElmParser.clean("BUS INIT: ...OK41 00 BE 3E B8 13\r\r>"))
    }

    @Test fun fastInitOkWithoutDotsIsNoise() {
        assertEquals(listOf("4100BE3EB813"), ElmParser.clean("BUS INIT: OK\r41 00 BE 3E B8 13\r\r>"))
    }

    @Test fun hasGluedDataDetectsGluedLines() {
        assertTrue(ElmParser.hasGluedData("BUS INIT: ...OK41 00 BE 3E B8 13\r\r>"))
        assertFalse(ElmParser.hasGluedData("BUS INIT: ...OK\r41 00 BE 3E B8 13\r\r>"))
        assertFalse(ElmParser.hasGluedData("BUS INIT: OK\r41 00\r\r>"))
    }

    @Test fun gluedDataAfterDotlessFastInitIsKept() {
        val raw = "BUS INIT: OK41 00 BE 3E B8 13\r\r>"
        assertEquals(listOf("4100BE3EB813"), ElmParser.clean(raw))
        assertTrue(ElmParser.supportedPids(listOf(raw)).isNotEmpty())
        assertTrue(ElmParser.hasGluedData(raw))
        assertFalse(ElmParser.isError(raw))
    }

    @Test fun gluedDataWithoutOkIsKeptRealTrace() {
        val raw = "BUS INIT:4100983B4011\r\r>"
        assertEquals(listOf("4100983B4011"), ElmParser.clean(raw))
        assertTrue(ElmParser.supportedPids(listOf(raw)).isNotEmpty())
        assertTrue(ElmParser.hasGluedData(raw))
        assertFalse(ElmParser.isError(raw))
    }

    @Test fun busInitWithHeadersGluedIsKept() {
        val raw = "BUS INIT:86F1104100983B4011EC\r\n\r\n>"
        assertEquals(listOf("86F1104100983B4011EC"), ElmParser.clean(raw))
        assertFalse(ElmParser.isError(raw))
    }

    @Test fun busInitErrorsAndBareOkAreNotData() {
        for (raw in listOf(
            "BUS INIT:UNABLE TO CONNECT\r>",
            "BUS INIT: ...ERROR\r>",
            "BUS INIT: OK\r>",
            "BUS INIT: ...OK\r>",
        )) {
            assertEquals(raw, emptyList<String>(), ElmParser.clean(raw))
            assertFalse(raw, ElmParser.hasGluedData(raw))
        }
        assertTrue(ElmParser.isError("BUS INIT:UNABLE TO CONNECT\r>"))
        assertTrue(ElmParser.isError("BUS INIT: ...ERROR\r>"))
        assertFalse(ElmParser.isError("BUS INIT: OK\r>"))
    }
}
