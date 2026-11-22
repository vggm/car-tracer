"""Read-only statistics for the web panel, derived from trips and records."""
import calendar
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app import dtc as dtc_mod
from app.trips import Trip

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


def trips_in_month(trips: list[Trip], year: int, month: int, tz: str) -> list[Trip]:
    key = f"{year:04d}-{month:02d}"
    return [t for t in trips if month_key(t.start_ts, tz) == key]


def totals(trips: list[Trip]) -> dict:
    speeds = [t.max_kmh for t in trips if t.max_kmh is not None]
    return {
        "km": _km(sum(t.distance_m for t in trips)),
        "trips": len(trips),
        "drive_ms": sum(t.duration_ms for t in trips),
        "max_kmh": _round(max(speeds)) if speeds else None,
    }


def months_series(
    trips: list[Trip], year: int, month: int, tz: str, count: int = 12
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
            a["drive_ms"] += t.duration_ms
    return [
        {"month": k, "km": _km(a["dist"]), "trips": a["trips"], "drive_ms": a["drive_ms"]}
        for k, a in acc.items()
    ]


def days_series(
    trips: list[Trip], year: int, month: int, tz: str, days: int = 365
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
        "avg_kmh": round(trip.avg_kmh),
        "max_kmh": _round(trip.max_kmh),
        "has_obd": trip.has_obd,
        "new_dtcs": trip.new_dtcs,
    }


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
