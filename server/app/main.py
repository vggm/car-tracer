import time
from collections.abc import Callable

from fastapi import FastAPI

from app.config import Settings
from app.db import connect
from app.funnel_guard import FunnelGuardMiddleware
from app.ingest import router


def now_ms() -> int:
    return int(time.time() * 1000)


def create_app(settings: Settings, clock: Callable[[], int] = now_ms) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.clock = clock
    app.state.db = connect(settings.db_path)
    app.add_middleware(FunnelGuardMiddleware)
    app.include_router(router)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app
