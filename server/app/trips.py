"""Pure logic behind the trip commands: segment records into trips and compute stats."""
import json
import sqlite3
from dataclasses import dataclass

from app.location import (
    DRIVING_SQL,
    MAX_ACC_M,
    MAX_SPEED_MPS,
    MOVING_MIN_KMH,
    GpsPoint,
    _haversine_m,
)

TRIP_GAP_MS = 120_000
MIN_TRIP_M = 300.0
MIN_HOP_M = 20.0
IDLE_STEP_CAP_MS = 10_000
PAGE_SIZE = 5


@dataclass(frozen=True)
class Trip:
    id: str
    start_ts: int
    end_ts: int
    distance_m: float
    max_kmh: float | None
    has_obd: bool
    idle_ms: int
    coolant_start: float | None
    coolant_max: float | None
    rpm_avg: float | None
    rpm_max: float | None
    new_dtcs: list[str] | None
    points: list[GpsPoint]
    rpm_n: int = 0  # samples with rpm > 0

    @property
    def duration_ms(self) -> int:
        return self.end_ts - self.start_ts

    @property
    def drive_ms(self) -> int:
        return self.duration_ms

    @property
    def avg_kmh(self) -> float:
        if self.duration_ms <= 0:
            return 0.0
        return self.distance_m / (self.duration_ms / 1000.0) * 3.6


def valid_points(points_oldest_first: list[GpsPoint]) -> list[GpsPoint]:
    """Apply the /donde filters oldest to newest: acc, not (0, 0), implied speed."""
    out: list[GpsPoint] = []
    for p in points_oldest_first:
        if p.acc_m > MAX_ACC_M or (abs(p.lat) < 1e-6 and abs(p.lon) < 1e-6):
            continue
        if out:
            dist = _haversine_m(p, out[-1])
            dt = (p.ts - out[-1].ts) / 1000.0
            if (dist >= 1.0) if dt <= 0 else (dist / dt > MAX_SPEED_MPS):
                continue
        out.append(p)
    return out


def _distance_m(points: list[GpsPoint]) -> float:
    total = 0.0
    for prev, cur in zip(points, points[1:]):
        hop = _haversine_m(prev, cur)
        moving = cur.speed_mps is not None and cur.speed_mps * 3.6 >= MOVING_MIN_KMH
        if moving or hop >= MIN_HOP_M:
            total += hop
    return total


def _codes(data: dict) -> list[str]:
    return list(dict.fromkeys([*(data.get("active") or []), *(data.get("pending") or [])]))


def _build(conn: sqlite3.Connection, rows: list[tuple[int, str, dict]]) -> Trip | None:
    """rows: one segment of (ts, type, data), ordered by ts."""
    start_ts, end_ts = rows[0][0], rows[-1][0]
    gps_pts = [
        GpsPoint(ts, d["lat"], d["lon"], d["acc_m"], d.get("speed_mps"))
        for ts, t, d in rows
        if t == "gps" and None not in (d.get("lat"), d.get("lon"), d.get("acc_m"))
    ]
    points = valid_points(gps_pts)
    distance = _distance_m(points)
    if distance < MIN_TRIP_M:
        return None

    obd = [(ts, d.get("values") or {}) for ts, t, d in rows if t == "obd"]
    rpms = [float(v["rpm"]) for _, v in obd if v.get("rpm") is not None]
    if rpms and not any(r > 0 for r in rpms):
        return None

    obd_speeds = [float(v["speed_kmh"]) for _, v in obd if v.get("speed_kmh") is not None]
    if obd_speeds:
        max_kmh: float | None = max(obd_speeds)
    else:
        gps_speeds = [p.speed_mps * 3.6 for p in points if p.speed_mps is not None]
        max_kmh = max(gps_speeds) if gps_speeds else None

    idle_ms = 0
    for (t0, v0), (t1, _) in zip(obd, obd[1:]):
        # a sample without speed_kmh is not idle (the app sends it with rpm when the ECU supports it)
        speed = v0.get("speed_kmh")
        if (v0.get("rpm") or 0) > 0 and speed is not None and speed < MOVING_MIN_KMH:
            idle_ms += min(t1 - t0, IDLE_STEP_CAP_MS)

    coolants = [float(v["coolant_c"]) for _, v in obd if v.get("coolant_c") is not None]
    running = [r for r in rpms if r > 0]

    dtc_rows = [d for _, t, d in rows if t == "dtc"]
    new_dtcs: list[str] | None = None
    if dtc_rows:
        prev = conn.execute(
            "SELECT data FROM records WHERE type='dtc' AND ts < ? ORDER BY ts DESC LIMIT 1",
            (start_ts,),
        ).fetchone()
        if prev:
            known = set(_codes(json.loads(prev[0])))
            new_dtcs = [c for c in _codes(dtc_rows[-1]) if c not in known]

    return Trip(
        id=str(start_ts),
        start_ts=start_ts,
        end_ts=end_ts,
        distance_m=distance,
        max_kmh=max_kmh,
        has_obd=bool(rpms),
        idle_ms=idle_ms,
        coolant_start=coolants[0] if coolants else None,
        coolant_max=max(coolants) if coolants else None,
        rpm_avg=sum(running) / len(running) if running else None,
        rpm_max=max(running) if running else None,
        new_dtcs=new_dtcs,
        points=points,
        rpm_n=len(running),
    )


