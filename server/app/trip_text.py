"""Spanish texts and keyboards for the trip commands."""
import html

from app import fmt
from app.trips import Trip


def _minutes(ms: int) -> int:
    return max(1, round(ms / 60_000))


KEYCAPS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟")


def _keycap(i: int) -> str:
    return KEYCAPS[i - 1] if 1 <= i <= len(KEYCAPS) else f"{i}."


def format_trip_list(trips: list[Trip], now_ms: int, tz: str) -> str:
    lines = ["🚗 <b>Últimos trayectos</b>"]
    current = None
    for i, t in enumerate(trips, 1):
        label = fmt.day_label(t.start_ts, now_ms, tz)
        if label != current:
            current = label
            lines += ["", f"<b>{html.escape(label)}</b>"]
        lines.append(
            f"{_keycap(i)} {fmt.hhmm(t.start_ts, tz)} → {fmt.hhmm(t.end_ts, tz)}"
            f" · <b>{fmt.num(t.distance_m / 1000, 1)} km</b> · {_minutes(t.duration_ms)} min"
        )
    return "\n".join(lines)


def trip_list_keyboard(trips: list[Trip], has_more: bool) -> dict | None:
    if not trips:
        return None
    rows = [[{"text": _keycap(i), "callback_data": f"trip:{t.id}"} for i, t in enumerate(trips, 1)]]
    if has_more:
        rows.append(
            [{"text": "⬅️ Anteriores", "callback_data": f"trips:{trips[-1].start_ts}"}]
        )
    return {"inline_keyboard": rows}


def format_trip_detail(trip: Trip, tz: str, has_route: bool) -> str:
    blocks = [
        f"🚗 <b>{fmt.full_day(trip.start_ts, tz)}</b>\n"
        f"🕒 {fmt.hhmm(trip.start_ts, tz)} → {fmt.hhmm(trip.end_ts, tz)}"
        f" · {_minutes(trip.duration_ms)} min"
    ]
    dist = f"📏 <b>{fmt.num(trip.distance_m / 1000, 1)} km</b> · media {fmt.num(trip.avg_kmh)} km/h"
    if trip.max_kmh is not None:
        dist += f" · máx. {fmt.num(trip.max_kmh)} km/h"
    blocks.append(dist)
    if trip.has_obd:
        pct = trip.idle_ms / trip.duration_ms * 100 if trip.duration_ms > 0 else 0
        motor = [
            "⚙️ <b>Motor</b>",
            f"• Ralentí: {fmt.num(round(trip.idle_ms / 60_000))} min ({fmt.num(pct)} %)",
        ]
        if trip.coolant_start is not None and trip.coolant_max is not None:
            motor.append(
                f"• Temperatura: de {fmt.num(trip.coolant_start)} a {fmt.num(trip.coolant_max)} °C"
            )
        if trip.rpm_avg is not None and trip.rpm_max is not None:
            motor.append(
                f"• Revoluciones: media {fmt.num(trip.rpm_avg)} · máx. {fmt.num(trip.rpm_max)} rpm"
            )
        blocks.append("\n".join(motor))
    else:
        blocks.append("⚙️ Sin datos del motor en este trayecto")
    if trip.new_dtcs is not None:
        codes = ", ".join(html.escape(c) for c in trip.new_dtcs) if trip.new_dtcs else "ninguna"
        blocks.append("⚠️ Averías nuevas: " + codes)
    if not has_route:
        blocks.append("📎 Sin posiciones GPS válidas para la ruta")
    return "\n\n".join(blocks)
