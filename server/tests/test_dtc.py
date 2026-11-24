import json

from app import db, dtc, fmt

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


def test_group_codes():
    assert dtc.group_codes(["P0401", "P0409"], ["P0401", "P1351"]) == (
        [("P0401", True), ("P0409", False)], ["P1351"])
    assert dtc.group_codes([], ["P1", "P2", "P1"]) == ([], ["P1", "P2"])
    assert dtc.group_codes(["P1", "P1", "P2"], []) == ([("P1", False), ("P2", False)], [])


def test_format_codes_suffix():
    assert dtc.format_codes(["P0401"], suffix=" · sigue fallando") == [
        "• P0401 · Flujo insuficiente de recirculación de gases (EGR) · sigue fallando"
    ]


def test_averias_never_read(tmp_path):
    assert dtc.format_averias(_conn(tmp_path), NOW, TZ) == "Todavía no se han leído las averías."


def test_averias_example(tmp_path):
    c = _conn(tmp_path)
    add_dtc(c, NOW - 60_000, ["P0401", "P1162", "P0490", "P0409"],
            ["P0401", "P1162", "P0490", "P0409", "P1351"])
    when = fmt.when(NOW - 60_000, NOW, TZ)
    assert dtc.format_averias(c, NOW, TZ) == (
        f"⚠️ Averías · leídas {when}\n"
        "\n"
        "🔴 Confirmadas (4)\n"
        "• P0401 · Flujo insuficiente de recirculación de gases (EGR) · sigue fallando\n"
        "• P1162 · Código de Peugeot sin descripción en el catálogo · sigue fallando\n"
        "• P0490 · Circuito de control de la EGR: señal alta · sigue fallando\n"
        "• P0409 · Circuito del sensor de la EGR · sigue fallando\n"
        "\n"
        "🟡 En observación (1)\n"
        "• P1351 · Relé de los calentadores (código de Peugeot)"
    )


def test_averias_empty(tmp_path):
    c = _conn(tmp_path)
    add_dtc(c, NOW - 60_000, [], [])
    assert dtc.format_averias(c, NOW, TZ) == (
        f"✅ Sin averías · leídas {fmt.when(NOW - 60_000, NOW, TZ)}"
    )


def test_averias_confirmed_only_not_recurring(tmp_path):
    c = _conn(tmp_path)
    add_dtc(c, NOW - 60_000, ["P0401"], [])
    assert dtc.format_averias(c, NOW, TZ) == (
        f"⚠️ Averías · leídas {fmt.when(NOW - 60_000, NOW, TZ)}\n"
        "\n"
        "🔴 Confirmadas (1)\n"
        "• P0401 · Flujo insuficiente de recirculación de gases (EGR)"
    )


def test_averias_watching_only(tmp_path):
    c = _conn(tmp_path)
    add_dtc(c, NOW - 60_000, [], ["P0420"])
    out = dtc.format_averias(c, NOW, TZ)
    assert out == (
        f"⚠️ Averías · leídas {fmt.when(NOW - 60_000, NOW, TZ)}\n"
        "\n"
        "🟡 En observación (1)\n"
        "• P0420 · Eficiencia del catalizador por debajo del umbral (banco 1)"
    )
    assert "Confirmadas" not in out
