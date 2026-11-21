import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.db import connect
from app.funnel_guard import FunnelGuardMiddleware
from app.ingest import router
from app.panel.api import router as panel_router
from app.panel.tiles import tiles_router
from app.tiles import TileCache
from app.trip_cache import TripCache

WEB_DIR = Path(__file__).parent / "web"


def now_ms() -> int:
    return int(time.time() * 1000)


def create_app(
    settings: Settings,
    clock: Callable[[], int] = now_ms,
    http: httpx.Client | None = None,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.clock = clock
    app.state.db = connect(settings.db_path)
    app.add_middleware(FunnelGuardMiddleware)
    app.state.trip_cache = TripCache()
    app.include_router(router)
    app.include_router(panel_router)
    tile_dir = Path(os.environ.get("CAR_TRACE_TILE_DIR")
                    or Path(settings.db_path).parent / "tiles")
    tile_dir.mkdir(parents=True, exist_ok=True)
    app.include_router(tiles_router(TileCache(tile_dir, http or httpx.Client())))
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app
