"""Read-only statistics for the web panel, derived from trips and records."""
import calendar
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app import dtc as dtc_mod
from app.journeys import Item, JourneyView
from app.trips import Trip, get_trip

_MONTH_RE = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


def parse_month(s: str) -> tuple[int, int]:
    if not _MONTH_RE.fullmatch(s):
        raise ValueError(f"invalid month: {s!r}")
    year = int(s[:4])
    if year < 2000:
        raise ValueError(f"invalid month: {s!r}")
    return year, int(s[5:])


def _local(ts_ms: int, tz: str) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, ZoneInfo(tz))


def current_month(now_ms: int, tz: str) -> tuple[int, int]:
    d = _local(now_ms, tz)
    return d.year, d.month


def month_key(ts_ms: int, tz: str) -> str:
    return _local(ts_ms, tz).strftime("%Y-%m")


def date_key(ts_ms: int, tz: str) -> str:
    return _local(ts_ms, tz).strftime("%Y-%m-%d")


def _km(distance_m: float) -> float:
    return round(distance_m / 1000, 1)


def _round(x: float | None) -> int | None:
    return None if x is None else round(x)


def _round1(x: float | None) -> float | None:
    return None if x is None else round(x, 1)


def items_in_month(items: list[Item], year: int, month: int, tz: str) -> list[Item]:
    key = f"{year:04d}-{month:02d}"
    return [t for t in items if month_key(t.start_ts, tz) == key]


trips_in_month = items_in_month


def totals(trips: list[Item]) -> dict:
    speeds = [t.max_kmh for t in trips if t.max_kmh is not None]
    return {
        "km": _km(sum(t.distance_m for t in trips)),
        "trips": len(trips),
        "drive_ms": sum(t.drive_ms for t in trips),
        "max_kmh": _round(max(speeds)) if speeds else None,
    }


def months_series(
    trips: list[Item], year: int, month: int, tz: str, count: int = 12
) -> list[dict]:
    keys = []
    idx = year * 12 + (month - 1)
    for i in range(idx - count + 1, idx + 1):
        keys.append(f"{i // 12:04d}-{i % 12 + 1:02d}")
    acc = {k: {"dist": 0.0, "trips": 0, "drive_ms": 0} for k in keys}
    for t in trips:
        a = acc.get(month_key(t.start_ts, tz))
        if a is not None:
            a["dist"] += t.distance_m
            a["trips"] += 1
            a["drive_ms"] += t.drive_ms
    return [
        {"month": k, "km": _km(a["dist"]), "trips": a["trips"], "drive_ms": a["drive_ms"]}
        for k, a in acc.items()
    ]


def days_series(
    trips: list[Item], year: int, month: int, tz: str, days: int = 365
) -> list[dict]:
    end = date(year, month, calendar.monthrange(year, month)[1])
    start = end - timedelta(days=days - 1)
    acc: dict[str, dict] = {}
    for t in trips:
        key = date_key(t.start_ts, tz)
        if not start.isoformat() <= key <= end.isoformat():
            continue
        a = acc.setdefault(key, {"dist": 0.0, "trips": 0})
        a["dist"] += t.distance_m
        a["trips"] += 1
    return [
        {"date": k, "km": _km(acc[k]["dist"]), "trips": acc[k]["trips"]} for k in sorted(acc)
    ]


def trip_summary(trip: Trip) -> dict:
    return {
        "id": trip.id,
        "start_ts": trip.start_ts,
        "end_ts": trip.end_ts,
        "km": _km(trip.distance_m),
        "duration_ms": trip.duration_ms,
        "drive_ms": trip.drive_ms,
        "avg_kmh": round(trip.avg_kmh),
        "max_kmh": _round(trip.max_kmh),
        "has_obd": trip.has_obd,
        "new_dtcs": trip.new_dtcs,
    }


def _stop_dicts(view: JourneyView) -> list[dict]:
    return [
        {"start_ts": st.start_ts, "end_ts": st.end_ts, "duration_ms": st.duration_ms}
        for st in view.stops
    ]


def item_summary(item: Item) -> dict:
    if isinstance(item, JourneyView):
        return {
            "kind": "journey",
            "id": item.id,
            "start_ts": item.start_ts,
            "end_ts": item.end_ts,
            "km": _km(item.distance_m),
            "duration_ms": item.duration_ms,
            "drive_ms": item.drive_ms,
            "avg_kmh": round(item.avg_kmh),
            "max_kmh": _round(item.max_kmh),
            "has_obd": item.has_obd,
            "new_dtcs": item.new_dtcs,
            "segments": [trip_summary(s) for s in item.segments],
            "stops": _stop_dicts(item),
        }
    return {"kind": "trip", **trip_summary(item)}


