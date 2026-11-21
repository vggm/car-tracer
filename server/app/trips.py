"""Pure logic behind the trip commands: segment records into trips and compute stats."""
import json
import sqlite3
from dataclasses import dataclass

from app.location import (
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
    session_id: str
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

    @property
    def duration_ms(self) -> int:
        return self.end_ts - self.start_ts

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


def _build(conn: sqlite3.Connection, session_id: str, rows: list[tuple[int, str, dict]]) -> Trip | None:
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
        id=f"{session_id}:{start_ts}",
        session_id=session_id,
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
    )


def _session_segments(
    conn: sqlite3.Connection, session_id: str
) -> list[list[tuple[int, str, dict]]]:
    """Records of a session split at gaps, oldest first."""
    rows = [
        (ts, t, json.loads(d))
        for ts, t, d in conn.execute(
            "SELECT ts, type, data FROM records WHERE session_id=? ORDER BY ts, seq",
            (session_id,),
        )
    ]
    segments: list[list[tuple[int, str, dict]]] = []
    for row in rows:
        if segments and row[0] - segments[-1][-1][0] <= TRIP_GAP_MS:
            segments[-1].append(row)
        else:
            segments.append([row])
    return segments


def session_trips(conn: sqlite3.Connection, session_id: str) -> list[Trip]:
    """All trips of a session, oldest first."""
    trips = (_build(conn, session_id, seg) for seg in _session_segments(conn, session_id))
    return [t for t in trips if t is not None]


def list_trips(
    conn: sqlite3.Connection, before_ts: int | None = None, limit: int = PAGE_SIZE
) -> tuple[list[Trip], bool]:
    """Newest trips first with start_ts < before_ts; flag = older trips exist."""
    having, params = ("HAVING MIN(ts) < ?", (before_ts,)) if before_ts is not None else ("", ())
    sessions = conn.execute(
        f"SELECT session_id, MIN(ts) FROM records GROUP BY session_id {having} ORDER BY 2 DESC",
        params,
    ).fetchall()
    found: list[Trip] = []
    for session_id, _ in sessions:
        for trip in reversed(session_trips(conn, session_id)):
            if before_ts is None or trip.start_ts < before_ts:
                found.append(trip)
        if len(found) > limit:
            break
    return found[:limit], len(found) > limit


def get_trip(conn: sqlite3.Connection, trip_id: str) -> Trip | None:
    session_id, sep, start = trip_id.rpartition(":")
    if not sep or not start.isdigit():
        return None
    for seg in _session_segments(conn, session_id):
        if seg[0][0] == int(start):
            return _build(conn, session_id, seg)
    return None
