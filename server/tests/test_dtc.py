import json

from app import db, dtc

TZ = "Europe/Madrid"
NOW = 1_795_000_000_000  # fixed instant
_n = [0]


def _conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))


def add_dtc(conn, ts, active, pending):
    _n[0] += 1
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (f"d{_n[0]}", "d", "s", _n[0], ts, "dtc",
         json.dumps({"active": active, "pending": pending}), ts),
    )


def test_describe():
    assert dtc.describe("P0401") == "Flujo insuficiente de recirculación de gases (EGR)"
    assert dtc.describe("P1351") == "Relé de los calentadores (código de Peugeot)"
    assert dtc.describe("P1162") == "Código de Peugeot sin descripción en el catálogo"
    assert dtc.describe("P0999") == "Código sin descripción en el catálogo"


def test_catalog_required_and_excluded():
    assert dtc.CATALOG["P0409"] == "Circuito del sensor de la EGR"
    assert dtc.CATALOG["P0490"] == "Circuito de control de la EGR: señal alta"
    assert "P1162" not in dtc.CATALOG


def test_format_codes():
    assert dtc.format_codes(["P0401"]) == [
        "• P0401 · Flujo insuficiente de recirculación de gases (EGR)"
    ]
    assert dtc.format_codes(["P0420"], {"P0420"})[0].startswith("• 🆕 P0420 · ")


def test_latest_dtc(tmp_path):
    c = _conn(tmp_path)
    assert dtc.latest_dtc(c) is None
    add_dtc(c, 1000, ["P0401"], [])
    add_dtc(c, 2000, ["P0401", "P1351"], ["P0401"])
    assert dtc.latest_dtc(c) == (2000, ["P0401", "P1351"], ["P0401"])


def test_averias_never_read(tmp_path):
    assert dtc.format_averias(_conn(tmp_path), NOW, TZ) == "Todavía no se han leído las averías."


def test_averias_example_same_pending(tmp_path):
    c = _conn(tmp_path)
    add_dtc(c, NOW - 60_000, ["P0401", "P1351"], ["P0401", "P1351"])
    from app import fmt
    when = fmt.when(NOW - 60_000, NOW, TZ)
    assert dtc.format_averias(c, NOW, TZ) == (
        f"⚠️ Averías guardadas · leídas {when}\n"
        "• P0401 · Flujo insuficiente de recirculación de gases (EGR)\n"
        "• P1351 · Relé de los calentadores (código de Peugeot)\n"
        "Pendientes: las mismas."
    )


def test_averias_empty(tmp_path):
    c = _conn(tmp_path)
    add_dtc(c, NOW - 60_000, [], [])
    from app import fmt
    assert dtc.format_averias(c, NOW, TZ) == (
        f"✅ Sin averías guardadas · leídas {fmt.when(NOW - 60_000, NOW, TZ)}"
    )


def test_averias_pending_different(tmp_path):
    c = _conn(tmp_path)
    add_dtc(c, NOW - 60_000, ["P0401"], ["P0409"])
    from app import fmt
    assert dtc.format_averias(c, NOW, TZ) == (
        f"⚠️ Averías guardadas · leídas {fmt.when(NOW - 60_000, NOW, TZ)}\n"
        "• P0401 · Flujo insuficiente de recirculación de gases (EGR)\n"
        "Pendientes:\n"
        "• P0409 · Circuito del sensor de la EGR"
    )


def test_averias_pending_only(tmp_path):
    c = _conn(tmp_path)
    add_dtc(c, NOW - 60_000, [], ["P0409"])
    from app import fmt
    assert dtc.format_averias(c, NOW, TZ) == (
        f"⚠️ Averías guardadas · leídas {fmt.when(NOW - 60_000, NOW, TZ)}\n"
        "Pendientes:\n"
        "• P0409 · Circuito del sensor de la EGR"
    )


def test_averias_no_pending_line_omitted(tmp_path):
    c = _conn(tmp_path)
    add_dtc(c, NOW - 60_000, ["P0401"], [])
    assert "Pendientes" not in dtc.format_averias(c, NOW, TZ)
