"""Watches open dtc scan requests and answers them in Telegram."""
import json
import logging
import time

from app import fmt, scans
from app.db import connect
from app.dtc import format_codes

log = logging.getLogger("car-trace.bot")
SCAN_POLL_S = 2

FAILED_TEXT = "⚠️ La tablet no está conectada al ELM327 ahora mismo."
TIMEOUT_TEXT = "⌛ La tablet no ha respondido a tiempo. Prueba otra vez en un rato."


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
    new = frozenset(c for c in codes if c not in previous) if len(rows) > 1 else frozenset()
    return "\n".join([f"⚠️ Averías · leídas ahora {when}", *format_codes(codes, new)])


def check_scans(conn, client, chat_id: int, now_ms: int, tz: str) -> None:
    for scan_id, requested_at in scans.open_scans(conn):
        result = scans.scan_result(conn, scan_id)
        if result is not None:
            kind, ts = result
            text = _done_text(conn, ts, tz) if kind == "done" else FAILED_TEXT
        elif now_ms - requested_at >= scans.SCAN_TIMEOUT_MS:
            kind, text = "timeout", TIMEOUT_TEXT
        else:
            continue
        scans.close_scan(conn, scan_id, kind, now_ms)
        client.send_message(chat_id, text)


def run_watcher(db_path, client, chat_id, tz, sleep=time.sleep) -> None:
    conn = connect(db_path)
    while True:
        try:
            check_scans(conn, client, chat_id, int(time.time() * 1000), tz)
        except Exception as e:
            # type name only: the bot URL carries its credential
            log.warning("scan watcher failed (%s)", type(e).__name__)
        sleep(SCAN_POLL_S)
