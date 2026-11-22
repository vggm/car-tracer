import json
import uuid

from app import db
from app.location import GpsPoint
from app.trips import get_trip, group_spans, list_trips, parse_trip_ts, session_spans, valid_points

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


def dtc(conn, ts, active=(), pending=(), session="s1"):
    add(conn, ts, "dtc", {"active": list(active), "pending": list(pending)}, session)


def drive(conn, start_ts, seconds, speed=10.0, session="s1", rpm=1500, north0=0.0):
    """Straight line north, one GPS + one OBD sample every 10 s."""
    for i in range(0, seconds + 1, 10):
        ts = start_ts + i * 1000
        gps(conn, ts, north_m=north0 + i * speed, speed=speed, session=session)
        if rpm is not None:
            obd(conn, ts, session=session, rpm=rpm, speed_kmh=speed * 3.6)


def test_session_split_by_gap(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 300)
    drive(conn, 300_000 + 180_000, 300, north0=5000)
    trips, more = list_trips(conn)
    assert len(trips) == 2 and more is False
    assert trips[0].start_ts > trips[1].start_ts


def test_short_segment_is_not_a_trip(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 20)  # 200 m
    assert list_trips(conn) == ([], False)


def test_parked_with_gps_jitter_is_not_a_trip(tmp_path):
    conn = _conn(tmp_path)
    for i in range(0, 1800, 5):
        sign = 1 if (i // 5) % 2 else -1
        gps(conn, i * 1000, north_m=8.0 * sign, speed=0.0)
        obd(conn, i * 1000, rpm=800, speed_kmh=0)
    assert list_trips(conn) == ([], False)


def test_engine_off_with_movement_is_not_a_trip(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 120, rpm=0)
    assert list_trips(conn) == ([], False)


def test_trip_without_obd(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 100, rpm=None)
    (trip,), _ = list_trips(conn)
    assert trip.has_obd is False
    assert abs(trip.max_kmh - 36.0) < 0.01
    assert trip.rpm_avg is None and trip.coolant_start is None


def test_distance_and_speeds(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 100)
    # a faster OBD sample must win for max_kmh
    obd(conn, 55_000, rpm=2000, speed_kmh=42.0)
    (trip,), _ = list_trips(conn)
    assert abs(trip.distance_m - 1000) <= 5
    assert abs(trip.avg_kmh - 36.0) < 0.5
    assert trip.max_kmh == 42.0
    assert trip.duration_ms == 100_000
    assert trip.has_obd is True


def test_idle_time(tmp_path):
    conn = _conn(tmp_path)
    for i in range(0, 61, 3):  # 60 s at rpm 800, stopped
        obd(conn, i * 1000, rpm=800, speed_kmh=0)
    for i in range(0, 101, 10):  # then moving
        ts = 63_000 + i * 1000
        obd(conn, ts, rpm=1500, speed_kmh=36)
        gps(conn, ts, north_m=i * 10.0, speed=10.0)
    (trip,), _ = list_trips(conn)
    assert abs(trip.idle_ms - 60_000) <= 3_000


def test_idle_hole_is_capped(tmp_path):
    conn = _conn(tmp_path)
    obd(conn, 0, rpm=800, speed_kmh=0)
    obd(conn, 40_000, rpm=800, speed_kmh=0)
    obd(conn, 41_000, rpm=1500, speed_kmh=30)
    # keep the segment contiguous with GPS pings and make it long enough
    for i in range(0, 41, 10):
        gps(conn, i * 1000, north_m=i * 20.0, speed=20.0)
    (trip,), _ = list_trips(conn)
    assert trip.idle_ms == 10_000 + 1_000


def test_engine_stats(tmp_path):
    conn = _conn(tmp_path)
    for k, (c, r) in enumerate([(40, 0), (60, 1000), (87, 2000)]):
        obd(conn, k * 50_000, coolant_c=c, rpm=r, speed_kmh=36)
    for i in range(0, 101, 10):
        gps(conn, i * 1000, north_m=i * 10.0, speed=10.0)
    (trip,), _ = list_trips(conn)
    assert trip.coolant_start == 40 and trip.coolant_max == 87
    assert trip.rpm_avg == 1500 and trip.rpm_max == 2000


def test_new_dtcs(tmp_path):
    conn = _conn(tmp_path)
    dtc(conn, 0, active=["P0401"], session="old")
    drive(conn, 1_000_000, 100)
    dtc(conn, 1_050_000, active=["P0401", "P0420"])
    (trip,), _ = list_trips(conn)
    assert trip.new_dtcs == ["P0420"]


def test_new_dtcs_none_and_empty(tmp_path):
    conn = _conn(tmp_path)
    dtc(conn, 0, active=["P0401"], session="old")
    drive(conn, 1_000_000, 100)
    (trip,), _ = list_trips(conn)
    assert trip.new_dtcs is None
    dtc(conn, 1_060_000, pending=["P0401"])
    (trip,), _ = list_trips(conn)
    assert trip.new_dtcs == []


def test_new_dtcs_none_without_previous_reading(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 1_000_000, 100)
    dtc(conn, 1_050_000, active=["P0401"])
    (trip,), _ = list_trips(conn)
    assert trip.new_dtcs is None


def test_pagination(tmp_path):
    conn = _conn(tmp_path)
    for k in range(7):
        drive(conn, k * 1_000_000, 100, session=f"s{k}")
    page1, more1 = list_trips(conn)
    assert len(page1) == 5 and more1 is True
    page2, more2 = list_trips(conn, before_ts=page1[-1].start_ts)
    assert len(page2) == 2 and more2 is False
    assert [t.start_ts for t in page1 + page2] == sorted(
        (k * 1_000_000 for k in range(7)), reverse=True
    )


def test_get_trip_recomputes_with_late_data(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 100)
    (trip,), _ = list_trips(conn)
    first = get_trip(conn, trip.id)
    assert first is not None and first.end_ts == 100_000
    drive(conn, 110_000, 100, north0=1100)
    again = get_trip(conn, trip.id)
    assert again.id == trip.id
    assert again.end_ts > first.end_ts


def test_get_trip_unknown_and_malformed(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 100)
    assert get_trip(conn, "nope") is None
    assert get_trip(conn, "s1:abc") is None
    assert get_trip(conn, "s1:999999999") is None
    assert get_trip(conn, "999999999") is None


def test_trip_id_fits_callback_data(tmp_path):
    conn = _conn(tmp_path)
    sid = str(uuid.uuid4())
    drive(conn, 1_760_000_000_000, 100, session=sid)
    (trip,), _ = list_trips(conn)
    assert len(("trip:" + trip.id).encode()) <= 64


def P(ts, north_m=0.0, acc=5.0, lat=None, lon=None):
    return GpsPoint(
        ts=ts,
        lat=40.0 + north_m / M_PER_DEG if lat is None else lat,
        lon=-3.0 if lon is None else lon,
        acc_m=acc,
        speed_mps=None,
    )


def test_valid_points_drops_low_accuracy_and_zero_zero():
    pts = [P(0), P(1000, acc=80.0), P(2000, lat=0.0, lon=0.0), P(3000, north_m=10)]
    assert [p.ts for p in valid_points(pts)] == [0, 3000]


def test_valid_points_drops_jump_and_keeps_next_plausible():
    # 5 km in 10 s is a jump; the next point is near the last accepted one
    pts = [P(0), P(10_000, north_m=5000), P(20_000, north_m=100)]
    assert [p.ts for p in valid_points(pts)] == [0, 20_000]


def test_valid_points_same_timestamp():
    pts = [P(0), P(0, north_m=0.5), P(0, north_m=50), P(1000, north_m=10)]
    # same ts: kept only if closer than 1 m to the last accepted point
    assert [(p.ts, round(p.lat, 6)) for p in valid_points(pts)] == [
        (0, round(40.0, 6)),
        (0, round(40.0 + 0.5 / M_PER_DEG, 6)),
        (1000, round(40.0 + 10 / M_PER_DEG, 6)),
    ]
    assert valid_points([]) == []


def test_gap_of_exactly_120s_joins(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 100)
    drive(conn, 220_000, 100, north0=1000)  # last record at 100_000 -> exactly 120 s
    trips, _ = list_trips(conn)
    assert len(trips) == 1 and trips[0].end_ts == 320_000
    drive(conn, 1_000_000, 100, session="s2")
    drive(conn, 1_220_001, 100, session="s2", north0=1000)  # 120_001 ms: splits
    trips, _ = list_trips(conn)
    assert len(trips) == 3


def test_pagination_boundary_inside_session(tmp_path):
    conn = _conn(tmp_path)
    starts = []
    for k in range(3):  # one session with three trips
        s = k * 1_000_000
        drive(conn, s, 100)
        starts.append(s)
    drive(conn, 5_000_000, 100, session="s2")
    drive(conn, 6_000_000, 100, session="s3")
    starts += [5_000_000, 6_000_000]
    page1, more1 = list_trips(conn, limit=2)
    assert [t.start_ts for t in page1] == [6_000_000, 5_000_000] and more1
    page2, more2 = list_trips(conn, before_ts=page1[-1].start_ts, limit=2)
    assert [t.start_ts for t in page2] == [2_000_000, 1_000_000] and more2
    page3, more3 = list_trips(conn, before_ts=page2[-1].start_ts, limit=2)
    assert [t.start_ts for t in page3] == [0] and not more3


def test_relaunch_joins_sessions(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 600, session="a")
    drive(conn, 637_000, 600, session="b", north0=6000)
    trips, _ = list_trips(conn)
    assert len(trips) == 1
    assert trips[0].id == "0"
    assert trips[0].end_ts == 1_237_000
    assert trips[0].distance_m > 11_000


def test_stop_over_gap_keeps_two_trips(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 600, session="a")
    drive(conn, 600_000 + 230_000, 600, session="b", north0=6000)
    trips, _ = list_trips(conn)
    assert len(trips) == 2


def test_overlapping_sessions_one_group(tmp_path):
    conn = _conn(tmp_path)
    for i in range(0, 300, 20):
        gps(conn, i * 1000, north_m=i * 10, speed=10.0, session="a")
        gps(conn, (i + 10) * 1000, north_m=(i + 10) * 10, speed=10.0, session="b")
    groups = group_spans(session_spans(conn))
    assert len(groups) == 1 and len(groups[0]) == 2


def test_get_trip_new_and_legacy_id(tmp_path):
    conn = _conn(tmp_path)
    drive(conn, 0, 600, session="a")
    drive(conn, 637_000, 600, session="b", north0=6000)
    base = get_trip(conn, "0")
    assert base is not None and base.id == "0"
    for tid in ("b:637000", "a:0"):
        t = get_trip(conn, tid)
        assert t is not None and t.id == "0" and t.end_ts == base.end_ts
    assert get_trip(conn, "nope") is None
    assert get_trip(conn, "999999999") is None


def test_parse_trip_ts():
    assert parse_trip_ts("123") == 123
    assert parse_trip_ts("s:123") == 123
    assert parse_trip_ts("v12") is None
    assert parse_trip_ts("") is None
    assert parse_trip_ts("s:") is None
