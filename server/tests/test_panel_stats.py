import json
from datetime import datetime, timezone

import pytest

from app import db
from app.dtc import describe
from app.panel import stats
from app.trips import Trip, list_trips

TZ = "Europe/Madrid"
M_PER_DEG = 111_195.0
_n = [0]


def utc(y, m, d, hh=12, mm=0):
    return int(datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp() * 1000)


def make_trip(start_ts, km=1.0, max_kmh=None, drive_ms=600_000):
    return Trip(
        id=f"s:{start_ts}", session_id="s", start_ts=start_ts, end_ts=start_ts + drive_ms,
        distance_m=km * 1000, max_kmh=max_kmh, has_obd=False, idle_ms=0,
        coolant_start=None, coolant_max=None, rpm_avg=None, rpm_max=None,
        new_dtcs=None, points=[],
    )


def _conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))


def add(conn, ts, type_, data, session="s1"):
    _n[0] += 1
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (f"id{_n[0]}", "d", session, _n[0], ts, type_, json.dumps(data), ts),
    )


def gps(conn, ts, north_m=0.0, east_m=0.0, speed=None, acc=5.0, session="s1"):
    add(conn, ts, "gps", {
        "lat": 40.0 + north_m / M_PER_DEG, "lon": -3.0 + east_m / M_PER_DEG,
        "acc_m": acc, "speed_mps": speed,
    }, session)


def obd(conn, ts, session="s1", **values):
    add(conn, ts, "obd", {"values": values}, session)


def dtc(conn, ts, active=(), pending=(), session="s1"):
    add(conn, ts, "dtc", {"active": list(active), "pending": list(pending)}, session)


def drive(conn, start_ts, seconds, speed=10.0, session="s1", rpm=1500, north0=0.0):
    for i in range(0, seconds + 1, 10):
        ts = start_ts + i * 1000
        gps(conn, ts, north_m=north0 + i * speed, speed=speed, session=session)
        if rpm is not None:
            obd(conn, ts, session=session, rpm=rpm, speed_kmh=speed * 3.6)


def test_parse_month_valid_and_invalid():
    assert stats.parse_month("2026-11") == (2026, 11)
    for bad in ("2026-13", "2026-1", "x", "2026-00", "2026-11\n"):
        with pytest.raises(ValueError):
            stats.parse_month(bad)


def test_current_month():
    assert stats.current_month(utc(2026, 11, 30, 23, 30), TZ) == (2026, 12)


def test_trip_after_local_midnight_counts_for_local_day():
    assert stats.date_key(utc(2026, 11, 19, 23, 30), TZ) == "2026-11-20"
    assert stats.month_key(utc(2026, 11, 30, 23, 30), TZ) == "2026-12"


def test_trips_in_month_keeps_order():
    a, b, c = make_trip(utc(2026, 11, 5)), make_trip(utc(2026, 10, 5)), make_trip(utc(2026, 11, 2))
    assert stats.trips_in_month([a, b, c], 2026, 11, TZ) == [a, c]


def test_months_series_twelve_with_empty_months():
    trips = [make_trip(utc(2026, 1, 10), km=5), make_trip(utc(2026, 11, 10), km=2)]
    s = stats.months_series(trips, 2026, 11, TZ)
    assert len(s) == 12
    assert s[0]["month"] == "2025-12" and s[-1]["month"] == "2026-11"
    assert s[1] == {"month": "2026-01", "km": 5.0, "trips": 1, "drive_ms": 600_000}
    assert s[2] == {"month": "2026-02", "km": 0.0, "trips": 0, "drive_ms": 0}
    assert s[-1]["trips"] == 1


def test_months_series_crosses_year():
    s = stats.months_series([], 2026, 2, TZ, count=4)
    assert [m["month"] for m in s] == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_days_series_window_and_only_used_days():
    trips = [
        make_trip(utc(2025, 11, 30), km=1), make_trip(utc(2025, 12, 1), km=2),
        make_trip(utc(2025, 12, 1, 15), km=3), make_trip(utc(2026, 11, 30), km=4),
    ]
    s = stats.days_series(trips, 2026, 11, TZ)
    assert s == [
        {"date": "2025-12-01", "km": 5.0, "trips": 2},
        {"date": "2026-11-30", "km": 4.0, "trips": 1},
    ]


