package dev.lnk.cartrace.ui

import dev.lnk.cartrace.upload.UploadOutcome
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PermissionsTest {
    private val all = setOf(
        Permissions.FINE_LOCATION, Permissions.BACKGROUND_LOCATION,
        Permissions.BLUETOOTH_CONNECT, Permissions.POST_NOTIFICATIONS, Permissions.AUTOSTART_SEEN,
    )

    @Test fun orderIsFineThenBackground() {
        assertEquals(OnboardingStep.FINE_LOCATION, Permissions.nextStep(emptySet(), false))
        assertEquals(
            OnboardingStep.BACKGROUND_LOCATION,
            Permissions.nextStep(setOf(Permissions.FINE_LOCATION), false),
        )
        assertEquals(
            OnboardingStep.BLUETOOTH_CONNECT,
            Permissions.nextStep(setOf(Permissions.FINE_LOCATION, Permissions.BACKGROUND_LOCATION), false),
        )
    }

    @Test fun skipsGranted() {
        assertEquals(OnboardingStep.BATTERY, Permissions.nextStep(all - Permissions.AUTOSTART_SEEN, false))
        assertEquals(OnboardingStep.AUTOSTART_INFO, Permissions.nextStep(all - Permissions.AUTOSTART_SEEN, true))
        assertEquals(
            OnboardingStep.POST_NOTIFICATIONS,
            Permissions.nextStep(all - Permissions.POST_NOTIFICATIONS - Permissions.AUTOSTART_SEEN, true),
        )
    }

    @Test fun doneWhenAllGranted() {
        assertNull(Permissions.nextStep(all, true))
    }

    @Test fun outcomeTexts() {
        assertEquals("Enviado", Formatters.outcome(UploadOutcome.Sent(1, 0, 0)))
        assertEquals("Descartado", Formatters.outcome(UploadOutcome.Discarded(400)))
        assertEquals("Token incorrecto", Formatters.outcome(UploadOutcome.Unauthorized))
        assertEquals("Reintentando: timeout", Formatters.outcome(UploadOutcome.Retry("timeout")))
        assertEquals("Sin datos", Formatters.outcome(UploadOutcome.Idle))
    }

    @Test fun urlValidation() {
        assertTrue(Formatters.isValidUrl("https://a.b/ingest"))
        assertTrue(Formatters.isValidUrl(" http://10.0.0.1:8000 "))
        assertFalse(Formatters.isValidUrl("ftp://x"))
        assertFalse(Formatters.isValidUrl("https://"))
        assertFalse(Formatters.isValidUrl(""))
    }
}
