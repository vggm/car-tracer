package dev.lnk.cartrace.panel

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback

class MainActivity : ComponentActivity() {
    private lateinit var webView: WebView

    private var errorPending = false
    private var showingOffline = false
    private var clearHistoryOnLoad = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        webView = WebView(this).apply {
            setBackgroundColor(getColor(R.color.panel_bg))
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            webViewClient = PanelClient()
        }
        setContentView(webView)

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (!showingOffline && webView.canGoBack()) {
                    webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        val restored = savedInstanceState?.let { webView.restoreState(it) }
        if (restored == null) webView.loadUrl(BuildConfig.PANEL_URL)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        webView.saveState(outState)
    }

    override fun onDestroy() {
        webView.destroy()
        super.onDestroy()
    }

    private fun retry() {
        showingOffline = false
        clearHistoryOnLoad = true
        webView.loadUrl(BuildConfig.PANEL_URL)
    }

    private inner class PanelClient : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val url = request.url.toString()
            if (PanelLinks.isRetry(url)) {
                retry()
                return true
            }
            if (PanelLinks.isInternal(url, BuildConfig.PANEL_URL)) return false
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
            } catch (_: ActivityNotFoundException) {
                // No app can handle it; ignore.
            }
            return true
        }

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (!request.isForMainFrame) return
            errorPending = true
            showingOffline = true
            view.loadDataWithBaseURL(null, OfflinePage.html(), "text/html", "utf-8", null)
        }

        override fun onPageFinished(view: WebView, url: String?) {
            when {
                url == "about:blank" -> {
                    showingOffline = true
                    errorPending = false
                }
                !errorPending && !showingOffline && clearHistoryOnLoad -> {
                    clearHistoryOnLoad = false
                    view.clearHistory()
                }
            }
        }
    }
}
