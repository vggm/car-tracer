"""DTC catalog (SAE J2012 generic titles, Spanish) and /averias text."""
import json
import sqlite3

from app import fmt

_SENSOR = {
    "P0100": "Circuito del sensor de masa de aire (MAF)",
    "P0101": "Rango/funcionamiento del sensor de masa de aire (MAF)",
    "P0102": "Circuito del sensor de masa de aire (MAF): señal baja",
    "P0103": "Circuito del sensor de masa de aire (MAF): señal alta",
    "P0104": "Circuito del sensor de masa de aire (MAF): intermitente",
    "P0105": "Circuito del sensor de presión del colector (MAP)",
    "P0106": "Rango/funcionamiento del sensor de presión del colector (MAP)",
    "P0107": "Circuito del sensor de presión del colector (MAP): señal baja",
    "P0108": "Circuito del sensor de presión del colector (MAP): señal alta",
    "P0109": "Circuito del sensor de presión del colector (MAP): intermitente",
    "P0110": "Circuito del sensor de temperatura del aire de admisión (IAT)",
    "P0111": "Rango/funcionamiento del sensor de temperatura del aire de admisión (IAT)",
    "P0112": "Circuito del sensor de temperatura del aire de admisión (IAT): señal baja",
    "P0113": "Circuito del sensor de temperatura del aire de admisión (IAT): señal alta",
    "P0114": "Circuito del sensor de temperatura del aire de admisión (IAT): intermitente",
    "P0115": "Circuito del sensor de temperatura del refrigerante (ECT)",
    "P0116": "Rango/funcionamiento del sensor de temperatura del refrigerante (ECT)",
    "P0117": "Circuito del sensor de temperatura del refrigerante (ECT): señal baja",
    "P0118": "Circuito del sensor de temperatura del refrigerante (ECT): señal alta",
}

CATALOG: dict[str, str] = {
    **_SENSOR,
    "P0190": "Circuito del sensor de presión del raíl de combustible",
    "P0191": "Rango/funcionamiento del sensor de presión del raíl de combustible",
    "P0192": "Circuito del sensor de presión del raíl de combustible: señal baja",
    "P0193": "Circuito del sensor de presión del raíl de combustible: señal alta",
    "P0234": "Sobrepresión del turbo",
    "P0299": "Presión insuficiente del turbo",
    "P0300": "Fallos de encendido aleatorios o múltiples detectados",
    "P0301": "Fallo de encendido detectado en el cilindro 1",
    "P0302": "Fallo de encendido detectado en el cilindro 2",
    "P0303": "Fallo de encendido detectado en el cilindro 3",
    "P0304": "Fallo de encendido detectado en el cilindro 4",
    "P0380": "Circuito A de los calentadores",
    "P0381": "Circuito del testigo de los calentadores",
    "P0382": "Circuito B de los calentadores",
    "P0383": "Circuito de control del módulo de los calentadores: señal baja",
    "P0384": "Circuito de control del módulo de los calentadores: señal alta",
    "P0400": "Flujo de recirculación de gases (EGR)",
    "P0401": "Flujo insuficiente de recirculación de gases (EGR)",
    "P0402": "Flujo excesivo de recirculación de gases (EGR)",
    "P0403": "Circuito de control de la EGR",
    "P0404": "Rango/funcionamiento del circuito de control de la EGR",
    "P0405": "Circuito del sensor A de la EGR: señal baja",
    "P0406": "Circuito del sensor A de la EGR: señal alta",
    "P0407": "Circuito del sensor B de la EGR: señal baja",
    "P0408": "Circuito del sensor B de la EGR: señal alta",
    "P0409": "Circuito del sensor de la EGR",
    "P0420": "Eficiencia del catalizador por debajo del umbral (banco 1)",
    "P0490": "Circuito de control de la EGR: señal alta",
    "P0500": "Sensor de velocidad del vehículo (VSS)",
    "P0505": "Sistema de control del ralentí",
    "P0560": "Tensión del sistema",
    "P0561": "Tensión del sistema inestable",
    "P0562": "Tensión del sistema baja",
    "P0563": "Tensión del sistema alta",
    "P1351": "Relé de los calentadores",
    "P2002": "Eficiencia del filtro de partículas por debajo del umbral (banco 1)",
    "P2463": "Filtro de partículas: acumulación de hollín",
}


def describe(code: str) -> str:
    desc = CATALOG.get(code)
    if code.startswith("P1"):
        return f"{desc} (código de Peugeot)" if desc else "Código de Peugeot sin descripción en el catálogo"
    return desc or "Código sin descripción en el catálogo"


def latest_dtc(conn: sqlite3.Connection) -> tuple[int, list[str], list[str]] | None:
    row = conn.execute(
        "SELECT ts, data FROM records WHERE type='dtc' ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    d = json.loads(row[1])
    return row[0], list(d.get("active") or []), list(d.get("pending") or [])


def group_codes(
    active: list[str], pending: list[str]
) -> tuple[list[tuple[str, bool]], list[str]]:
    """Split into (confirmed as (code, recurring), watching). Deduped, order kept."""
    act = list(dict.fromkeys(active))
    pend = list(dict.fromkeys(pending))
    pend_set, act_set = set(pend), set(act)
    confirmed = [(c, c in pend_set) for c in act]
    watching = [c for c in pend if c not in act_set]
    return confirmed, watching


def format_codes(
    codes: list[str], mark_new: set[str] = frozenset(), suffix: str = ""
) -> list[str]:
    return [
        f"• {'🆕 ' if c in mark_new else ''}{c} · {describe(c)}{suffix}" for c in codes
    ]


def format_averias(conn: sqlite3.Connection, now_ms: int, tz: str) -> str:
    latest = latest_dtc(conn)
    if latest is None:
        return "Todavía no se han leído las averías."
    ts, active, pending = latest
    when = fmt.when(ts, now_ms, tz)
    confirmed, watching = group_codes(active, pending)
    if not confirmed and not watching:
        return f"✅ Sin averías · leídas {when}"
    lines = [f"⚠️ Averías · leídas {when}"]
    if confirmed:
        lines += ["", f"🔴 Confirmadas ({len(confirmed)})"]
        for code, recurring in confirmed:
            lines += format_codes([code], suffix=" · sigue fallando" if recurring else "")
    if watching:
        lines += ["", f"🟡 En observación ({len(watching)})", *format_codes(watching)]
    return "\n".join(lines)
