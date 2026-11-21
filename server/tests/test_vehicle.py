import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app import db
from app.vehicle import format_estado

TZ = "Europe/Madrid"
NOW = int(datetime(2026, 11, 21, 20, 31, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)
T = int(datetime(2026, 11, 21, 18, 26, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)
_n = [0]


def _conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))


def add(conn, ts, type_, data):
    _n[0] += 1
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (f"v{_n[0]}", "d", "s", _n[0], ts, type_, json.dumps(data), ts),
    )


def obd(conn, ts, **values):
    add(conn, ts, "obd", {"values": values})


def test_spec_example(tmp_path):
    c = _conn(tmp_path)
    obd(c, T, coolant_c=85, rpm=741)
    obd(c, T - 20_000, voltage_v=14.1)
    add(c, T, "dtc", {"active": ["P0401", "P0409", "P0490", "P1351", "P1162"], "pending": []})
    assert format_estado(c, NOW, TZ) == (
        "🔧 Estado del coche · datos de hoy 18:26 (hace 2 h 5 min)\n"
        "🌡️ Motor: 85 °C\n"
        "🔋 Batería: 14,1 V (cargando)\n"
        "⚙️ Revoluciones: 741 rpm\n"
        "⚠️ 5 averías guardadas · /averias"
    )


def test_header_uses_newest_of_engine_and_voltage(tmp_path):
    c = _conn(tmp_path)
    obd(c, T - 600_000, coolant_c=85, rpm=741)
    obd(c, T, voltage_v=12.4)
    assert format_estado(c, NOW, TZ).startswith(
        "🔧 Estado del coche · datos de hoy 18:26 (hace 2 h 5 min)"
    )


def test_not_charging(tmp_path):
    c = _conn(tmp_path)
    obd(c, T, coolant_c=85, rpm=0, voltage_v=12.4)
    out = format_estado(c, NOW, TZ)
    assert "🔋 Batería: 12,4 V\n" in out + "\n"
    assert "cargando" not in out


def test_no_voltage_omits_battery(tmp_path):
    c = _conn(tmp_path)
    obd(c, T, coolant_c=85, rpm=741)
    assert "Batería" not in format_estado(c, NOW, TZ)


def test_dtc_lines(tmp_path):
    c = _conn(tmp_path)
    obd(c, T, coolant_c=85, rpm=741)
    assert "DTC" not in format_estado(c, NOW, TZ) and "avería" not in format_estado(c, NOW, TZ)
    add(c, T, "dtc", {"active": [], "pending": []})
    assert format_estado(c, NOW, TZ).endswith("✅ Sin averías guardadas")
    add(c, T + 1, "dtc", {"active": ["P0401"], "pending": []})
    assert format_estado(c, NOW, TZ).endswith("⚠️ 1 avería guardada · /averias")


def test_no_engine_data(tmp_path):
    assert format_estado(_conn(tmp_path), NOW, TZ) == "Todavía no hay datos del motor."


def test_estado_same_ts_most_recent_insert_wins(tmp_path):
    conn = _conn(tmp_path)
    obd(conn, T, voltage_v=11.0)
    obd(conn, T, voltage_v=14.2)
    assert "14,2 V" in format_estado(conn, NOW, TZ)
