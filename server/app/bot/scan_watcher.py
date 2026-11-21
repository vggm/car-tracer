"""Watches open dtc scan requests and answers them in Telegram."""
import json
import logging
import time

import httpx

from app import fmt, scans
from app.bot.telegram import TelegramError
from app.db import connect
from app.dtc import format_codes

log = logging.getLogger("car-trace.bot")
SCAN_POLL_S = 2
RESULT_GRACE_MS = 30_000  # a command delivered late in its window still gets answered
REREAD_WINDOW_MS = 30_000

FAILED_TEXT = "⚠️ La tablet no está conectada al ELM327 ahora mismo."
TIMEOUT_TEXT = "⌛ La tablet no ha respondido a tiempo. Prueba otra vez en un rato."
ENGINE_RUNNING_TEXT = (
    "🔑 Para borrar, pon el contacto con el motor apagado y vuelve a mandar /borrar_averias."
)
REJECTED_TEXT = "⚠️ La centralita no ha aceptado el borrado. Prueba con el motor apagado."
LINK_LOST_TEXT = (
    "⚠️ Se perdió la conexión con el ELM327 durante el borrado. "
    "Comprueba con /escanear si se borraron."
)
CLEAR_FAILED_TEXTS = {
    "engine_running": ENGINE_RUNNING_TEXT,
    "obd_not_connected": FAILED_TEXT,
    "rejected": REJECTED_TEXT,
    "obd_error": LINK_LOST_TEXT,
}


def _codes(data: str) -> list[str]:
    d = json.loads(data)
    out: list[str] = []
    for c in list(d.get("active") or []) + list(d.get("pending") or []):
        if c not in out:
            out.append(c)
    return out


def _done_text(conn, event_ts: int, tz: str) -> str:
    rows = conn.execute(
        "SELECT ts, data FROM records WHERE type='dtc' AND ts <= ?"
        " ORDER BY ts DESC LIMIT 2",
        (event_ts,),
    ).fetchall()
    if not rows:
        return "⚠️ La tablet respondió, pero no llegaron las averías. Prueba otra vez."
    ts, data = rows[0]
    codes = _codes(data)
    previous = set(_codes(rows[1][1])) if len(rows) > 1 else set()
    when = fmt.hhmm(ts, tz)
    if not codes:
        return f"✅ Sin averías · leídas ahora {when}"
    # no previous reading: nothing to compare against, so nothing is marked new
    new = frozenset(c for c in codes if c not in previous) if len(rows) > 1 else frozenset()
    return "\n".join([f"⚠️ Averías · leídas ahora {when}", *format_codes(codes, new)])


def _clear_done_text(conn, event_ts: int, session_id: str | None) -> str:
    # the tablet's own re-read: same session, just before the event (tablet clock only)
    row = conn.execute(
        "SELECT data FROM records WHERE type='dtc' AND session_id = ?"
        " AND ts BETWEEN ? AND ? ORDER BY ts DESC LIMIT 1",
        (session_id, event_ts - REREAD_WINDOW_MS, event_ts),
    ).fetchone()
    if row is None:
        return "✅ Averías borradas."
    codes = _codes(row[0])
    if not codes:
        return "✅ Averías borradas · ahora la centralita no tiene ninguna"
    return "\n".join(["⚠️ Borradas, pero siguen apareciendo:", *format_codes(codes)])


def _process(conn, scan_id, requested_at, now_ms, tz, scan_kind="read_dtc"):
    result = scans.scan_result(conn, scan_id)
    if result is not None:
        kind, ts = result
        if scan_kind == "clear_dtc":
            if kind == "done":
                return kind, _clear_done_text(conn, ts, scans.result_session(conn, scan_id))
            reason = scans.failure_reason(conn, scan_id)
            return kind, CLEAR_FAILED_TEXTS.get(reason, REJECTED_TEXT)
        return kind, (_done_text(conn, ts, tz) if kind == "done" else FAILED_TEXT)
    if now_ms - requested_at >= scans.SCAN_TIMEOUT_MS + RESULT_GRACE_MS:
        return "timeout", TIMEOUT_TEXT
    return None


def check_scans(conn, client, chat_id: int, now_ms: int, tz: str) -> None:
    for scan_id, requested_at, scan_kind in scans.open_scans(conn):
        try:
            outcome = _process(conn, scan_id, requested_at, now_ms, tz, scan_kind)
        except Exception as e:
            # type name only; close the scan so it neither repeats nor blocks others
            log.warning("scan %s failed (%s)", scan_id, type(e).__name__)
            scans.close_scan(conn, scan_id, "error", now_ms)
            continue
        if outcome is None:
            continue
        kind, text = outcome
        scans.close_scan(conn, scan_id, kind, now_ms)
        try:
            client.send_message(chat_id, text)
        except (TelegramError, httpx.HTTPError) as e:
            log.warning("scan reply failed (%s)", type(e).__name__)


def run_watcher(db_path, client, chat_id, tz, sleep=time.sleep, connect=connect) -> None:
    conn = None
    while True:
        try:
            if conn is None:
                conn = connect(db_path)
            check_scans(conn, client, chat_id, int(time.time() * 1000), tz)
        except Exception as e:
            # type name only: the bot URL carries its credential
            log.warning("scan watcher failed (%s)", type(e).__name__)
        sleep(SCAN_POLL_S)
