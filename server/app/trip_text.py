"""Spanish texts and keyboards for the trip commands."""
import html
from urllib.parse import urlencode

from app import fmt
from app.location import GpsPoint, _haversine_m
from app.trips import Trip

MAPS_WAYPOINTS = 8
MAPS_BUTTON_TEXT = "🗺️ Ver en Google Maps"


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


def _coord(p: GpsPoint) -> str:
    return f"{p.lat:.5f},{p.lon:.5f}"


def maps_url(points: list[GpsPoint]) -> str | None:
    """Google Maps directions URL approximating the route, or None without a route."""
    if len(points) < 2:
        return None
    cum = [0.0]
    for prev, cur in zip(points, points[1:]):
        cum.append(cum[-1] + _haversine_m(prev, cur))
    total = cum[-1]
    if total <= 0:
        return None
    origin, destination = _coord(points[0]), _coord(points[-1])
    seen = {origin, destination}
    waypoints: list[str] = []
    idx = 0
    for k in range(1, MAPS_WAYPOINTS + 1):
        target = total * k / (MAPS_WAYPOINTS + 1)
        while idx < len(points) - 1 and cum[idx] < target:
            idx += 1
        # pick the nearer of the two points around the target distance
        best = idx if idx == 0 or cum[idx] - target <= target - cum[idx - 1] else idx - 1
        c = _coord(points[best])
        if c not in seen:
            seen.add(c)
            waypoints.append(c)
    params = [("api", "1"), ("origin", origin), ("destination", destination),
              ("travelmode", "driving")]
    if waypoints:
        params.append(("waypoints", "|".join(waypoints)))
    return "https://www.google.com/maps/dir/?" + urlencode(params)


def trip_detail_keyboard(points: list[GpsPoint]) -> dict | None:
    url = maps_url(points)
    if url is None:
        return None
    return {"inline_keyboard": [[{"text": MAPS_BUTTON_TEXT, "url": url}]]}


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
