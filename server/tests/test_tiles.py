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
    assert seen[0].headers["User-Agent"] == "car-trace/1.0 (self-hosted, personal use)"
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


def test_backoff_after_failure_skips_network_for_a_minute(tmp_path):
    calls = []
    clock = [NOW]
    ok = [False]

    def h(request):
        calls.append(request)
        return httpx.Response(200, content=b"png") if ok[0] else httpx.Response(500)

    http = httpx.Client(transport=httpx.MockTransport(h))
    c = TileCache(tmp_path, http, now=lambda: clock[0])
    assert c.fetch(5, 1, 1) is None
    assert len(calls) == 1
    clock[0] += 59
    assert c.fetch(5, 2, 2) is None
    assert len(calls) == 1
    p = tmp_path / "5" / "3" / "3.png"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"old")
    os.utime(p, (NOW - 8 * DAY, NOW - 8 * DAY))
    assert c.fetch(5, 3, 3) == b"old"
    assert len(calls) == 1
    clock[0] += 2
    ok[0] = True
    assert c.fetch(5, 2, 2) == b"png"
    assert len(calls) == 2
    assert c.fetch(5, 4, 4) == b"png"  # success cleared the backoff
    assert len(calls) == 3
