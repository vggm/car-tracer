INGEST_PATH = "/api/v1/ingest"


class FunnelGuardMiddleware:
    """Reject anything but the ingest route when the request came via Tailscale
    serve/Funnel (which always adds X-Forwarded-Host)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") != INGEST_PATH:
            if any(name == b"x-forwarded-host" for name, _ in scope.get("headers", [])):
                body = b'{"error":"not found"}'
                await send({
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
