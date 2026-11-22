import json

from app import db, trip_cache
from app.trip_cache import TripCache
from app.trips import list_trips

M_PER_DEG = 111_195.0  # metres per degree of latitude
_n = [0]


def _conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))


def add(conn, ts, type_, data, session="s1"):
    _n[0] += 1
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (f"id{_n[0]}", "d", session, _n[0], ts, type_, json.dumps(data), ts),
    )


def gps(conn, ts, north_m=0.0, east_m=0.0, speed=None, acc=5.0, session="s1"):
    add(conn, ts, "gps", {
        "lat": 40.0 + north_m / M_PER_DEG,
        "lon": -3.0 + east_m / M_PER_DEG,
        "acc_m": acc, "speed_mps": speed,
    }, session)


def obd(conn, ts, session="s1", **values):
    add(conn, ts, "obd", {"values": values}, session)


def drive(conn, start_ts, seconds, speed=10.0, session="s1", rpm=1500, north0=0.0):
    """Straight line north, one GPS + one OBD sample every 10 s."""
    for i in range(0, seconds + 1, 10):
        ts = start_ts + i * 1000
        gps(conn, ts, north_m=north0 + i * speed, speed=speed, session=session)
        if rpm is not None:
            obd(conn, ts, session=session, rpm=rpm, speed_kmh=speed * 3.6)


def test_all_trips_matches_list_trips(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 300)
    drive(conn, 300_000 + 180_000, 300, north0=5000)
    drive(conn, 2_000_000, 300, session="s2")
    got = [t.id for t in TripCache().all_trips(conn)]
    assert len(got) == 3
    assert got == [t.id for t in list_trips(conn, limit=100)[0]]


def test_cache_picks_up_new_records_in_open_session(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 300)
    drive(conn, 2_000_000, 300, session="s2")
    cache = TripCache()
    cache.all_trips(conn)
    drive(conn, 310_000, 300, north0=3000)
    trips = [t for t in cache.all_trips(conn) if t.start_ts == 0]
    assert len(trips) == 1 and trips[0].end_ts == 610_000


def test_get_returns_trip_and_none_for_unknown(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 300)
    cache = TripCache()
    trip = cache.all_trips(conn)[0]
    assert cache.get(conn, trip.id) == trip
    assert cache.get(conn, "nope") is None
    assert cache.get(conn, "s1:999") is None
    assert cache.get(conn, "999") is None


def test_cached_trips_do_not_hold_points(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 300)
    trips = TripCache().all_trips(conn)
    assert trips and all(t.points == [] for t in trips)


def test_cache_joins_sessions(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 600, session="a")
    drive(conn, 637_000, 600, session="b", north0=6000)
    assert len(TripCache().all_trips(conn)) == 1


def test_cache_recomputes_only_changed_group(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    drive(conn, 0, 300, session="a")
    drive(conn, 86_400_000, 300, session="b")
    calls = [0]
    real = trip_cache.range_trips

    def spy(*args, **kwargs):
        calls[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(trip_cache, "range_trips", spy)
    cache = TripCache()
    assert len(cache.all_trips(conn)) == 2 and calls[0] == 2
    calls[0] = 0
    cache.all_trips(conn)
    assert calls[0] == 0
    gps(conn, 86_400_000 + 305_000, north_m=3100, speed=10.0, session="b")
    cache.all_trips(conn)
    assert calls[0] == 1


def test_cache_regroups_when_new_session_bridges(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 300, session="a")
    drive(conn, 500_000, 300, session="c", north0=4000)
    cache = TripCache()
    assert len(cache.all_trips(conn)) == 2
    drive(conn, 390_000, 110, session="b", north0=3000)
    assert len(cache.all_trips(conn)) == 1
