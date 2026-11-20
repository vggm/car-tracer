package dev.lnk.cartrace.settings

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class AppSettingsTest {
    private fun settings() = AppSettings(
        ApplicationProvider.getApplicationContext<Context>().getSharedPreferences("t", Context.MODE_PRIVATE),
    )

    @Test
    fun obdProtocolDefaultsToAutomatic() {
        assertEquals("0", settings().obdProtocol)
        assertEquals("0", settings().snapshot().obdProtocol)
    }

    @Test
    fun obdProtocolIsStoredAndPublished() {
        val s = settings()
        s.obdProtocol = "5"
        assertEquals("5", s.snapshot().obdProtocol)
        assertEquals("5", s.changes.value.obdProtocol)
        assertEquals("5", settings().obdProtocol)
    }
}
