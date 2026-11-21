import json

import pytest

from app import scans
from app.db import connect

NOW = 1763481600000


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "s.db"))


def add_event(conn, event, detail, i=1):
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (f"ev-{i}", "dev", "sess", i, NOW, "event",
         json.dumps({"event": event, "detail": detail}), NOW),
    )


def test_create_scan_returns_uuid_and_is_open(conn):
    sid = scans.create_scan(conn, NOW)
    assert len(sid) == 36
    assert scans.open_scans(conn) == [(sid, NOW, "read_dtc")]


def test_pending_commands_fresh_scan(conn):
    sid = scans.create_scan(conn, NOW)
    assert scans.pending_commands(conn, NOW + 1000) == [{"type": "read_dtc", "id": sid}]


def test_pending_commands_excludes_old_scan(conn):
    scans.create_scan(conn, NOW)
    assert scans.pending_commands(conn, NOW + scans.SCAN_TIMEOUT_MS) == []
    assert scans.pending_commands(conn, NOW + scans.SCAN_TIMEOUT_MS + 1) == []


def test_pending_commands_excludes_closed_scan(conn):
    sid = scans.create_scan(conn, NOW)
    scans.close_scan(conn, sid, "done", NOW + 5)
    assert scans.pending_commands(conn, NOW + 10) == []
    assert scans.open_scans(conn) == []


def test_scan_result_done_and_failed(conn):
    a, b = "aaaa", "bbbb"
    add_event(conn, "dtc_scan", a, 1)
    add_event(conn, "dtc_scan_failed", f"{b} obd_not_connected", 2)
    assert scans.scan_result(conn, a) == ("done", NOW)
    assert scans.scan_result(conn, b) == ("failed", NOW)
    assert scans.scan_result(conn, "cccc") is None


def test_scan_result_ignores_other_events(conn):
    add_event(conn, "obd_error", "aaaa", 1)
    assert scans.scan_result(conn, "aaaa") is None


def test_create_clear_scan_and_pending_both_kinds(conn):
    a = scans.create_scan(conn, NOW)
    b = scans.create_scan(conn, NOW + 1, "clear_dtc")
    assert scans.open_scans(conn) == [(a, NOW, "read_dtc"), (b, NOW + 1, "clear_dtc")]
    assert scans.pending_commands(conn, NOW + 1000) == [
        {"type": "read_dtc", "id": a},
        {"type": "clear_dtc", "id": b},
    ]


def test_scan_result_clear_done_and_failed(conn):
    a = scans.create_scan(conn, NOW, "clear_dtc")
    b = scans.create_scan(conn, NOW, "clear_dtc")
    add_event(conn, "dtc_clear", a, 1)
    add_event(conn, "dtc_clear_failed", f"{b} rejected", 2)
    assert scans.scan_result(conn, a) == ("done", NOW)
    assert scans.scan_result(conn, b) == ("failed", NOW)
    assert scans.failure_reason(conn, b) == "rejected"
    assert scans.failure_reason(conn, a) is None


def test_scan_event_does_not_resolve_clear_request(conn):
    a = scans.create_scan(conn, NOW, "clear_dtc")
    add_event(conn, "dtc_scan", a, 1)
    add_event(conn, "dtc_scan_failed", f"{a} obd_error", 2)
    assert scans.scan_result(conn, a) is None
    assert scans.failure_reason(conn, a) is None


def test_clear_event_does_not_resolve_read_request(conn):
    a = scans.create_scan(conn, NOW)
    add_event(conn, "dtc_clear", a, 1)
    assert scans.scan_result(conn, a) is None


def test_failure_reason_for_read_request(conn):
    a = scans.create_scan(conn, NOW)
    add_event(conn, "dtc_scan_failed", f"{a} obd_not_connected", 1)
    assert scans.failure_reason(conn, a) == "obd_not_connected"
