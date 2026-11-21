import json

import pytest

from app import scans
from app.bot.scan_watcher import check_scans, run_watcher
from app.db import connect

NOW = 1_700_000_000_000
CHAT = 42
TZ = "Europe/Madrid"


class FakeClient:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text))


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "w.db"))


def add(conn, rid, ts, type_, data):
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (rid, "d", "s", 1, ts, type_, json.dumps(data), ts),
    )


def add_dtc(conn, rid, ts, active, pending=()):
    add(conn, rid, ts, "dtc", {"active": list(active), "pending": list(pending)})


def add_result(conn, scan_id, ts, event="dtc_scan", suffix=""):
    add(conn, "ev" + scan_id, ts, "event", {"event": event, "detail": scan_id + suffix})


def test_done_with_new_code(conn):
    add_dtc(conn, "a", NOW - 100_000, ["P0401"])
    sid = scans.create_scan(conn, NOW)
    add_dtc(conn, "b", NOW + 5_000, ["P0401", "P0409"])
    add_result(conn, sid, NOW + 5_001)
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 10_000, TZ)
    assert len(c.sent) == 1
    chat, text = c.sent[0]
    assert chat == CHAT
    hhmm = text.split("\n")[0].rsplit(" ", 1)[1]
    assert text == (
        f"⚠️ Averías · leídas ahora {hhmm}\n"
        "• P0401 · Flujo insuficiente de recirculación de gases (EGR)\n"
        "• 🆕 P0409 · Circuito del sensor de la EGR"
    )
    check_scans(conn, c, CHAT, NOW + 12_000, TZ)
    assert len(c.sent) == 1


def test_done_empty(conn):
    sid = scans.create_scan(conn, NOW)
    add_dtc(conn, "b", NOW + 5_000, [])
    add_result(conn, sid, NOW + 5_001)
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 10_000, TZ)
    assert c.sent[0][1].startswith("✅ Sin averías · leídas ahora ")
    assert scans.open_scans(conn) == []


def test_failed(conn):
    sid = scans.create_scan(conn, NOW)
    add_result(conn, sid, NOW + 1_000, "dtc_scan_failed", " obd_not_connected")
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 5_000, TZ)
    assert c.sent == [(CHAT, "⚠️ La tablet no está conectada al ELM327 ahora mismo.")]
    check_scans(conn, c, CHAT, NOW + 6_000, TZ)
    assert len(c.sent) == 1


def test_timeout(conn):
    scans.create_scan(conn, NOW)
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 89_000, TZ)
    assert c.sent == []
    check_scans(conn, c, CHAT, NOW + 91_000, TZ)
    assert c.sent == [(CHAT, "⌛ La tablet no ha respondido a tiempo. Prueba otra vez en un rato.")]
    check_scans(conn, c, CHAT, NOW + 95_000, TZ)
    assert len(c.sent) == 1
    assert scans.open_scans(conn) == []


def test_run_watcher_survives_errors(tmp_path, monkeypatch):
    from app.bot import scan_watcher
    calls = []

    def boom(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("x")
        if len(calls) >= 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(scan_watcher, "check_scans", boom)
    sleeps = []
    with pytest.raises(KeyboardInterrupt):
        run_watcher(str(tmp_path / "r.db"), FakeClient(), CHAT, TZ, sleep=sleeps.append)
    assert len(calls) == 3
    assert sleeps == [scan_watcher.SCAN_POLL_S] * 2
