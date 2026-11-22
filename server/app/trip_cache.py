"""In-memory cache of computed trips, recomputed from the records on every snapshot.

Cached trips carry no GPS points (memory); use trips.get_trip for the full trip."""
import dataclasses
import sqlite3
import threading

from app.trips import Trip, group_spans, range_trips, session_spans


class TripCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: tuple[list[Trip], tuple] | None = None

    def all_trips(self, conn: sqlite3.Connection) -> list[Trip]:
        """Every trip, newest first by start_ts. Only changed sessions are recomputed."""
        return self.snapshot(conn)[0]

    def snapshot(self, conn: sqlite3.Connection) -> tuple[list[Trip], tuple]:
        """Like all_trips, plus a fingerprint that changes whenever any session changes."""
        spans = session_spans(conn)
        trips = [
            dataclasses.replace(t, points=[])
            for group in group_spans(spans)
            for t in range_trips(conn, min(s.min_ts for s in group), max(s.max_ts for s in group))
        ]
        trips.sort(key=lambda t: t.start_ts, reverse=True)
        result = (trips, tuple(sorted((s.session_id, (s.count, s.max_ts)) for s in spans)))
        with self._lock:
            self._last = result
        return result

    def get(self, conn: sqlite3.Connection, trip_id: str) -> Trip | None:
        for trip in self.all_trips(conn):
            if trip.id == trip_id:
                return trip
        return None
