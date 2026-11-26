from app.location import OBD_WINDOW_MS
from tests.conftest import FIXED_NOW
from tests.test_location import add, gps

KEYS = {"state", "now", "last_ts", "point", "speed_kmh", "engine_on", "rpm"}


def _get(client):
    r = client.get("/api/panel/location")
    assert r.status_code == 200
    return r.json()


def obd(conn, ts, **values):
    add(conn, ts, "obd", {"values": values})


def test_no_data(client):
    body = _get(client)
    assert set(body) == KEYS
    assert body["state"] == "no_data"
    assert body["now"] == FIXED_NOW
    for k in KEYS - {"state", "now"}:
        assert body[k] is None


def test_parked_with_point(client):
    conn = client.app.state.db
    ts = FIXED_NOW - 10 * 60_000
    gps(conn, ts, lat=40.5, lon=-3.5, acc=7.0, speed=0.0)
    body = _get(client)
    assert body["state"] == "parked"
    assert body["last_ts"] == ts
    assert body["point"] == {"ts": ts, "lat": 40.5, "lon": -3.5, "acc_m": 7.0}
    assert body["rpm"] is None


def test_moving_with_speed_and_rpm(client):
    conn = client.app.state.db
    ts = FIXED_NOW - 5_000
    gps(conn, ts, speed=20.0)
    obd(conn, ts, speed_kmh=72.34, rpm=2500.4)
    body = _get(client)
    assert body["state"] == "moving"
    assert body["speed_kmh"] == 72.3
    assert body["rpm"] == 2500
    assert body["engine_on"] is True
    assert body["point"]["ts"] == ts


def test_idle_engine_on_slow(client):
    conn = client.app.state.db
    ts = FIXED_NOW - 5_000
    gps(conn, ts, speed=0.0)
    obd(conn, ts, speed_kmh=0, rpm=800)
    body = _get(client)
    assert body["state"] == "idle"
    assert body["engine_on"] is True
    assert body["rpm"] == 800


def test_rpm_outside_window_is_null(client):
    conn = client.app.state.db
    ts = FIXED_NOW - 5_000
    obd(conn, ts - OBD_WINDOW_MS - 1, rpm=3000)
    obd(conn, ts, voltage_v=12.0)
    body = _get(client)
    assert body["rpm"] is None


def test_no_gps_point(client):
    conn = client.app.state.db
    ts = FIXED_NOW - 5_000
    obd(conn, ts, speed_kmh=0, rpm=900)
    body = _get(client)
    assert set(body) == KEYS
    assert body["point"] is None
    assert body["state"] == "idle"
    assert body["last_ts"] == ts
    assert body["rpm"] == 900