@dataclass(frozen=True)
class SessionSpan:
    session_id: str
    min_ts: int
    max_ts: int
    count: int


def session_spans(conn: sqlite3.Connection) -> list[SessionSpan]:
    """Time span of every session, ordered by first record."""
    return [
        SessionSpan(sid, min_ts, max_ts, count)
        for sid, min_ts, max_ts, count in conn.execute(
            "SELECT session_id, MIN(ts), MAX(ts), COUNT(*) FROM records"
            f" WHERE {DRIVING_SQL} GROUP BY session_id ORDER BY 2, 1"
        )
    ]


def group_spans(spans: list[SessionSpan]) -> list[list[SessionSpan]]:
    """Chain sessions whose gap to the group so far is within TRIP_GAP_MS (overlaps included)."""
    groups: list[list[SessionSpan]] = []
    group_max = 0
    for span in sorted(spans, key=lambda s: s.min_ts):
        if groups and span.min_ts - group_max <= TRIP_GAP_MS:
            groups[-1].append(span)
            group_max = max(group_max, span.max_ts)
        else:
            groups.append([span])
            group_max = span.max_ts
    return groups


def range_trips(conn: sqlite3.Connection, min_ts: int, max_ts: int) -> list[Trip]:
    """Trips of all records with ts in [min_ts, max_ts], regardless of session, oldest first."""
    segments: list[list[tuple[int, str, dict]]] = []
    for ts, t, d in conn.execute(
        f"SELECT ts, type, data FROM records WHERE ts BETWEEN ? AND ? AND {DRIVING_SQL}"
        " ORDER BY ts, seq",
        (min_ts, max_ts),
    ):
        row = (ts, t, json.loads(d))
        if segments and ts - segments[-1][-1][0] <= TRIP_GAP_MS:
            segments[-1].append(row)
        else:
            segments.append([row])
    trips = (_build(conn, seg) for seg in segments)
    return [t for t in trips if t is not None]


def trips_overlapping(conn: sqlite3.Connection, lo: int, hi: int) -> list[Trip]:
    """Whole trips of every session group intersecting [lo, hi] (late records included)."""
    for group in group_spans(session_spans(conn)):
        g_lo, g_hi = min(s.min_ts for s in group), max(s.max_ts for s in group)
        if g_lo <= hi and g_hi >= lo:
            lo, hi = min(lo, g_lo), max(hi, g_hi)
    return range_trips(conn, lo, hi)


def parse_trip_ts(trip_id: str) -> int | None:
    """New ids are str(start_ts); legacy ones are '<session>:<ts>'."""
    ts = trip_id.rpartition(":")[2]
    return int(ts) if ts.isascii() and ts.isdigit() and len(ts) <= 18 else None


def list_trips(
    conn: sqlite3.Connection, before_ts: int | None = None, limit: int = PAGE_SIZE
) -> tuple[list[Trip], bool]:
    """Newest trips first with start_ts < before_ts; flag = older trips exist."""
    groups = group_spans(session_spans(conn))
    found: list[Trip] = []
    for group in reversed(groups):
        lo = min(s.min_ts for s in group)
        if before_ts is not None and lo >= before_ts:
            continue
        hi = max(s.max_ts for s in group)
        for trip in reversed(range_trips(conn, lo, hi)):
            if before_ts is None or trip.start_ts < before_ts:
                found.append(trip)
        if len(found) > limit:
            break
    return found[:limit], len(found) > limit


def get_trip(conn: sqlite3.Connection, trip_id: str) -> Trip | None:
    ts = parse_trip_ts(trip_id)
    if ts is None:
        return None
    for group in group_spans(session_spans(conn)):
        lo, hi = min(s.min_ts for s in group), max(s.max_ts for s in group)
        if lo <= ts <= hi:
            return next((t for t in range_trips(conn, lo, hi) if t.start_ts <= ts <= t.end_ts), None)
    return None
