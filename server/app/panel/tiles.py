"""OSM tiles served through the API so the browser never contacts OSM directly."""
import threading

from fastapi import APIRouter, HTTPException, Response

from app.tiles import TileCache

MAX_ZOOM = 19
CACHE_CONTROL = "public, max-age=604800"


def tiles_router(cache: TileCache) -> APIRouter:
    router = APIRouter()
    lock = threading.Lock()

    @router.get("/tiles/{z}/{x}/{y}.png")
    def tile(z: int, x: int, y: int) -> Response:
        if not (0 <= z <= MAX_ZOOM and 0 <= x < 2**z and 0 <= y < 2**z):
            raise HTTPException(status_code=400, detail="tile out of range")
        with lock:
            data = cache.fetch(z, x, y)
        if data is None:
            raise HTTPException(status_code=503, detail="tile unavailable")
        return Response(content=data, media_type="image/png",
                        headers={"Cache-Control": CACHE_CONTROL})

    return router
