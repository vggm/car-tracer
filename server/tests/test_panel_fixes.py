import time

from app.config import Settings
from app.dtc import describe
from app.main import create_app
from app.panel import api
from tests.conftest import FIXED_NOW
from tests.test_panel_api import T1, T2, _ids, _seed
from tests.test_trip_cache import add, drive


def test_trip_detail_keeps_points_though_cache_is_slim(client):
    _seed(client)
    trip_id = _ids(client)[0]
    cached = client.app.state.trip_cache.all_trips(client.app.state.readers.get())
    assert cached and all(t.points == [] for t in cached)
    body = client.get(f"/api/panel/trips/{trip_id}").json()
    assert len(body["points"]) > 1 and len(body["series"]["ts"]) > 1


def test_trip_detail_malformed_ids_still_404(client):
    _seed(client)
    for bad in ["abc", "x:y", "s1:999", "a:b:123", "s1:"]:
        assert client.get(f"/api/panel/trips/{bad}").status_code == 404, bad


def test_trip_detail_new_dtcs_desc(client):
    conn = client.app.state.db
    add(conn, 0, "dtc", {"active": ["P0401"], "pending": []}, "old")
    drive(conn, T1, 600, session="s1")
    add(conn, T1 + 300_000, "dtc", {"active": ["P0401", "P0420"], "pending": []}, "s1")
    body = client.get(f"/api/panel/trips/{_ids(client)[0]}").json()
    assert body["new_dtcs"] == ["P0420"]
    assert body["new_dtcs_desc"] == [{"code": "P0420", "desc": describe("P0420")}]


def test_trip_detail_new_dtcs_desc_empty_when_none(client):
    _seed(client)
    body = client.get(f"/api/panel/trips/{_ids(client)[0]}").json()
    assert body["new_dtcs"] is None and body["new_dtcs_desc"] == []


def test_year_before_2000_is_422(client):
    for m in ["0000-01", "0001-01", "1999-12"]:
        assert client.get(f"/api/panel/overview?month={m}").status_code == 422
        assert client.get(f"/api/panel/trips?month={m}").status_code == 422


def _count_alerts(monkeypatch):
    calls = []
    real = api.compute_alerts

    def counted(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(api, "compute_alerts", counted)
    return calls


def test_alerts_memoized_within_ttl(client, monkeypatch):
    _seed(client)
    calls = _count_alerts(monkeypatch)
    client.get("/api/panel/overview")
    client.get("/api/panel/alerts")
    client.get("/api/panel/overview")
    assert len(calls) == 1


def test_alerts_memo_invalidated_by_new_record(client, monkeypatch):
    conn = _seed(client)
    calls = _count_alerts(monkeypatch)
    client.get("/api/panel/alerts")
    drive(conn, T2 + 700_000, 100, session="s2", north0=9000)
    client.get("/api/panel/alerts")
    assert len(calls) == 2


def test_alerts_memo_expires_after_ttl(client, monkeypatch):
    _seed(client)
    calls = _count_alerts(monkeypatch)
    now = [1000.0]
    monkeypatch.setattr(api, "_mono", lambda: now[0])
    client.get("/api/panel/alerts")
    now[0] += 59
    client.get("/api/panel/alerts")
    now[0] += 2
    client.get("/api/panel/alerts")
    assert len(calls) == 2


def test_warm_populates_cache(tmp_path):
    s = Settings(ingest_token="t", bot_token="", chat_id=None,
                 db_path=str(tmp_path / "w.db"), tz="Europe/Madrid")
    cold = create_app(s, clock=lambda: FIXED_NOW)
    drive(cold.state.db, T1, 300)
    cold.state.db.commit()
    assert not cold.state.trip_cache._sessions
    warm = create_app(s, clock=lambda: FIXED_NOW, warm=True)
    deadline = time.time() + 5
    while time.time() < deadline and not warm.state.trip_cache._sessions:
        time.sleep(0.05)
    assert warm.state.trip_cache._sessions
