package dev.lnk.cartrace.panel

import java.net.URI

/** Pure URL decisions for the WebView, kept free of Android types so they are unit-testable. */
object PanelLinks {
    const val RETRY_URL = "cartrace://retry"

    fun isRetry(url: String): Boolean = url == RETRY_URL

    /** True when [url] has the same scheme, host and port as [panelUrl]. */
    fun isInternal(url: String, panelUrl: String): Boolean {
        val target = origin(url) ?: return false
        val panel = origin(panelUrl) ?: return false
        return target == panel
    }

    private fun origin(url: String): Triple<String, String, Int>? = try {
        val uri = URI(url)
        val scheme = uri.scheme?.lowercase()
        val host = uri.host?.lowercase()
        if (scheme == null || host == null) {
            null
        } else {
            val port = if (uri.port != -1) uri.port else when (scheme) {
                "http" -> 80
                "https" -> 443
                else -> -1
            }
            Triple(scheme, host, port)
        }
    } catch (e: java.net.URISyntaxException) {
        null
    }
}
