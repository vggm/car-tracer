package dev.lnk.cartrace.panel

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PanelLinksTest {
    private val panel = "http://example.test:8090/"

    @Test fun sameOriginRootIsInternal() = assertTrue(PanelLinks.isInternal("http://example.test:8090/", panel))
    @Test fun sameOriginWithPathAndHashIsInternal() =
        assertTrue(PanelLinks.isInternal("http://example.test:8090/index.html#/trayectos/12?x=1", panel))
    @Test fun hostComparisonIsCaseInsensitive() =
        assertTrue(PanelLinks.isInternal("http://EXAMPLE.test:8090/a", panel))
    @Test fun differentPortIsExternal() = assertFalse(PanelLinks.isInternal("http://example.test:8091/", panel))
    @Test fun differentSchemeIsExternal() = assertFalse(PanelLinks.isInternal("https://example.test:8090/", panel))
    @Test fun differentHostIsExternal() = assertFalse(PanelLinks.isInternal("http://other.test:8090/", panel))
    @Test fun mailtoIsExternal() = assertFalse(PanelLinks.isInternal("mailto:a@b.c", panel))
    @Test fun geoIsExternal() = assertFalse(PanelLinks.isInternal("geo:40.4,-3.7?q=40.4,-3.7", panel))
    @Test fun googleMapsIsExternal() =
        assertFalse(PanelLinks.isInternal("https://www.google.com/maps/search/?api=1&query=1,2", panel))
    @Test fun malformedUrlIsExternal() = assertFalse(PanelLinks.isInternal("http://exa mple:80 /%%", panel))
    @Test fun malformedPanelUrlIsExternal() = assertFalse(PanelLinks.isInternal("http://example.test:8090/", "not a url"))
    @Test fun defaultPortsAreNormalized() {
        assertTrue(PanelLinks.isInternal("http://example.test/x", "http://example.test:80/"))
        assertFalse(PanelLinks.isInternal("http://example.test:8090/x", "http://example.test/"))
    }
    @Test fun retryUrlDetected() = assertTrue(PanelLinks.isRetry("cartrace://retry"))
    @Test fun otherUrlIsNotRetry() {
        assertFalse(PanelLinks.isRetry("http://example.test:8090/"))
        assertFalse(PanelLinks.isRetry("cartrace://other"))
    }
}
