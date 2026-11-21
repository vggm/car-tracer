"""Spanish texts and keyboards for the trip commands."""
from app import fmt
from app.trips import Trip


def _minutes(ms: int) -> int:
    return max(1, round(ms / 60_000))


def format_trip_list(trips: list[Trip], now_ms: int, tz: str) -> str:
    lines = ["🚗 Últimos trayectos"]
    for i, t in enumerate(trips, 1):
        lines.append(
            f"{i}. {fmt.day_label(t.start_ts, now_ms, tz)} {fmt.hhmm(t.start_ts, tz)}"
            f" → {fmt.hhmm(t.end_ts, tz)} · {_minutes(t.duration_ms)} min"
            f" · {fmt.num(t.distance_m / 1000, 1)} km"
        )
    return "\n".join(lines)


def trip_list_keyboard(trips: list[Trip], has_more: bool) -> dict | None:
    if not trips:
        return None
    rows = [[{"text": str(i), "callback_data": f"trip:{t.id}"} for i, t in enumerate(trips, 1)]]
    if has_more:
        rows.append(
            [{"text": "⬅️ Anteriores", "callback_data": f"trips:{trips[-1].start_ts}"}]
        )
    return {"inline_keyboard": rows}


def format_trip_detail(trip: Trip, tz: str, has_route: bool) -> str:
    lines = [
        f"🚗 Trayecto del {fmt.long_day(trip.start_ts, tz)}",
        f"🕒 {fmt.hhmm(trip.start_ts, tz)} → {fmt.hhmm(trip.end_ts, tz)}"
        f" ({_minutes(trip.duration_ms)} min)",
    ]
    dist = f"📏 {fmt.num(trip.distance_m / 1000, 1)} km · media {fmt.num(trip.avg_kmh)} km/h"
    if trip.max_kmh is not None:
        dist += f" · máx. {fmt.num(trip.max_kmh)} km/h"
    lines.append(dist)
    if trip.has_obd:
        pct = trip.idle_ms / trip.duration_ms * 100 if trip.duration_ms > 0 else 0
        lines.append(
            f"⏸️ Al ralentí: {fmt.num(round(trip.idle_ms / 60_000))} min ({fmt.num(pct)} %)"
        )
        if trip.coolant_start is not None and trip.coolant_max is not None:
            lines.append(
                f"🌡️ Motor: de {fmt.num(trip.coolant_start)} °C a {fmt.num(trip.coolant_max)} °C"
            )
        if trip.rpm_avg is not None and trip.rpm_max is not None:
            lines.append(
                f"⚙️ Revoluciones: media {fmt.num(trip.rpm_avg)} · máx. {fmt.num(trip.rpm_max)} rpm"
            )
    else:
        lines.append("Sin datos del motor en este trayecto")
    if trip.new_dtcs is not None:
        lines.append(
            "⚠️ Averías nuevas: " + (", ".join(trip.new_dtcs) if trip.new_dtcs else "ninguna")
        )
    if not has_route:
        lines.append("📎 Sin posiciones GPS válidas para la ruta")
    return "\n".join(lines)
