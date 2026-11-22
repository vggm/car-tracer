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
