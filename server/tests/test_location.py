import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app import db
from app.location import (
    CarStatus,
    GpsPoint,
    car_status,
    format_status,
    last_valid_point,
)

TZ = "Europe/Madrid"


def P(ts, lat=40.0, lon=-3.0, acc=5.0, speed=None):
    return GpsPoint(ts=ts, lat=lat, lon=lon, acc_m=acc, speed_mps=speed)


def test_skips_zero_zero():
    pts = [P(2000, 0.0, 0.0), P(1000)]
    assert last_valid_point(pts).ts == 1000


def test_skips_low_accuracy():
    pts = [P(2000, acc=80.0), P(1000)]
    assert last_valid_point(pts).ts == 1000


def test_skips_impossible_jump():
    # newest is ~11 km away from the older one, 10 s apart -> bogus
    pts = [P(11000, lat=40.1), P(1000, lat=40.0)]
    assert last_valid_point(pts).ts == 1000


def test_accepts_plausible_move_and_empty():
    assert last_valid_point([P(11000, lat=40.0005), P(1000)]).ts == 11000
    assert last_valid_point([]) is None


def _conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))


_n = [0]


def add(conn, ts, type_, data):
    _n[0] += 1
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (f"id{_n[0]}", "d", "s", _n[0], ts, type_, json.dumps(data), ts),
    )


def gps(conn, ts, lat=40.0, lon=-3.0, acc=5.0, speed=None):
    add(conn, ts, "gps", {"lat": lat, "lon": lon, "acc_m": acc, "speed_mps": speed,
                          "bearing": None, "alt_m": None})


def test_no_data(tmp_path):
    st = car_status(_conn(tmp_path), 10_000)
    assert st.state == "no_data" and st.last_ts is None
    assert format_status(st, 10_000, TZ) == "Todavía no hay datos del coche."


def test_moving_when_recent(tmp_path):
    c = _conn(tmp_path)
    gps(c, 1_000_000, speed=10.0)
    st = car_status(c, 1_000_000 + 299_000)
    assert st.state == "moving"
    assert st.speed_kmh == 36.0


def test_parked_after_five_minutes(tmp_path):
    c = _conn(tmp_path)
    gps(c, 1_000_000)
    assert car_status(c, 1_000_000 + 300_000).state == "parked"


def test_speed_prefers_obd(tmp_path):
    c = _conn(tmp_path)
    gps(c, 1_000_000, speed=10.0)
    add(c, 990_000, "obd", {"values": {"speed_kmh": 47.4}})
    add(c, 900_000, "obd", {"values": {"speed_kmh": 99}})  # older than 60 s
    st = car_status(c, 1_010_000)
    assert st.speed_kmh == 47.4


def test_status_without_valid_gps(tmp_path):
    c = _conn(tmp_path)
    gps(c, 1_000_000, lat=0.0, lon=0.0)
    add(c, 1_001_000, "obd", {"values": {"rpm": 800}})
    st = car_status(c, 1_002_000)
    assert st.state == "moving" and st.point is None and st.last_ts == 1_001_000
    assert st.speed_kmh is None
    assert format_status(st, 1_002_000, TZ).endswith("\nSin posición GPS todavía.")


def ms(h, m, s=0):
    return int(datetime(2026, 11, 18, h, m, s, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


def test_format_parked_with_gps_gap():
    st = CarStatus("parked", ms(18, 42), P(ms(18, 39)), None)
    now = ms(20, 47)
    assert format_status(st, now, TZ) == (
        "🅿️ Aparcado desde las 18:42 (hace 2 h 5 min)\nÚltima posición GPS de las 18:39"
    )


def test_format_parked_no_gap():
    st = CarStatus("parked", ms(18, 42), P(ms(18, 41)), None)
    assert format_status(st, ms(18, 50), TZ) == "🅿️ Aparcado desde las 18:42 (hace 8 min)"


def test_format_moving():
    st = CarStatus("moving", ms(12, 0), P(ms(12, 0)), 47.4)
    assert format_status(st, ms(12, 0, 20), TZ) == "🚗 En marcha · último dato hace 20 s · 47 km/h"
    st = CarStatus("moving", ms(12, 0), P(ms(12, 0)), None)
    assert format_status(st, ms(12, 0, 20), TZ) == "🚗 En marcha · último dato hace 20 s"


def test_relative_time_buckets():
    def rel(sec):
        st = CarStatus("moving", 0, P(0), None)
        return format_status(st, sec * 1000, TZ)

    assert "hace 59 s" in rel(59)
    assert "hace 1 min" in rel(60)
    assert "hace 59 min" in rel(3599)
    assert "hace 1 h 0 min" in rel(3600)
    assert "hace 2 h 5 min" in rel(7500)
