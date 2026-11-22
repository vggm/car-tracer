"""Journeys ("viajes"): trips joined by hand, stored as a time range so they survive recomputation."""
import sqlite3
from dataclasses import dataclass

from app.trips import Trip


@dataclass(frozen=True)
class Journey:
    id: int
    start_ts: int
    end_ts: int


@dataclass(frozen=True)
class Stop:
    start_ts: int
    end_ts: int

    @property
    def duration_ms(self) -> int:
        return self.end_ts - self.start_ts


def _max(values):
    vals = [v for v in values if v is not None]
    return max(vals) if vals else None


@dataclass(frozen=True)
class JourneyView:
    journey_id: int
    segments: list[Trip]  # oldest first, always 2 or more

    @property
    def id(self) -> str:
        return f"v{self.journey_id}"

    @property
    def start_ts(self) -> int:
        return self.segments[0].start_ts

    @property
    def end_ts(self) -> int:
        return self.segments[-1].end_ts

    @property
    def distance_m(self) -> float:
        return sum(s.distance_m for s in self.segments)

    @property
    def drive_ms(self) -> int:
        return sum(s.drive_ms for s in self.segments)

    @property
    def duration_ms(self) -> int:
        return self.end_ts - self.start_ts

    @property
    def avg_kmh(self) -> float:
        if self.drive_ms <= 0:
            return 0.0
        return self.distance_m / (self.drive_ms / 1000.0) * 3.6

    @property
    def max_kmh(self) -> float | None:
        return _max(s.max_kmh for s in self.segments)

    @property
    def coolant_max(self) -> float | None:
        return _max(s.coolant_max for s in self.segments)

    @property
    def rpm_max(self) -> float | None:
        return _max(s.rpm_max for s in self.segments)

    @property
    def has_obd(self) -> bool:
        return any(s.has_obd for s in self.segments)

    @property
    def idle_ms(self) -> int:
        return sum(s.idle_ms for s in self.segments)

    @property
    def coolant_start(self) -> float | None:
        return next((s.coolant_start for s in self.segments if s.coolant_start is not None), None)

    @property
    def rpm_avg(self) -> float | None:
        n = sum(s.rpm_n for s in self.segments)
        if n == 0:
            return None
        return sum((s.rpm_avg or 0.0) * s.rpm_n for s in self.segments) / n

    @property
    def new_dtcs(self) -> list[str] | None:
        lists = [s.new_dtcs for s in self.segments if s.new_dtcs is not None]
        if not lists:
            return None
        return sorted({c for lst in lists for c in lst})

    @property
    def stops(self) -> list[Stop]:
        return [Stop(a.end_ts, b.start_ts) for a, b in zip(self.segments, self.segments[1:])]


Item = Trip | JourneyView


def parse_journey_id(s: str) -> int | None:
    if len(s) > 1 and s[0] == "v" and s[1:].isascii() and s[1:].isdigit() and len(s) <= 19:
        return int(s[1:])
    return None


def load_journeys(conn: sqlite3.Connection) -> list[Journey]:
    return [Journey(*r) for r in conn.execute("SELECT id, start_ts, end_ts FROM journeys ORDER BY start_ts, id")]


def _overlaps(trip: Trip, j: Journey) -> bool:
    return trip.start_ts <= j.end_ts and trip.end_ts >= j.start_ts


def _views(trips: list[Trip], journeys: list[Journey]) -> tuple[list[JourneyView], set[str]]:
    """Visible journeys (2+ trips) and the ids of the trips they claim."""
    ordered = sorted(trips, key=lambda t: t.start_ts)
    taken: set[str] = set()
    views: list[JourneyView] = []
    for j in sorted(journeys, key=lambda j: (j.start_ts, j.id)):
        segs = [t for t in ordered if t.id not in taken and _overlaps(t, j)]
        if len(segs) >= 2:
            views.append(JourneyView(j.id, segs))
            taken.update(t.id for t in segs)
    return views, taken


def group_items(trips: list[Trip], journeys: list[Journey]) -> list[Item]:
    views, taken = _views(trips, journeys)
    items: list[Item] = [*views, *(t for t in trips if t.id not in taken)]
    return sorted(items, key=lambda i: i.start_ts, reverse=True)


def find_journey(trips: list[Trip], journeys: list[Journey], journey_id: int) -> JourneyView | None:
    views, _ = _views(trips, journeys)
    return next((v for v in views if v.journey_id == journey_id), None)


def journey_of(trip: Trip, journeys: list[Journey], trips: list[Trip]) -> str | None:
    for v in _views(trips, journeys)[0]:
        if any(s.id == trip.id for s in v.segments):
            return v.id
    return None


def join(conn: sqlite3.Connection, trips: list[Trip], id_a: str, id_b: str, now_ms: int) -> int:
    by_id = {t.id: t for t in trips}
    if id_a not in by_id or id_b not in by_id:
        raise ValueError("unknown trip")
    if id_a == id_b:
        raise ValueError("need two different trips")
    a, b = sorted((by_id[id_a], by_id[id_b]), key=lambda t: t.start_ts)
    if any(a.start_ts < t.start_ts < b.start_ts for t in trips):
        raise ValueError("trips are not consecutive")
    lo, hi = min(a.start_ts, b.start_ts), max(a.end_ts, b.end_ts)
    conn.execute("BEGIN IMMEDIATE")
    try:
        overlapped = conn.execute(
            "SELECT id, start_ts, end_ts FROM journeys WHERE start_ts <= ? AND end_ts >= ?", (hi, lo)
        ).fetchall()
        for jid, s, e in overlapped:
            if s <= lo and e >= hi:
                conn.execute("COMMIT")
                return jid
        for _, s, e in overlapped:
            lo, hi = min(lo, s), max(hi, e)
        conn.executemany("DELETE FROM journeys WHERE id = ?", [(r[0],) for r in overlapped])
        rowid = conn.execute(
            "INSERT INTO journeys(start_ts, end_ts, created_at) VALUES (?,?,?)", (lo, hi, now_ms)
        ).lastrowid
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return rowid


def separate(conn: sqlite3.Connection, journey_id: int) -> bool:
    return conn.execute("DELETE FROM journeys WHERE id = ?", (journey_id,)).rowcount > 0
