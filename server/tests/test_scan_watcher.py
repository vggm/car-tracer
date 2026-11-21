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


def add(conn, rid, ts, type_, data, session="s"):
    conn.execute(
        "INSERT INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (rid, "d", session, 1, ts, type_, json.dumps(data), ts),
    )


def add_dtc(conn, rid, ts, active, pending=(), session="s"):
    add(conn, rid, ts, "dtc", {"active": list(active), "pending": list(pending)}, session)


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
    check_scans(conn, c, CHAT, NOW + 119_000, TZ)
    assert c.sent == []
    check_scans(conn, c, CHAT, NOW + 121_000, TZ)
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


def test_first_reading_marks_nothing_new(conn):
    sid = scans.create_scan(conn, NOW)
    add_dtc(conn, "b", NOW + 5_000, ["P0401"])
    add_result(conn, sid, NOW + 5_001)
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 10_000, TZ)
    assert "🆕" not in c.sent[0][1]


def test_failing_scan_is_isolated_and_closed(conn):
    bad = scans.create_scan(conn, NOW)
    add_dtc(conn, "bad", NOW + 1_000, [])
    conn.execute("UPDATE records SET data='not json' WHERE id='bad'")
    add_result(conn, bad, NOW + 1_001)
    good = scans.create_scan(conn, NOW + 10)
    add_result(conn, good, NOW + 2_000, "dtc_scan_failed", " obd_not_connected")
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 5_000, TZ)
    assert c.sent == [(CHAT, "⚠️ La tablet no está conectada al ELM327 ahora mismo.")]
    assert scans.open_scans(conn) == []


def test_send_failure_does_not_stop_pass_or_reopen(conn):
    from app.bot.telegram import TelegramError
    for i, t in enumerate((0, 10)):
        sid = scans.create_scan(conn, NOW + t)
        add_result(conn, sid, NOW + 1_000 + i, "dtc_scan_failed", " x")

    class Flaky(FakeClient):
        def send_message(self, chat_id, text, reply_markup=None):
            if not self.sent and not getattr(self, "tried", False):
                self.tried = True
                raise TelegramError("boom")
            super().send_message(chat_id, text)

    c = Flaky()
    check_scans(conn, c, CHAT, NOW + 5_000, TZ)
    assert len(c.sent) == 1
    assert scans.open_scans(conn) == []


def test_run_watcher_retries_connect(tmp_path, monkeypatch):
    from app.bot import scan_watcher
    attempts = []
    seen = []

    def flaky_connect(path):
        attempts.append(path)
        if len(attempts) == 1:
            raise OSError("db locked")
        return "CONN"

    def fake_check(conn, *a, **k):
        seen.append(conn)
        raise KeyboardInterrupt

    monkeypatch.setattr(scan_watcher, "check_scans", fake_check)
    sleeps = []
    with pytest.raises(KeyboardInterrupt):
        run_watcher("p", FakeClient(), CHAT, TZ, sleep=sleeps.append, connect=flaky_connect)
    assert len(attempts) == 2
    assert seen == ["CONN"]
    assert sleeps == [scan_watcher.SCAN_POLL_S]


# ---- clear_dtc ----

def clear_scan(conn, now=NOW):
    return scans.create_scan(conn, now, kind="clear_dtc")


def test_clear_done_no_reading(conn):
    sid = clear_scan(conn)
    add_dtc(conn, "old", NOW - 40_000, ["P0401"])  # older than the re-read window: ignored
    add_result(conn, sid, NOW + 5_000, "dtc_clear")
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 10_000, TZ)
    assert c.sent == [(CHAT, "✅ Averías borradas.")]
    assert scans.open_scans(conn) == []


def test_clear_done_reading_empty(conn):
    sid = clear_scan(conn)
    add_dtc(conn, "b", NOW + 4_000, [])
    add_result(conn, sid, NOW + 5_000, "dtc_clear")
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 10_000, TZ)
    assert c.sent == [(CHAT, "✅ Averías borradas · ahora la centralita no tiene ninguna")]


