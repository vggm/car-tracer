package dev.lnk.cartrace.obd

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CancelDiscoveryBestEffortTest {
    @Test
    fun `swallows SecurityException when scan permission is missing`() {
        val ok = cancelDiscoveryBestEffort { throw SecurityException("need BLUETOOTH_SCAN") }
        assertFalse(ok)
    }

    @Test
    fun `invokes cancel and reports success`() {
        var calls = 0
        val ok = cancelDiscoveryBestEffort { calls++; true }
        assertTrue(ok)
        assertEquals(1, calls)
    }

    @Test(expected = IllegalStateException::class)
    fun `does not swallow other exceptions`() {
        cancelDiscoveryBestEffort { throw IllegalStateException("boom") }
    }
}
