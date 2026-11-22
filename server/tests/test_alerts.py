import json

from app import db
from app.dtc import describe
from app.alerts import RECENT_MS, WINDOW_MS, Alert, compute_alerts, recent_count
from app.trips import list_trips

DAY = 86_400_000
NOW = 100 * DAY
TZ = "Europe/Madrid"
M_PER_DEG = 111_195.0
_n = [0]


def _conn(tmp_path, name="t.db"):
    return db.connect(str(tmp_path / name))


def add(conn, ts, type_, data, session="s1"):
    _n[0] += 1
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (f"id{_n[0]}", "d", session, _n[0], ts, type_, json.dumps(data), ts),
    )


def gps(conn, ts, north_m=0.0, speed=None, session="s1"):
    add(conn, ts, "gps", {
        "lat": 40.0 + north_m / M_PER_DEG, "lon": -3.0,
        "acc_m": 5.0, "speed_mps": speed,
    }, session)


def obd(conn, ts, session="s1", **values):
    add(conn, ts, "obd", {"values": values}, session)


def dtc(conn, ts, active=(), pending=(), session="s1"):
    add(conn, ts, "dtc", {"active": list(active), "pending": list(pending)}, session)


def drive(conn, start_ts, seconds=300, speed=10.0, session="s1", rpm=1500, coolant=None):
    for i in range(0, seconds + 1, 10):
        ts = start_ts + i * 1000
        gps(conn, ts, north_m=i * speed, speed=speed, session=session)
        if rpm is not None:
            vals = {"rpm": rpm, "speed_kmh": speed * 3.6}
            if coolant is not None:
                vals["coolant_c"] = coolant
            obd(conn, ts, session=session, **vals)


def alerts(conn, now=NOW):
    trips, _ = list_trips(conn, limit=1000)
    return compute_alerts(conn, trips, now, TZ)


def kinds(result, kind):
    return [a for a in result if a.kind == kind]


def test_new_dtc_only_codes_not_in_previous_reading(tmp_path):
    conn = _conn(tmp_path)
    dtc(conn, NOW - 2000, active=["P0401"])
    dtc(conn, NOW - 1000, active=["P0401"], pending=["P0409"])
    (a,) = kinds(alerts(conn), "new_dtc")
    assert a.title == "Avería nueva: P0409"
    assert a.severity == "high"
    assert a.ts == NOW - 1000


def test_new_dtc_plural_title(tmp_path):
    conn = _conn(tmp_path)
    dtc(conn, NOW - 2000)
    dtc(conn, NOW - 1000, active=["P0401", "P0409"])
    (a,) = kinds(alerts(conn), "new_dtc")
    assert a.title == "Averías nuevas: P0401, P0409"
    assert a.detail == f"{describe('P0401')}; {describe('P0409')}"


def test_first_dtc_reading_gives_no_alert(tmp_path):
    conn = _conn(tmp_path)
    dtc(conn, NOW - 1000, active=["P0401"])
    assert kinds(alerts(conn), "new_dtc") == []


def test_new_dtc_previous_reading_outside_window_counts(tmp_path):
    conn = _conn(tmp_path)
    dtc(conn, NOW - WINDOW_MS - 5000, active=["P0401"])
    dtc(conn, NOW - 1000, active=["P0401", "P0409"])
    (a,) = kinds(alerts(conn), "new_dtc")
    assert a.title == "Avería nueva: P0409"


def test_overheat_threshold_inclusive(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, NOW - 3_600_000, coolant=105)
    (a,) = kinds(alerts(conn), "overheat")
    assert a.title == "Motor caliente: 105 °C"
    assert a.severity == "high"
    assert a.ts == NOW - 3_600_000
    assert a.detail == "Trayecto del sábado 11 de abril a las 00:00"


def test_overheat_just_below_threshold(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, NOW - 3_600_000, coolant=104.9)
    assert kinds(alerts(conn), "overheat") == []


def test_battery_low_engine_off_min_per_session(tmp_path):
    conn = _conn(tmp_path)
    for i, v in enumerate([12.1, 11.9, 11.7]):
        obd(conn, NOW - 5000 + i * 1000, voltage_v=v, rpm=0)
    (a,) = kinds(alerts(conn), "battery_low")
    assert a.title == "Batería baja: 11,7 V"
    assert a.ts == NOW - 3000
    assert a.severity == "warn"
    assert a.detail == "Con el motor parado, hoy 00:59"


