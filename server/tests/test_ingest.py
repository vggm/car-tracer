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
    assert r.json() == {"accepted": 1, "duplicates": 1, "rejected": []}
    assert count(client) == 1


def test_stored_row(client):
    req = load("valid-mixed")["request"]
    client.post("/api/v1/ingest", json=req, headers=HDR)
    row = client.app.state.db.execute(
        "SELECT id, device_id, session_id, seq, ts, type, data, received_at "
        "FROM records WHERE type='event'"
    ).fetchone()
    assert row[0] == req["records"][0]["id"]
    assert row[1] == "junsun-307"
    assert json.loads(row[6]) == {"event": "session_start"} or "event" in json.loads(row[6])
    assert row[7] == 1763481600000


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
