import os

import httpx

from app.tiles import TileCache

NOW = 1_700_000_000.0
DAY = 86400


def make(tmp_path, handler, now=NOW):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return TileCache(tmp_path, http, now=lambda: now)


def put(tmp_path, data, age_s):
    p = tmp_path / "5" / "3" / "4.png"
    p.parent.mkdir(parents=True)
    p.write_bytes(data)
    os.utime(p, (NOW - age_s, NOW - age_s))
    return p


def no_http(request):
    raise AssertionError("unexpected request")


def test_fresh_cache_no_http(tmp_path):
    put(tmp_path, b"cached", 6 * DAY)
    assert make(tmp_path, no_http).fetch(5, 3, 4) == b"cached"


def test_miss_downloads_and_writes(tmp_path):
    seen = []

    def h(request):
        seen.append(request)
        return httpx.Response(200, content=b"png")

    assert make(tmp_path, h).fetch(5, 3, 4) == b"png"
    assert (tmp_path / "5" / "3" / "4.png").read_bytes() == b"png"
    assert str(seen[0].url) == "https://tile.openstreetmap.org/5/3/4.png"
    assert seen[0].headers["User-Agent"] == "car-trace-bot/1.0 (self-hosted, personal use)"
    assert not list(tmp_path.rglob("*.tmp"))


def test_stale_refetched_and_rewritten(tmp_path):
    p = put(tmp_path, b"old", 8 * DAY)
    c = make(tmp_path, lambda r: httpx.Response(200, content=b"new"))
    assert c.fetch(5, 3, 4) == b"new"
    assert p.read_bytes() == b"new"


def test_http_500_returns_stale(tmp_path):
    put(tmp_path, b"old", 8 * DAY)
    assert make(tmp_path, lambda r: httpx.Response(500)).fetch(5, 3, 4) == b"old"


def test_error_without_file_returns_none(tmp_path):
    def boom(request):
        raise httpx.ConnectError("x")

    assert make(tmp_path, boom).fetch(5, 3, 4) is None
    assert make(tmp_path, lambda r: httpx.Response(404)).fetch(5, 3, 4) is None
