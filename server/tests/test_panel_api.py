import pytest
from tests.test_trip_cache import drive

# 2025-11-10 and 2025-11-12 (inside FIXED_NOW's month, 2025-11)
T1 = 1762761600000
T2 = 1762934400000


def _seed(client):
    conn = client.app.state.db
    drive(conn, T1, 600, session="s1")
    drive(conn, T2, 600, session="s2")
    return conn


def _ids(client):
    return [t["id"] for t in client.get("/api/panel/trips").json()["trips"]]


def test_overview_shape_and_default_month(client):
    _seed(client)
    body = client.get("/api/panel/overview").json()
    assert set(body) == {"month", "totals", "months", "days", "alerts_recent"}
    assert body["month"] == "2025-11"
    assert len(body["months"]) == 12
    assert body["totals"]["trips"] == 2


def test_overview_bad_month_422(client):
    assert client.get("/api/panel/overview?month=2025-13").status_code == 422
    assert client.get("/api/panel/trips?month=nope").status_code == 422


def test_trips_month_list_newest_first_without_points(client):
    _seed(client)
    body = client.get("/api/panel/trips").json()
    assert body["month"] == "2025-11"
    trips = body["trips"]
    assert [t["start_ts"] for t in trips] == [T2, T1]
    assert all("points" not in t for t in trips)


def test_trip_detail_ok(client):
    _seed(client)
    trip_id = _ids(client)[0]
    r = client.get(f"/api/panel/trips/{trip_id}")
    assert r.status_code == 200
    body = r.json()
    assert "points" in body and "series" in body
    ts = body["series"]["ts"]
    assert ts == sorted(ts) and len(ts) > 1


def test_trip_detail_bad_ids_404(client):
    _seed(client)
    for bad in ["abc", "x:y", "s1:999", "a:b:123"]:
        r = client.get(f"/api/panel/trips/{bad}")
        assert r.status_code == 404, bad
        assert r.json() == {"detail": "trip not found"}


def test_endpoints_on_empty_db(client):
    for path in ["overview", "trips", "dtc", "alerts"]:
        assert client.get(f"/api/panel/{path}").status_code == 200
    assert client.get("/api/panel/overview").json()["totals"] == {
        "km": 0, "trips": 0, "drive_ms": 0, "max_kmh": None}
    dtc = client.get("/api/panel/dtc").json()
    assert dtc["current"] is None and dtc["history"] == []
    assert client.get("/api/panel/alerts").json() == {"alerts": []}


def test_index_and_static_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert client.get("/static/index.html").status_code == 200


from urllib.parse import quote


class _Boom:
    def __getattr__(self, name):
        raise AssertionError(f"panel used app.state.db ({name})")


def test_panel_does_not_use_shared_ingest_connection(client):
    _seed(client)
    trip_id = _ids(client)[0]
    client.app.state.db = _Boom()
    for url in [f"/api/panel/trips/{quote(trip_id, safe='')}", "/api/panel/overview", "/api/panel/dtc",
                "/api/panel/alerts", "/api/panel/trips"]:
        assert client.get(url).status_code == 200, url


def test_panel_concurrent_requests_all_ok(client):
    from concurrent.futures import ThreadPoolExecutor
    _seed(client)
    urls = ["/api/panel/alerts", "/api/panel/dtc", "/api/panel/overview"] * 20
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda u: client.get(u).status_code, urls))
    assert codes == [200] * 60


# --- journeys ---------------------------------------------------------------
GAP = 230_000
J0 = 1762761600000  # 2025-11-10 08:00 Madrid-ish, well inside the month


def _three(client):
    conn = client.app.state.db
    drive(conn, J0, 300)
    drive(conn, J0 + 300_000 + GAP, 300, north0=5000)
    drive(conn, J0 + 600_000 + 2 * GAP, 300, north0=10000)
    return [str(J0), str(J0 + 300_000 + GAP), str(J0 + 600_000 + 2 * GAP)]


def _post(client, a, b):
    return client.post("/api/panel/journeys", json={"trip_ids": [a, b]})


