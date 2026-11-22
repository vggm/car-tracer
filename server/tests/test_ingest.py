import json
from pathlib import Path

import pytest

EX = Path(__file__).resolve().parents[2] / "docs" / "contract" / "examples"
JSONS = sorted(EX.glob("*.json"))
HDR = {"Authorization": "Bearer test-token"}
LIMIT = 262144


def load(name):
    return json.loads((EX / f"{name}.json").read_text())


def count(client):
    return client.app.state.db.execute("SELECT count(*) FROM records").fetchone()[0]


@pytest.mark.parametrize("path", JSONS, ids=lambda p: p.stem)
def test_contract_examples(client, path):
    case = json.loads(path.read_text())
    r = client.post("/api/v1/ingest", json=case["request"], headers=HDR)
    assert r.status_code == case["expected_status"]
    if case["expected_status"] == 200:
        exp = case["expected"]
        body = r.json()
        assert body["accepted"] == exp["accepted"]
        assert body["duplicates"] == exp["duplicates"]
        assert [x["index"] for x in body["rejected"]] == exp["rejected_indexes"]


def test_not_json_body_is_400(client):
    data = (EX / "batch-not-json.txt").read_bytes()
    r = client.post("/api/v1/ingest", content=data, headers=HDR)
    assert r.status_code == 400


def test_json_not_object_is_400(client):
    assert client.post("/api/v1/ingest", content=b"[1]", headers=HDR).status_code == 400


def test_too_many_records_is_400(client):
    req = load("valid-mixed")["request"]
    req = {**req, "records": req["records"] * 84}  # 504
    assert client.post("/api/v1/ingest", json=req, headers=HDR).status_code == 400


def test_resend_counts_as_duplicates(client):
    req = load("valid-mixed")["request"]
    client.post("/api/v1/ingest", json=req, headers=HDR)
    r = client.post("/api/v1/ingest", json=req, headers=HDR)
    assert r.status_code == 200
    assert r.json()["accepted"] == 0 and r.json()["duplicates"] == 6
    assert count(client) == 6


def test_duplicate_ids_within_batch(client):
    req = load("valid-mixed")["request"]
    req = {**req, "records": [req["records"][0], req["records"][0]]}
    r = client.post("/api/v1/ingest", json=req, headers=HDR)
    assert r.json() == {"accepted": 1, "duplicates": 1, "rejected": [], "commands": []}
    assert count(client) == 1


def test_stored_row(client):
    req = load("valid-mixed")["request"]
    client.post("/api/v1/ingest", json=req, headers=HDR)
    row = client.app.state.db.execute(
        "SELECT id, device_id, session_id, seq, ts, type, data, received_at "
        "FROM records WHERE type='event'"
    ).fetchone()
    assert row == (
        "4347dc96-113b-4b4e-aba8-bdcff7f6eda2",
        "junsun-307",
        "5d3eb6a5-e4ec-4dad-85a8-7fb5ebfc5375",
        0,
        1763481001000,
        "event",
        json.dumps({"event": "session_start", "detail": None}),
        1763481600000,
    )


def test_obd_attempt_failed_event_is_stored(client):
    req = load("valid-mixed")["request"]
    detail = "n=2 t=54s v=12.4V | 5: BUS INIT ERROR | 0: UNABLE TO CONNECT"
    rec = dict(req["records"][0])
    rec.update(id="aaaaaaaa-113b-4b4e-aba8-bdcff7f6eda2", seq=999,
               event="obd_attempt_failed", detail=detail)
    assert rec["type"] == "event"
    r = client.post("/api/v1/ingest", json={**req, "records": [rec]}, headers=HDR)
    assert r.status_code == 200
    assert r.json()["accepted"] == 1
    row = client.app.state.db.execute(
        "SELECT data FROM records WHERE id=?", (rec["id"],)
    ).fetchone()
    assert json.loads(row[0]) == {"event": "obd_attempt_failed", "detail": detail}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer x"}, {"Authorization": "Basic test-token"},
     {"Authorization": "bearer test-token"}, {"Authorization": "Bearer  test-token"}],
)
def test_missing_or_wrong_token_is_401(client, headers):
    req = load("valid-mixed")["request"]
    r = client.post("/api/v1/ingest", json=req, headers=headers)
    assert r.status_code == 401
    assert count(client) == 0


def test_401_before_reading_body(client):
    r = client.post("/api/v1/ingest", content=b"x" * (LIMIT + 1))
    assert r.status_code == 401


def test_content_length_over_limit_is_413(client):
    r = client.post("/api/v1/ingest", content=b"x" * (LIMIT + 1), headers=HDR)
    assert r.status_code == 413


def test_chunked_body_over_limit_is_413(client):
    def gen():
        for _ in range(100):
            yield b"x" * 4096

    r = client.post("/api/v1/ingest", content=gen(), headers=HDR)
    assert r.status_code == 413


def test_rejected_entries_carry_index_id_and_error(client):
    case = load("partial-reject")
    r = client.post("/api/v1/ingest", json=case["request"], headers=HDR)
    for entry in r.json()["rejected"]:
        i = entry["index"]
        assert set(entry) == {"index", "id", "error"}
        assert entry["id"] == case["request"]["records"][i].get("id")
        assert isinstance(entry["error"], str) and entry["error"]


def test_huge_seq_rejects_only_that_record(client):
    req = load("valid-mixed")["request"]
    bad = {**req["records"][0], "seq": 2**63}
    req = {**req, "records": [bad] + req["records"][1:]}
    r = client.post("/api/v1/ingest", json=req, headers=HDR)
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 5 and [x["index"] for x in body["rejected"]] == [0]
    assert count(client) == 5