def test_clear_done_codes_remain(conn):
    sid = clear_scan(conn)
    add_dtc(conn, "b", NOW + 4_000, ["P0401"], ["P0409"])
    add_result(conn, sid, NOW + 5_000, "dtc_clear")
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 10_000, TZ)
    assert c.sent == [(CHAT, "⚠️ Borradas, pero siguen apareciendo:\n"
        "• P0401 · Flujo insuficiente de recirculación de gases (EGR)\n"
        "• P0409 · Circuito del sensor de la EGR")]


@pytest.mark.parametrize("reason,text", [
    ("engine_running", "🔑 Para borrar, pon el contacto con el motor apagado y vuelve a mandar /borrar_averias."),
    ("obd_not_connected", "⚠️ La tablet no está conectada al ELM327 ahora mismo."),
    ("rejected", "⚠️ La centralita no ha aceptado el borrado. Prueba con el motor apagado."),
    ("obd_error", "⚠️ Se perdió la conexión con el ELM327 durante el borrado. Comprueba con /escanear si se borraron."),
    ("weird", "⚠️ La centralita no ha aceptado el borrado. Prueba con el motor apagado."),
])
def test_clear_failed_reasons(conn, reason, text):
    sid = clear_scan(conn)
    add_result(conn, sid, NOW + 1_000, "dtc_clear_failed", " " + reason)
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 5_000, TZ)
    assert c.sent == [(CHAT, text)]


def test_clear_timeout(conn):
    clear_scan(conn)
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 121_000, TZ)
    assert c.sent == [(CHAT, "⌛ La tablet no ha respondido a tiempo. Prueba otra vez en un rato.")]


def test_read_and_clear_each_get_own_text(conn):
    rid = scans.create_scan(conn, NOW)
    cid = clear_scan(conn)
    add_dtc(conn, "b", NOW + 4_000, [])
    add_result(conn, rid, NOW + 5_000, "dtc_scan")
    add_result(conn, cid, NOW + 5_000, "dtc_clear")
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 10_000, TZ)
    texts = sorted(t for _, t in c.sent)
    assert len(texts) == 2
    assert any(t.startswith("✅ Sin averías · leídas ahora ") for t in texts)
    assert "✅ Averías borradas · ahora la centralita no tiene ninguna" in texts


def test_timeout_waits_for_grace_period(conn):
    sid = clear_scan(conn)
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 100_000, TZ)
    assert c.sent == []
    assert len(scans.open_scans(conn)) == 1
    add_result(conn, sid, NOW + 99_000, "dtc_clear")
    check_scans(conn, c, CHAT, NOW + 100_000, TZ)
    assert c.sent == [(CHAT, "✅ Averías borradas.")]


def test_timeout_after_grace_period(conn):
    clear_scan(conn)
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 121_000, TZ)
    assert c.sent == [(CHAT, "⌛ La tablet no ha respondido a tiempo. Prueba otra vez en un rato.")]


def test_clear_reread_matched_by_session_despite_tablet_clock_behind(conn):
    # tablet clock is 60 s behind the server: the re-read ts < requested_at
    sid = clear_scan(conn)
    add_dtc(conn, "r", NOW - 60_000 + 4_000, ["P0401"])
    add_result(conn, sid, NOW - 60_000 + 5_000, "dtc_clear")
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 10_000, TZ)
    assert c.sent == [(CHAT, "⚠️ Borradas, pero siguen apareciendo:\n"
        "• P0401 · Flujo insuficiente de recirculación de gases (EGR)")]


def test_clear_reread_ignores_other_session_and_stale(conn):
    sid = clear_scan(conn)
    add_dtc(conn, "o", NOW + 4_000, ["P0401"], session="other")
    add_dtc(conn, "st", NOW + 5_000 - 31_000, ["P0409"])
    add_result(conn, sid, NOW + 5_000, "dtc_clear")
    c = FakeClient()
    check_scans(conn, c, CHAT, NOW + 10_000, TZ)
    assert c.sent == [(CHAT, "✅ Averías borradas.")]
