import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app import db
from app.location import (
    MOVING_MIN_KMH,
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


def test_stopped_when_recent_with_zero_gps_speed(tmp_path):
    c = _conn(tmp_path)
    gps(c, 1_000_000, speed=0.0)
    st = car_status(c, 1_000_000 + 10_000)
    assert st.state == "stopped"
    assert st.speed_kmh == 0.0


def test_stopped_when_recent_with_no_speed(tmp_path):
    c = _conn(tmp_path)
    gps(c, 1_000_000, speed=None)
    st = car_status(c, 1_000_000 + 10_000)
    assert st.state == "stopped"
    assert st.speed_kmh is None


def test_moving_at_exact_threshold(tmp_path):
    c = _conn(tmp_path)
    add(c, 1_000_000, "obd", {"values": {"speed_kmh": MOVING_MIN_KMH}})
    assert car_status(c, 1_010_000).state == "moving"


def test_stopped_just_below_threshold(tmp_path):
    c = _conn(tmp_path)
    add(c, 1_000_000, "obd", {"values": {"speed_kmh": 4.9}})
    assert car_status(c, 1_010_000).state == "stopped"


def test_idle_just_below_threshold_with_engine_on(tmp_path):
    c = _conn(tmp_path)
    add(c, 1_000_000, "obd", {"values": {"speed_kmh": 4.9, "rpm": 800}})
    assert car_status(c, 1_010_000).state == "idle"


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
    assert st.state == "idle" and st.point is None and st.last_ts == 1_001_000
    assert st.speed_kmh is None
    assert format_status(st, 1_002_000, TZ).endswith("\nSin posición GPS todavía.")


def obd(conn, ts, **values):
    add(conn, ts, "obd", {"values": values})


def test_engine_on_from_rpm(tmp_path):
    c = _conn(tmp_path)
    obd(c, 1_000_000, rpm=800, speed_kmh=0)
    st = car_status(c, 1_010_000)
    assert st.state == "idle" and st.engine_on is True


def test_engine_off_from_rpm_zero(tmp_path):
    c = _conn(tmp_path)
    obd(c, 1_000_000, rpm=0, speed_kmh=0)
    st = car_status(c, 1_010_000)
    assert st.state == "engine_off" and st.engine_on is False


def test_rpm_takes_precedence_over_voltage(tmp_path):
    c = _conn(tmp_path)
    obd(c, 990_000, voltage_v=14.2)
    obd(c, 1_000_000, rpm=0)
    st = car_status(c, 1_010_000)
    assert st.engine_on is False and st.state == "engine_off"


def test_rpm_precedence_engine_on_with_low_voltage(tmp_path):
    c = _conn(tmp_path)
    obd(c, 990_000, voltage_v=12.0)
    obd(c, 1_000_000, rpm=700)
    assert car_status(c, 1_010_000).engine_on is True


def test_voltage_threshold_boundary(tmp_path):
    c = _conn(tmp_path)
    obd(c, 1_000_000, voltage_v=13.2)
    assert car_status(c, 1_010_000).engine_on is True
    c2 = db.connect(str(tmp_path / "t2.db"))
    obd(c2, 1_000_000, voltage_v=13.19)
    st = car_status(c2, 1_010_000)
    assert st.engine_on is False and st.state == "engine_off"


def test_voltage_used_when_no_rpm_in_window(tmp_path):
    c = _conn(tmp_path)
    obd(c, 900_000, voltage_v=14.0)  # 100 s before last_ts: outside rpm window, inside voltage
    obd(c, 1_000_000, speed_kmh=0)
    assert car_status(c, 1_010_000).engine_on is True


def test_voltage_older_than_180s_ignored(tmp_path):
    c = _conn(tmp_path)
    obd(c, 800_000, voltage_v=14.0)  # 200 s before last_ts
    obd(c, 1_000_000, speed_kmh=0)
    st = car_status(c, 1_010_000)
    assert st.engine_on is None and st.state == "stopped"


def test_rpm_older_than_60s_ignored(tmp_path):
    c = _conn(tmp_path)
    obd(c, 930_000, rpm=800)  # 70 s before last_ts
    gps(c, 1_000_000, speed=0.0)
    st = car_status(c, 1_010_000)
    assert st.engine_on is None and st.state == "stopped"


def test_engine_none_without_obd(tmp_path):
    c = _conn(tmp_path)
    gps(c, 1_000_000)
    assert car_status(c, 1_010_000).engine_on is None


def test_moving_wins_over_engine_off(tmp_path):
    c = _conn(tmp_path)
    obd(c, 1_000_000, rpm=0, speed_kmh=30)
    assert car_status(c, 1_010_000).state == "moving"


def test_no_signal_when_stale_and_last_speed_moving(tmp_path):
    c = _conn(tmp_path)
    obd(c, 1_000_000, rpm=2000, speed_kmh=60)
    st = car_status(c, 1_000_000 + 300_000)
    assert st.state == "no_signal" and st.speed_kmh == 60


def test_no_signal_uses_gps_speed_fallback(tmp_path):
    c = _conn(tmp_path)
    gps(c, 1_000_000, speed=10.0)
    assert car_status(c, 1_400_000).state == "no_signal"


def test_parked_when_stale_and_slow(tmp_path):
    c = _conn(tmp_path)
    obd(c, 1_000_000, rpm=0, speed_kmh=0)
    assert car_status(c, 1_400_000).state == "parked"


def test_parked_when_stale_without_speed(tmp_path):
    c = _conn(tmp_path)
    obd(c, 1_000_000, rpm=800)
    assert car_status(c, 1_400_000).state == "parked"


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


def test_format_idle():
    st = CarStatus("idle", ms(12, 0), P(ms(12, 0)), 0.0)
    assert format_status(st, ms(12, 0, 20), TZ) == (
        "⏸️ Parado pero encendido · último dato hace 20 s"
    )
    st = CarStatus("idle", ms(12, 0), None, None)
    assert format_status(st, ms(12, 0, 20), TZ) == (
        "⏸️ Parado pero encendido · último dato hace 20 s\nSin posición GPS todavía."
    )


def test_format_engine_off():
    st = CarStatus("engine_off", ms(12, 0), P(ms(12, 0)), 0.0, False)
    assert format_status(st, ms(12, 0, 20), TZ) == (
        "🔑 Contacto puesto, motor apagado · último dato hace 20 s"
    )
    st = CarStatus("engine_off", ms(12, 0), None, None, False)
    assert format_status(st, ms(12, 0, 20), TZ) == (
        "🔑 Contacto puesto, motor apagado · último dato hace 20 s\nSin posición GPS todavía."
    )


def test_format_stopped():
    st = CarStatus("stopped", ms(12, 0), P(ms(12, 0)), 0.0, None)
    assert format_status(st, ms(12, 0, 20), TZ) == "⏸️ Parado · último dato hace 20 s"
    st = CarStatus("stopped", ms(12, 0), None, None, None)
    assert format_status(st, ms(12, 0, 20), TZ) == (
        "⏸️ Parado · último dato hace 20 s\nSin posición GPS todavía."
    )


def test_format_no_signal():
    st = CarStatus("no_signal", ms(18, 42), P(ms(18, 42)), 60.0, True)
    assert format_status(st, ms(18, 50), TZ) == "📵 Sin señal desde las 18:42 · iba en marcha"
    st = CarStatus("no_signal", ms(18, 42), None, 60.0, True)
    assert format_status(st, ms(18, 50), TZ) == (
        "📵 Sin señal desde las 18:42 · iba en marcha\nSin posición GPS todavía."
    )


def test_relative_time_buckets():
    def rel(sec):
        st = CarStatus("moving", 0, P(0), None)
        return format_status(st, sec * 1000, TZ)

    assert "hace 59 s" in rel(59)
    assert "hace 1 min" in rel(60)
    assert "hace 59 min" in rel(3599)
    assert "hace 1 h 0 min" in rel(3600)
    assert "hace 2 h 5 min" in rel(7500)


def test_diagnostic_records_do_not_change_car_status(tmp_path):
    c = _conn(tmp_path)
    gps(c, 1_000_000, speed=10.0)
    add(c, 1_000_000, "obd", {"values": {"rpm": 2000}})
    now = 1_000_000 + 30_000
    before = car_status(c, now)
    add(c, 1_020_000, "health", {"values": {"battery_pct": 80}})
    add(c, 1_025_000, "event", {"event": "obd_trace", "detail": "x"})
    add(c, 1_026_000, "event", {"event": "diag", "detail": "gps.no_fix"})
    assert car_status(c, now) == before
    assert before.last_ts == 1_000_000