def test_non_object_records_rejected_individually(client):
    req = load("valid-mixed")["request"]
    recs = req["records"]
    req = {**req, "records": [recs[0], 5, recs[1], None, "x", [1]]}
    r = client.post("/api/v1/ingest", json=req, headers=HDR)
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 2 and body["duplicates"] == 0
    assert [(x["index"], x["id"]) for x in body["rejected"]] == [
        (1, None), (3, None), (4, None), (5, None)
    ]
    assert all(x["error"] for x in body["rejected"])


def test_deeply_nested_json_is_400(client):
    body = b"[" * 100000 + b"]" * 100000
    assert len(body) <= LIMIT
    assert client.post("/api/v1/ingest", content=body, headers=HDR).status_code == 400


def _scan_req():
    req = load("valid-mixed")["request"]
    return {**req, "records": []}


def test_ingest_commands_empty_by_default(client):
    r = client.post("/api/v1/ingest", json=_scan_req(), headers=HDR)
    assert r.json()["commands"] == []


def test_ingest_returns_fresh_scan_command(client):
    from app import scans
    from conftest import FIXED_NOW
    sid = scans.create_scan(client.app.state.db, FIXED_NOW - 1000)
    r = client.post("/api/v1/ingest", json=_scan_req(), headers=HDR)
    assert r.json()["commands"] == [{"type": "read_dtc", "id": sid}]


def test_ingest_returns_clear_command(client):
    from app import scans
    from conftest import FIXED_NOW
    sid = scans.create_scan(client.app.state.db, FIXED_NOW - 1000, "clear_dtc")
    r = client.post("/api/v1/ingest", json=_scan_req(), headers=HDR)
    assert r.json()["commands"] == [{"type": "clear_dtc", "id": sid}]


def test_ingest_omits_stale_and_closed_scans(client):
    from app import scans
    from conftest import FIXED_NOW
    db = client.app.state.db
    scans.create_scan(db, FIXED_NOW - scans.SCAN_TIMEOUT_MS - 1)
    closed = scans.create_scan(db, FIXED_NOW - 1000)
    scans.close_scan(db, closed, "done", FIXED_NOW)
    r = client.post("/api/v1/ingest", json=_scan_req(), headers=HDR)
    assert r.json()["commands"] == []


def test_ingest_accepts_mixed_new_records(client):
    req = load("valid-mixed")["request"]
    tmpl = req["records"][0]
    health = {k: v for k, v in tmpl.items() if k not in ("event", "detail")}
    recs = [
        {**tmpl, "id": "aaaaaaa1-113b-4b4e-aba8-bdcff7f6eda2", "seq": 901,
         "event": "obd_trace", "detail": "x" * 4000},
        {**tmpl, "id": "aaaaaaa2-113b-4b4e-aba8-bdcff7f6eda2", "seq": 902,
         "event": "diag", "detail": "gps.no_fix x2 sin fix"},
        {**health, "id": "aaaaaaa3-113b-4b4e-aba8-bdcff7f6eda2", "seq": 903,
         "type": "health", "values": {"battery_pct": 80}},
    ]
    r = client.post("/api/v1/ingest", json={**req, "records": recs}, headers=HDR)
    assert r.status_code == 200
    assert r.json()["accepted"] == 3 and r.json()["rejected"] == []
    stored = client.app.state.db.execute(
        "SELECT type, data FROM records WHERE id='aaaaaaa3-113b-4b4e-aba8-bdcff7f6eda2'"
    ).fetchone()
    assert stored[0] == "health" and json.loads(stored[1]) == {"values": {"battery_pct": 80}}


def _noise(conn, kind, ts, session="s1"):
    from tests.test_trip_cache import add
    if kind == "health":
        add(conn, ts, "health", {"values": {"battery_pct": 50}}, session=session)
    else:
        add(conn, ts, "event", {"event": kind, "detail": "x"}, session=session)


@pytest.mark.parametrize("kind", ["health", "obd_trace", "diag"])
def test_health_does_not_affect_trips_alerts_panel(client, kind):
    from app.alerts import compute_alerts
    from app.trips import list_trips
    from conftest import FIXED_NOW
    from tests.test_panel_api import T1, T2
    from tests.test_trip_cache import drive

    conn = client.app.state.db
    # s1: two drives with a 200 s gap (> 120 s trip gap, so two trips); s2: one drive
    drive(conn, T1 + 100_000, 300, session="s1")
    drive(conn, T1 + 300_000 + 100_000 + 200_000, 300, session="s1")
    drive(conn, T2, 600, session="s2")

    def snapshot():
        trips, more = list_trips(conn)
        # "stale" intentionally counts heartbeats (the app is alive), so skip it here
        alerts = [a for a in compute_alerts(conn, trips, FIXED_NOW, "Europe/Madrid")
                  if a.kind != "stale"]
        panel = client.get("/api/panel/overview").json()
        trips_json = client.get("/api/panel/trips").json()
        return (
            [(t.id, t.start_ts, t.end_ts) for t in trips], more,
            repr(alerts), panel, trips_json,
        )

    before = snapshot()
    assert len(before[0]) == 3
    _noise(conn, kind, T1 + 40_000)                 # 60 s before the first GPS point
    _noise(conn, kind, T1 + 100_000 + 300_000 + 100_000)  # 100 s after the first drive
    _noise(conn, kind, T1 + 100_000 + 300_000 + 200_000)  # inside the gap between drives
    _noise(conn, kind, T2 + 600_000 + 100_000, session="s2")  # 100 s after the last point
    _noise(conn, kind, T1 + 5_000_000, session="s-only")      # noise-only session
    assert snapshot() == before