def with_gaps(items_newest_first: list[Item], tz: str) -> list[dict]:
    out = []
    items = items_newest_first
    for i, item in enumerate(items):
        gap = None
        if i + 1 < len(items):
            prev = items[i + 1]
            if date_key(item.start_ts, tz) == date_key(prev.end_ts, tz):
                gap = item.start_ts - prev.end_ts
        out.append({**item_summary(item), "gap_before_ms": gap})
    return out


def _series(conn: sqlite3.Connection, trip: Trip) -> dict:
    rows = [
        (ts, (json.loads(d).get("values") or {}))
        for ts, d in conn.execute(
            "SELECT ts, data FROM records WHERE type='obd'"
            " AND ts BETWEEN ? AND ? ORDER BY ts, seq",
            (trip.start_ts, trip.end_ts),
        )
    ]
    if any(v.get("speed_kmh") is not None for _, v in rows):
        return {
            "ts": [ts for ts, _ in rows],
            "speed_kmh": [_round1(v.get("speed_kmh")) for _, v in rows],
            "rpm": [_round(v.get("rpm")) for _, v in rows],
            "coolant_c": [_round(v.get("coolant_c")) for _, v in rows],
        }
    return {
        "ts": [p.ts for p in trip.points],
        "speed_kmh": [
            None if p.speed_mps is None else round(p.speed_mps * 3.6, 1) for p in trip.points
        ],
        "rpm": [None] * len(trip.points),
        "coolant_c": [None] * len(trip.points),
    }


def trip_detail(conn: sqlite3.Connection, trip: Trip) -> dict:
    return {
        **trip_summary(trip),
        "new_dtcs_desc": _described(trip.new_dtcs or []),
        "idle_ms": trip.idle_ms,
        "coolant_start": _round(trip.coolant_start),
        "coolant_max": _round(trip.coolant_max),
        "rpm_avg": _round(trip.rpm_avg),
        "rpm_max": _round(trip.rpm_max),
        "points": [[round(p.lat, 6), round(p.lon, 6), p.ts] for p in trip.points],
        "series": _series(conn, trip),
    }


def journey_detail(conn: sqlite3.Connection, view: JourneyView) -> dict | None:
    """Detail of a journey; None if a segment can no longer be loaded."""
    segs = []
    for seg in view.segments:
        full = get_trip(conn, seg.id)
        if full is None:
            return None
        segs.append(full)
    series: dict[str, list] = {"ts": [], "speed_kmh": [], "rpm": [], "coolant_c": []}
    stops = []
    for i, full in enumerate(segs):
        if i > 0:
            st = view.stops[i - 1]
            last = segs[i - 1].points[-1] if segs[i - 1].points else None
            stops.append({
                "start_ts": st.start_ts, "end_ts": st.end_ts, "duration_ms": st.duration_ms,
                "lat": None if last is None else round(last.lat, 6),
                "lon": None if last is None else round(last.lon, 6),
            })
            series["ts"].append(st.start_ts + 1)
            for k in ("speed_kmh", "rpm", "coolant_c"):
                series[k].append(None)
        part = _series(conn, full)
        for k in series:
            series[k].extend(part[k])
    seg_details = []
    for full in segs:
        d = trip_detail(conn, full)
        del d["series"]
        seg_details.append(d)
    return {
        **item_summary(view),
        "new_dtcs_desc": _described(view.new_dtcs or []),
        "idle_ms": view.idle_ms,
        "coolant_start": _round(view.coolant_start),
        "coolant_max": _round(view.coolant_max),
        "rpm_avg": _round(view.rpm_avg),
        "rpm_max": _round(view.rpm_max),
        "segments": seg_details,
        "stops": stops,
        "series": series,
    }


def _described(codes: list[str]) -> list[dict]:
    return [{"code": c, "desc": dtc_mod.describe(c)} for c in codes]


def dtc_state(conn: sqlite3.Connection) -> dict | None:
    latest = dtc_mod.latest_dtc(conn)
    if latest is None:
        return None
    ts, active, pending = latest
    return {"ts": ts, "active": _described(active), "pending": _described(pending)}


def dtc_history(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT ts, type, data FROM records"
        " WHERE type='dtc' OR (type='event' AND json_extract(data, '$.event')='dtc_clear')"
        " ORDER BY ts, seq"
    ).fetchall()
    out: list[dict] = []
    prev: list[str] = []
    for ts, type_, raw in rows:
        if type_ == "event":
            out.append({"ts": ts, "kind": "cleared", "codes": []})
            continue
        d = json.loads(raw)
        cur = list(dict.fromkeys([*(d.get("active") or []), *(d.get("pending") or [])]))
        appeared = [c for c in cur if c not in prev]
        gone = [c for c in prev if c not in cur]
        if appeared:
            out.append({"ts": ts, "kind": "appeared", "codes": appeared})
        if gone:
            out.append({"ts": ts, "kind": "gone", "codes": gone})
        prev = cur
    out.reverse()
    return out[:limit]