def test_trips_list_items_with_journey(client):
    a, b, c = _three(client)
    assert _post(client, a, b).status_code == 201
    items = client.get("/api/panel/trips").json()["trips"]
    assert len(items) == 2
    assert items[0]["kind"] == "trip" and items[0]["id"] == c
    assert items[0]["gap_before_ms"] == GAP
    j = items[1]
    assert j["kind"] == "journey" and j["id"] == "v1"
    assert len(j["segments"]) == 2 and len(j["stops"]) == 1
    assert set(j["stops"][0]) == {"start_ts", "end_ts", "duration_ms"}
    assert j["gap_before_ms"] is None
    assert "drive_ms" in j and "segments" not in items[0]


def test_gap_before_null_across_midnight(client):
    conn = client.app.state.db
    # 2025-11-10 22:50 UTC = 23:50 Madrid; 2025-11-10 23:10 UTC = 00:10 Madrid on the 11th
    a = 1762815000000
    drive(conn, a, 300)
    drive(conn, a + 20 * 60_000, 300, north0=5000)
    items = client.get("/api/panel/trips").json()["trips"]
    assert len(items) == 2
    assert items[0]["gap_before_ms"] is None


def test_post_journey_201_and_422(client):
    a, b, c = _three(client)
    r = _post(client, a, b)
    assert r.status_code == 201 and r.json() == {"id": "v1"}
    assert _post(client, a, c).status_code == 422
    assert _post(client, a, "999").status_code == 422
    assert client.post("/api/panel/journeys", json={}).status_code == 422


def test_journey_detail(client):
    a, b, c = _three(client)
    _post(client, a, b)
    r = client.get("/api/panel/journeys/v1")
    assert r.status_code == 200
    body = r.json()
    items = client.get("/api/panel/trips").json()["trips"]
    segs = body["segments"]
    assert body["km"] == pytest.approx(sum(s["km"] for s in segs), abs=0.11)
    assert len(segs) == 2 and all(s["points"] for s in segs)
    assert all("series" not in s for s in segs)
    stop = body["stops"][0]
    assert stop["lat"] is not None and stop["lon"] is not None
    assert stop["duration_ms"] == GAP
    s = body["series"]
    gaps = [i for i, v in enumerate(s["speed_kmh"]) if v is None]
    assert len(gaps) == 1
    assert s["ts"][gaps[0]] == stop["start_ts"] + 1
    assert s["rpm"][gaps[0]] is None and s["coolant_c"][gaps[0]] is None
    assert s["ts"] == sorted(s["ts"])
    for k in ("idle_ms", "coolant_start", "coolant_max", "rpm_avg", "rpm_max", "new_dtcs_desc"):
        assert k in body
    assert body["kind"] == "journey" and body["id"] == items[1]["id"]


def test_journey_detail_404(client):
    _three(client)
    assert client.get("/api/panel/journeys/v99").status_code == 404
    assert client.get("/api/panel/journeys/x").status_code == 404


def test_trip_detail_journey_id(client):
    a, b, c = _three(client)
    _post(client, a, b)
    assert client.get(f"/api/panel/trips/{a}").json()["journey_id"] == "v1"
    assert client.get(f"/api/panel/trips/{c}").json()["journey_id"] is None
    assert client.delete("/api/panel/journeys/v1").status_code == 204
    assert client.get(f"/api/panel/trips/{a}").json()["journey_id"] is None


def test_delete_journey_204_404(client):
    a, b, c = _three(client)
    _post(client, a, b)
    assert client.delete("/api/panel/journeys/v1").status_code == 204
    assert client.delete("/api/panel/journeys/v1").status_code == 404
    assert client.delete("/api/panel/journeys/x").status_code == 404
    assert len(client.get("/api/panel/trips").json()["trips"]) == 3


def test_overview_counts_items(client):
    a, b, c = _three(client)
    _post(client, a, b)
    body = client.get("/api/panel/overview").json()
    assert body["totals"]["trips"] == 2
    trips = client.get("/api/panel/trips").json()["trips"]
    assert body["totals"]["drive_ms"] == sum(t["drive_ms"] for t in trips)
    assert body["months"][-1]["trips"] == 2
    assert sum(d["trips"] for d in body["days"]) == 2
    assert body["totals"]["drive_ms"] == 900_000
