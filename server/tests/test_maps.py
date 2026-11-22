import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

DATA = bytes(range(100))


@pytest.fixture
def map_client(tmp_path):
    (tmp_path / "maps").mkdir()
    (tmp_path / "maps" / "spain.pmtiles").write_bytes(DATA)
    settings = Settings(ingest_token="t", bot_token="", chat_id=None,
                        db_path=str(tmp_path / "t.db"), tz="Europe/Madrid")
    with TestClient(create_app(settings, clock=lambda: 1763481600000)) as c:
        yield c


def test_full_get_advertises_ranges(map_client):
    r = map_client.get("/maps/spain.pmtiles")
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes"
    assert r.content == DATA


def test_range_request_returns_206(map_client):
    r = map_client.get("/maps/spain.pmtiles", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 0-9/100"
    assert r.content == DATA[:10]


def test_head_works(map_client):
    assert map_client.head("/maps/spain.pmtiles").status_code == 200


def test_missing_file_is_404(map_client):
    assert map_client.get("/maps/nope.pmtiles").status_code == 404


def test_missing_directory_is_404(client):
    assert client.head("/maps/spain.pmtiles").status_code == 404
    assert client.get("/maps/spain.pmtiles").status_code == 404


def test_forwarded_maps_is_404(map_client):
    r = map_client.get("/maps/spain.pmtiles", headers={"X-Forwarded-Host": "x.ts.net"})
    assert r.status_code == 404