def test_days_series_across_dst_change():
    # DST ends 2026-10-25 in Madrid
    # local date differs from the UTC date on both sides of the change:
    # 22:30Z on the 24th is 00:30 CEST on the 25th; 23:30Z on the 25th is 00:30 CET on the 26th
    trips = [
        make_trip(utc(2026, 10, 24, 22, 30)),
        make_trip(utc(2026, 10, 25, 23, 30)),
        make_trip(utc(2026, 10, 27, 10, 0)),
    ]
    s = stats.days_series(trips, 2026, 10, TZ)
    assert [d["date"] for d in s] == ["2026-10-25", "2026-10-26", "2026-10-27"]


def test_totals_and_rounding():
    t = stats.totals([make_trip(0, km=12.345, max_kmh=97.6), make_trip(1, km=1.0)])
    assert t == {"km": 13.3, "trips": 2, "drive_ms": 1_200_000, "max_kmh": 98}
    assert stats.totals([])["max_kmh"] is None


def test_trip_summary():
    t = make_trip(1000, km=3.0, max_kmh=60.4)
    s = stats.trip_summary(t)
    assert s["id"] == "s:1000" and s["km"] == 3.0 and s["max_kmh"] == 60
    assert s["duration_ms"] == 600_000 and s["avg_kmh"] == 18
    assert s["has_obd"] is False and s["new_dtcs"] is None


def test_trip_detail_series_prefers_obd(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 100)
    obd(conn, 55_000, rpm=1500.4, speed_kmh=36.04, coolant_c=87.6)
    (trip,), _ = list_trips(conn)
    d = stats.trip_detail(conn, trip)
    i = d["series"]["ts"].index(55_000)
    assert d["series"]["speed_kmh"][i] == 36.0
    assert d["series"]["rpm"][i] == 1500 and isinstance(d["series"]["rpm"][i], int)
    assert d["series"]["coolant_c"][i] == 88
    assert d["id"] == trip.id and d["idle_ms"] == trip.idle_ms
    assert len(d["points"]) > 0 and len(d["points"][0]) == 3
    assert d["series"]["rpm"] and None not in d["series"]["rpm"]
    assert d["series"]["coolant_c"].count(None) == len(d["series"]["ts"]) - 1
    assert d["rpm_avg"] == 1500


def test_trip_detail_series_gps_only(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 100, rpm=None)
    (trip,), _ = list_trips(conn)
    s = stats.trip_detail(conn, trip)["series"]
    assert len(s["ts"]) == len(trip.points)
    assert all(r is None for r in s["rpm"]) and all(c is None for c in s["coolant_c"])
    assert s["speed_kmh"][0] == 36.0


def test_dtc_history_appeared_gone_cleared(tmp_path):
    conn = _conn(tmp_path)
    dtc(conn, 100, [])
    dtc(conn, 200, ["P0401"])
    dtc(conn, 300, [], ["P0409"])
    add(conn, 400, "event", {"event": "dtc_clear", "detail": "abc"})
    h = stats.dtc_history(conn)
    assert [(e["kind"], e["codes"]) for e in h] == [
        ("cleared", []), ("gone", ["P0401"]), ("appeared", ["P0409"]), ("appeared", ["P0401"]),
    ]
    assert h[0]["ts"] == 400
    assert len(stats.dtc_history(conn, limit=2)) == 2


def test_dtc_state_none_and_described(tmp_path):
    conn = _conn(tmp_path)
    assert stats.dtc_state(conn) is None
    dtc(conn, 100, ["P0401"], ["P0409"])
    assert stats.dtc_state(conn) == {
        "ts": 100,
        "active": [{"code": "P0401", "desc": describe("P0401")}],
        "pending": [{"code": "P0409", "desc": describe("P0409")}],
    }
