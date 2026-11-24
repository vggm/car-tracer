package dev.lnk.cartrace.panel

/** Inline HTML shown when the panel can't be reached. The button is a link intercepted natively. */
object OfflinePage {
    fun html(): String = """
        <!doctype html>
        <html lang="es">
        <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          html, body { height: 100%; margin: 0; }
          body {
            background: #111315; color: #e8e6e3;
            font-family: system-ui, sans-serif;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            text-align: center; padding: 0 24px; box-sizing: border-box;
          }
          h1 { font-size: 1.3rem; margin: 0 0 12px; }
          p { margin: 0 0 28px; opacity: 0.8; line-height: 1.4; }
          @media (prefers-color-scheme: light) {
            body { background: #f6f5f2; color: #1b1d1f; }
          }
          a.btn {
            background: #5cb8ff; color: #111315; text-decoration: none;
            font-weight: 600; padding: 12px 28px; border-radius: 999px;
          }
        </style>
        </head>
        <body>
          <h1>No se puede conectar con el panel</h1>
          <p>Comprueba que Tailscale está activo y vuelve a intentarlo.</p>
          <a class="btn" href="${PanelLinks.RETRY_URL}">Reintentar</a>
        </body>
        </html>
    """.trimIndent()
}