def test_battery_low_without_rpm_uses_engine_on_voltage(tmp_path):
    conn = _conn(tmp_path)
    obd(conn, NOW - 1000, voltage_v=11.8)
    assert len(kinds(alerts(conn), "battery_low")) == 1


def test_battery_low_ignores_engine_running_and_unknown_high_voltage(tmp_path):
    conn = _conn(tmp_path)
    obd(conn, NOW - 2000, voltage_v=11.5, rpm=800)
    obd(conn, NOW - 1000, voltage_v=12.5)
    assert kinds(alerts(conn), "battery_low") == []


def test_charging_needs_two_consecutive_out_of_range(tmp_path):
    conn = _conn(tmp_path)
    for i, v in enumerate([12.6, 13.8, 12.7]):
        obd(conn, NOW - 5000 + i * 1000, voltage_v=v, rpm=1500)
    assert kinds(alerts(conn), "charging") == []

    conn2 = _conn(tmp_path, "t2.db")
    for i, v in enumerate([12.6, 12.5]):
        obd(conn2, NOW - 5000 + i * 1000, voltage_v=v, rpm=1500)
    (a,) = kinds(alerts(conn2), "charging")
    assert a.title == "Carga anómala: 12,6 V en marcha"
    assert a.severity == "warn"
    assert a.ts == NOW - 5000
    assert a.detail == "Lo normal en marcha es entre 13,0 y 14,8 V"


def test_no_obd_trip_alert_links_trip(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, NOW - 3_600_000, rpm=None)
    (trip,), _ = list_trips(conn)
    (a,) = kinds(alerts(conn), "no_obd")
    assert a.trip_id == trip.id
    assert a.severity == "info"
    assert a.title == "Trayecto sin datos del motor"
    assert a.detail == "3,0 km · sábado 11 de abril a las 00:00"


def test_stale_after_three_days(tmp_path):
    conn = _conn(tmp_path)
    obd(conn, NOW - 3 * DAY - 1, voltage_v=13.5, rpm=1000)
    (a,) = kinds(alerts(conn), "stale")
    assert a.title == "Sin datos desde hace 3 días"
    assert a.ts == NOW - 3 * DAY - 1
    assert a.id == f"stale:s1:{NOW - 3 * DAY - 1}"
    assert a.detail == "Último dato: mié 8 00:59"
    assert a.trip_id is None

    conn2 = _conn(tmp_path, "t2.db")
    obd(conn2, NOW - 3 * DAY, voltage_v=13.5, rpm=1000)
    assert kinds(alerts(conn2), "stale") == []


def test_outside_window_ignored(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, NOW - 91 * DAY, coolant=110)
    obd(conn, NOW - 1000, voltage_v=13.5, rpm=1000, session="s2")
    assert kinds(alerts(conn), "overheat") == []


def test_sorted_newest_first_and_ids_stable(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, NOW - 7_200_000, coolant=110, session="a")
    obd(conn, NOW - 1000, voltage_v=11.5, rpm=0, session="b")
    first, second = alerts(conn), alerts(conn)
    assert [a.id for a in first] == [a.id for a in second]
    assert len(first) >= 2
    assert [a.ts for a in first] == sorted((a.ts for a in first), reverse=True)


def test_stale_links_trip_containing_last_record(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, NOW - 5 * DAY, seconds=300)
    (trip,), _ = list_trips(conn)
    (a,) = kinds(alerts(conn), "stale")
    assert a.trip_id == trip.id


def test_stale_without_trip_when_last_record_outside_trip(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, NOW - 5 * DAY, seconds=300)
    obd(conn, NOW - 4 * DAY, voltage_v=13.5, rpm=1000)
    (a,) = kinds(alerts(conn), "stale")
    assert a.ts == NOW - 4 * DAY
    assert a.trip_id is None


def test_recent_count_seven_days():
    def mk(ts):
        return Alert(f"x:s:{ts}", "stale", "info", ts, "t", "d", None)

    items = [mk(NOW), mk(NOW - RECENT_MS), mk(NOW - RECENT_MS - 1)]
    assert recent_count(items, NOW) == 2


def test_stale_counts_health_heartbeat(tmp_path):
    conn = _conn(tmp_path)
    obd(conn, NOW - 5 * DAY, voltage_v=13.5, rpm=1000)
    assert len(kinds(alerts(conn), "stale")) == 1
    add(conn, NOW - 60_000, "health", {"values": {"battery_pct": 80}})
    assert kinds(alerts(conn), "stale") == []
