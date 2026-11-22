"""In-memory cache of computed trips, kept per session group.

A group is a chain of sessions whose gaps are within the trip gap. On every snapshot
only the groups whose key changed (new records, or a new session bridging two groups)
are recomputed; keys that no longer exist are dropped.
Cached trips carry no GPS points (memory); use trips.get_trip for the full trip."""
import dataclasses
import sqlite3
import threading

from app.trips import Trip, group_spans, range_trips, session_spans

GroupKey = tuple[tuple[str, int, int], ...]


class TripCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._compute = threading.Lock()  # one cold recompute at a time; others reuse it
        self._groups: dict[GroupKey, list[Trip]] = {}

    def all_trips(self, conn: sqlite3.Connection) -> list[Trip]:
        """Every trip, newest first by start_ts. Only changed session groups are recomputed."""
        return self.snapshot(conn)[0]

    def snapshot(self, conn: sqlite3.Connection) -> tuple[list[Trip], tuple]:
        """Like all_trips, plus a fingerprint that changes whenever any session group changes."""
        keyed = [
            (tuple(sorted((s.session_id, s.count, s.max_ts) for s in group)), group)
            for group in group_spans(session_spans(conn))
        ]
        with self._lock:
            cached = self._groups
        if all(key in cached for key, _ in keyed):
            fresh = {key: cached[key] for key, _ in keyed}
            if len(fresh) != len(cached):  # drop keys that no longer exist
                with self._lock:
                    self._groups = fresh
        else:
            with self._compute:
                with self._lock:
                    cached = self._groups  # another thread may have filled it meanwhile
                fresh = {}
                for key, group in keyed:
                    if key in cached:
                        fresh[key] = cached[key]
                    else:
                        lo = min(s.min_ts for s in group)
                        hi = max(s.max_ts for s in group)
                        fresh[key] = [dataclasses.replace(t, points=[])
                                      for t in range_trips(conn, lo, hi)]
                with self._lock:
                    self._groups = fresh
        trips = sorted((t for ts in fresh.values() for t in ts), key=lambda t: t.start_ts, reverse=True)
        return trips, tuple(sorted(fresh))

    def get(self, conn: sqlite3.Connection, trip_id: str) -> Trip | None:
        for trip in self.all_trips(conn):
            if trip.id == trip_id:
                return trip
        return None
