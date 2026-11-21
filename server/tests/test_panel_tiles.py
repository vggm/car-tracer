import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.panel.tiles import tiles_router
from app.tiles import TileCache


def make_app(tmp_path, handler):
    app = FastAPI()
    cache = TileCache(tmp_path, httpx.Client(transport=httpx.MockTransport(handler)))
    app.include_router(tiles_router(cache))
    return app


def test_tile_ok_with_cache_header(tmp_path):
    app = make_app(tmp_path, lambda r: httpx.Response(200, content=b"PNG"))
    resp = TestClient(app).get("/tiles/5/3/4.png")
    assert resp.status_code == 200
    assert resp.content == b"PNG"
    assert resp.headers["content-type"] == "image/png"
    assert "max-age=604800" in resp.headers["cache-control"]


def test_tile_failure_503(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    client = TestClient(make_app(tmp_path, handler))
    assert client.get("/tiles/5/3/4.png").status_code == 503
    assert client.get("/tiles/5/3/4.png").status_code == 503
    assert len(calls) == 1


def test_tile_out_of_range_400(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"PNG")

    client = TestClient(make_app(tmp_path, handler))
    for path in ("/tiles/20/0/0.png", "/tiles/2/4/0.png", "/tiles/2/0/-1.png"):
        assert client.get(path).status_code in (400, 422)
    assert calls == []


def test_tile_fetches_are_serialized(tmp_path):
    lock = threading.Lock()
    state = {"cur": 0, "max": 0}

    def handler(request):
        with lock:
            state["cur"] += 1
            state["max"] = max(state["max"], state["cur"])
        time.sleep(0.05)
        with lock:
            state["cur"] -= 1
        return httpx.Response(200, content=b"PNG")

    app = make_app(tmp_path, handler)

    def get(i):
        return TestClient(app).get(f"/tiles/5/{i}/4.png").status_code

    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(get, range(8)))
    assert codes == [200] * 8
    assert state["max"] == 1


def test_user_agent_is_generic(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.headers["User-Agent"])
        return httpx.Response(200, content=b"PNG")

    TestClient(make_app(tmp_path, handler)).get("/tiles/5/3/4.png")
    assert seen == ["car-trace/1.0 (self-hosted, personal use)"]
