package dev.lnk.cartrace.panel

import org.junit.Assert.assertTrue
import org.junit.Test

class OfflinePageTest {
    private val html = OfflinePage.html()

    @Test fun containsSpanishTexts() {
        assertTrue(html.contains("No se puede conectar con el panel"))
        assertTrue(html.contains("Comprueba que Tailscale está activo y vuelve a intentarlo."))
        assertTrue(html.contains("Reintentar"))
    }
    @Test fun retryButtonLinksToRetryUrl() {
        assertTrue(html.contains("href=\"${PanelLinks.RETRY_URL}\""))
        assertTrue(PanelLinks.isRetry(PanelLinks.RETRY_URL))
    }
    @Test fun usesBrandColors() {
        assertTrue(html.contains("#111315"))
        assertTrue(html.contains("#e8e6e3"))
        assertTrue(html.contains("#5cb8ff"))
    }
}
