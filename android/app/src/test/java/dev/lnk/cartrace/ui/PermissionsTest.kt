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
        assertEquals("Enviado · 1/0/0", Formatters.outcome(UploadOutcome.Sent(1, 0, 0)))
        assertEquals("Enviado · 2/1/3", Formatters.outcome(UploadOutcome.Sent(2, 1, 3, "bad ts")))
        assertEquals("Descartado", Formatters.outcome(UploadOutcome.Discarded(400)))
        assertEquals("Token incorrecto", Formatters.outcome(UploadOutcome.Unauthorized))
        assertEquals("Reintentando: timeout", Formatters.outcome(UploadOutcome.Retry("timeout")))
        assertEquals("Sin datos", Formatters.outcome(UploadOutcome.Idle))
    }

    @Test fun uploadErrorTexts() {
        assertEquals(null, Formatters.uploadError(UploadOutcome.Sent(1, 0, 0)))
        assertEquals(null, Formatters.uploadError(UploadOutcome.Idle))
        assertEquals(
            "Servidor rechazó 3 registros: ts out of range",
            Formatters.uploadError(UploadOutcome.Sent(5, 0, 3, "ts out of range")),
        )
        assertEquals("Servidor rechazó 1 registros", Formatters.uploadError(UploadOutcome.Sent(5, 0, 1)))
        assertEquals("Lote descartado (HTTP 400): bad json", Formatters.uploadError(UploadOutcome.Discarded(400, "bad json")))
        assertEquals("Lote descartado (HTTP 413)", Formatters.uploadError(UploadOutcome.Discarded(413)))
    }

    @Test fun urlValidation() {
        assertTrue(Formatters.isValidUrl("https://a.b/ingest"))
        assertTrue(Formatters.isValidUrl(" http://10.0.0.1:8000 "))
        assertFalse(Formatters.isValidUrl("ftp://x"))
        assertFalse(Formatters.isValidUrl("https://"))
        assertFalse(Formatters.isValidUrl(""))
    }

    @Test fun skippedOptionalStepsAreSkipped() {
        val base = all - Permissions.AUTOSTART_SEEN - Permissions.POST_NOTIFICATIONS
        assertEquals(OnboardingStep.POST_NOTIFICATIONS, Permissions.nextStep(base, false))
        assertEquals(
            OnboardingStep.BATTERY,
            Permissions.nextStep(base, false, setOf(OnboardingStep.POST_NOTIFICATIONS)),
        )
        assertEquals(
            OnboardingStep.AUTOSTART_INFO,
            Permissions.nextStep(base, false, setOf(OnboardingStep.POST_NOTIFICATIONS, OnboardingStep.BATTERY)),
        )
        assertNull(Permissions.nextStep(base, false, Permissions.SKIPPABLE))
    }

    @Test fun requiredStepsCannotBeSkipped() {
        assertEquals(OnboardingStep.FINE_LOCATION, Permissions.nextStep(emptySet(), false, OnboardingStep.entries.toSet()))
    }

    @Test fun serviceStartRequirements() {
        val loc = setOf(Permissions.FINE_LOCATION, Permissions.BACKGROUND_LOCATION)
        assertFalse(Permissions.canStartService(loc, false))
        assertTrue(Permissions.canStartService(loc, true))
        assertTrue(Permissions.canStartService(loc + Permissions.BLUETOOTH_CONNECT, false))
        assertFalse(Permissions.canStartService(setOf(Permissions.FINE_LOCATION), true))
    }

    @Test fun urlRejectsWhitespaceAndMissingHost() {
        assertFalse(Formatters.isValidUrl("https://a b/x"))
        assertFalse(Formatters.isValidUrl("http:///path"))
        assertFalse(Formatters.isValidUrl("https://:8000/x"))
        assertFalse(Formatters.isValidUrl("https:/host"))
        assertFalse(Formatters.isValidUrl("https://host\n/x"))
        assertTrue(Formatters.isValidUrl("https://example.com:8443/ingest?x=1"))
    }

    @Test fun bootCountFormatting() {
        assertEquals("42", Formatters.bootCount(42))
        assertEquals("1", Formatters.bootCount(1))
        assertEquals("desconocido (0)", Formatters.bootCount(0))
        assertEquals("desconocido (0)", Formatters.bootCount(-1))
        assertEquals("—", Formatters.bootCount(null))
        assertFalse(Formatters.isBootCountSuspicious(42))
        assertTrue(Formatters.isBootCountSuspicious(0))
        assertTrue(Formatters.isBootCountSuspicious(-3))
        assertFalse(Formatters.isBootCountSuspicious(null))
    }
}
