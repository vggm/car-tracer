"""Text behind the /estado command."""
import json
import sqlite3

from app import fmt
from app.dtc import group_codes, latest_dtc
from app.location import ENGINE_ON_VOLTAGE

MAX_OBD_SCAN = 2000


def _latest_values(conn: sqlite3.Connection, keys: tuple[str, ...]) -> tuple[int, dict] | None:
    for ts, data in conn.execute(
        "SELECT ts, data FROM records WHERE type='obd'"
        " ORDER BY ts DESC, rowid DESC LIMIT ?",
        (MAX_OBD_SCAN,),
    ):
        values = json.loads(data).get("values") or {}
        if any(values.get(k) is not None for k in keys):
            return ts, values
    return None


def format_estado(conn: sqlite3.Connection, now_ms: int, tz: str) -> str:
    engine = _latest_values(conn, ("coolant_c", "rpm"))
    volt = _latest_values(conn, ("voltage_v",))
    if engine is None and volt is None:
        return "Todavía no hay datos del motor."
    newest = max(t[0] for t in (engine, volt) if t is not None)
    lines = [
        f"🔧 Estado del coche · datos de {fmt.when(newest, now_ms, tz)}"
        f" (hace {fmt.rel(now_ms - newest)})"
    ]
    if engine is not None:
        v = engine[1]
        if v.get("coolant_c") is not None:
            lines.append(f"🌡️ Motor: {fmt.num(v['coolant_c'])} °C")
    if volt is not None:
        volts = float(volt[1]["voltage_v"])
        text = f"🔋 Batería: {fmt.num(volts, 1)} V"
        if volts >= ENGINE_ON_VOLTAGE:
            text += " (cargando)"
        lines.append(text)
    if engine is not None and engine[1].get("rpm") is not None:
        lines.append(f"⚙️ Revoluciones: {fmt.num(engine[1]['rpm'])} rpm")
    dtc = latest_dtc(conn)
    if dtc is not None:
        confirmed, watching = group_codes(dtc[1], dtc[2])
        parts = []
        if confirmed:
            n = len(confirmed)
            parts.append(f"{n} confirmada" if n == 1 else f"{n} confirmadas")
        if watching:
            parts.append(f"{len(watching)} en observación")
        if parts:
            lines.append(f"⚠️ Averías: {', '.join(parts)} · /averias")
        else:
            lines.append("✅ Sin averías")
    return "\n".join(lines)
