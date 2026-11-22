import dataclasses

import pytest

from app import db
from app.journeys import (
    JourneyView, find_journey, group_items, join, journey_of, load_journeys,
    parse_journey_id, separate,
)
from app.trips import range_trips
from tests.test_trips import drive

GAP = 230_000


@pytest.fixture
def setup(tmp_path):
    conn = db.connect(str(tmp_path / "j.db"))
    t0 = 1_000_000
    drive(conn, t0, 300)
    drive(conn, t0 + 300_000 + GAP, 300, north0=5000)
    drive(conn, t0 + 600_000 + 2 * GAP, 300, north0=10000)
    trips = range_trips(conn, 0, 10**12)
    assert len(trips) == 3
    return conn, trips


def _loose(trips):
    return [dataclasses.replace(t, points=[]) for t in trips]


def test_join_two_consecutive(setup):
    conn, (a, b, c) = setup
    jid = join(conn, [a, b, c], a.id, b.id, 1)
    items = group_items([a, b, c], load_journeys(conn))
    assert len(items) == 2 and items[0] == c
    v = items[1]
    assert isinstance(v, JourneyView) and v.segments == [a, b]
    assert v.id == f"v{jid}" == "v1"
    assert v.distance_m == a.distance_m + b.distance_m
    assert v.drive_ms == a.drive_ms + b.drive_ms
    assert v.duration_ms == b.end_ts - a.start_ts
    assert [s.duration_ms for s in v.stops] == [GAP]


def test_join_extends_existing_journey(setup):
    conn, (a, b, c) = setup
    join(conn, [a, b, c], b.id, a.id, 1)
    join(conn, [a, b, c], b.id, c.id, 2)
    assert conn.execute("SELECT count(*) FROM journeys").fetchone()[0] == 1
    items = group_items([c, b, a], load_journeys(conn))
    assert len(items) == 1 and len(items[0].segments) == 3


def test_join_twice_same_id(setup):
    conn, (a, b, c) = setup
    assert join(conn, [a, b, c], a.id, b.id, 1) == join(conn, [a, b, c], a.id, b.id, 2)
    assert conn.execute("SELECT count(*) FROM journeys").fetchone()[0] == 1


def test_join_not_consecutive_raises(setup):
    conn, (a, b, c) = setup
    with pytest.raises(ValueError):
        join(conn, [a, b, c], a.id, c.id, 1)
    with pytest.raises(ValueError):
        join(conn, [a, b, c], a.id, "999", 1)
    assert conn.execute("SELECT count(*) FROM journeys").fetchone()[0] == 0


def test_separate(setup):
    conn, (a, b, c) = setup
    jid = join(conn, [a, b, c], a.id, b.id, 1)
    assert separate(conn, jid) is True
    assert len(group_items([a, b, c], load_journeys(conn))) == 3
    assert separate(conn, 999) is False


def test_journey_with_one_trip_shows_loose(setup):
    conn, (a, b, c) = setup
    conn.execute("INSERT INTO journeys(start_ts, end_ts, created_at) VALUES (?,?,0)", (a.start_ts, a.end_ts))
    js = load_journeys(conn)
    assert group_items([a, b, c], js) == [c, b, a]
    assert journey_of(a, js, [a, b, c]) is None
    assert find_journey([a, b, c], js, js[0].id) is None


def test_journey_of_and_find(setup):
    conn, (a, b, c) = setup
    jid = join(conn, [a, b, c], a.id, b.id, 1)
    js = load_journeys(conn)
    assert journey_of(b, js, [a, b, c]) == f"v{jid}"
    assert journey_of(c, js, [a, b, c]) is None
    assert find_journey([a, b, c], js, jid).segments == [a, b]


def test_late_records_stay_in_journey(setup):
    conn, (a, b, c) = setup
    join(conn, [a, b, c], a.id, b.id, 1)
    drive(conn, b.end_ts + 10_000, 60, north0=5000 + 3000)
    trips = range_trips(conn, 0, 10**12)
    items = group_items(trips, load_journeys(conn))
    assert len(items) == 2
    v = items[1]
    assert isinstance(v, JourneyView) and len(v.segments) == 2
    assert v.segments[1].end_ts > b.end_ts


def test_combined_stats(tmp_path):
    conn = db.connect(str(tmp_path / "s.db"))
    drive(conn, 0, 90, rpm=1000, speed=10.0)        # 10 samples
    drive(conn, 90_000 + GAP, 290, rpm=2000, speed=20.0, north0=5000)  # 30 samples
    a, b = range_trips(conn, 0, 10**12)
    assert (a.rpm_n, b.rpm_n) == (10, 30)
    join(conn, [a, b], a.id, b.id, 1)
    v = group_items([a, b], load_journeys(conn))[0]
    assert v.rpm_avg == 1750
    assert v.new_dtcs is None
    assert v.max_kmh == max(a.max_kmh, b.max_kmh)
    assert v.rpm_max == 2000


def test_join_works_with_cache_style_trips(setup):
    conn, (a, b, c) = setup
    join(conn, _loose([a, b, c]), a.id, b.id, 1)


def test_parse_journey_id():
    assert parse_journey_id("v12") == 12
    for bad in ("12", "v", "vx", "v-1", "v1.5"):
        assert parse_journey_id(bad) is None
