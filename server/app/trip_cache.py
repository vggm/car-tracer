"""In-memory cache of computed trips, one entry per session.

Cached trips carry no GPS points (memory); use trips.get_trip for the full trip."""
import dataclasses
import sqlite3
import threading

from app.trips import Trip, session_trips


class TripCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # session_id -> ((record count, max ts), trips oldest first)
        self._sessions: dict[str, tuple[tuple[int, int], list[Trip]]] = {}

    def all_trips(self, conn: sqlite3.Connection) -> list[Trip]:
        """Every trip, newest first by start_ts. Only changed sessions are recomputed."""
        keys = {
            sid: (count, max_ts)
            for sid, count, max_ts in conn.execute(
                "SELECT session_id, count(*), max(ts) FROM records GROUP BY session_id"
            )
        }
        with self._lock:
            for sid in [s for s in self._sessions if s not in keys]:
                del self._sessions[sid]
            for sid, key in keys.items():
                cached = self._sessions.get(sid)
                if cached is None or cached[0] != key:
                    self._sessions[sid] = (key, [dataclasses.replace(t, points=[]) for t in session_trips(conn, sid)])
            trips = [t for _, ts in self._sessions.values() for t in ts]
        trips.sort(key=lambda t: t.start_ts, reverse=True)
        return trips

    def get(self, conn: sqlite3.Connection, trip_id: str) -> Trip | None:
        for trip in self.all_trips(conn):
            if trip.id == trip_id:
                return trip
        return None
