import importlib.util
import io
import json
import sqlite3
import time
from pathlib import Path

from app.db import SCHEMA

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "diag_report.py"
spec = importlib.util.spec_from_file_location("diag_report", SCRIPT)
dr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dr)

NOW = int(time.time() * 1000)


def ev(event, detail, ts=NOW):
    return {"ts": ts, "type": "event", "data": {"event": event, "detail": detail}}


def health(values, ts):
    return {"ts": ts, "type": "health", "data": {"values": values}}


TRACE_OK = (
    "attempt n=1 variant=V3 session_age=12s result=ok\n"
    "+0 > open | OK | 5\n"
    "+12 # glued=1\n"
    "+20 > ATI | ELM327 v1.5⏎⏎> | 30\n"
    "+40 > 0100 | 41 00 BE 3E B8 13⏎⏎> | 80\n"
    "+130 > ATWS | ELM327 v1.5⏎⏎> | 90\n"
    "+230 > 0100 | 41 00 BE 3E B8 13⏎⏎> | 70"
)
TRACE_FAIL = (
    "attempt n=2 variant=V2 session_age=20s result=fail glued=1\n"
    "+0 > ATDPN | A5⏎⏎> | 20\n"
    "+30 > 0100 | ⏎> | 3000 | ERR timeout\n"
    "+3100 > ATZ | ELM327 v1.5⏎⏎> | 900\n"
    "garbage line"
)


def seeded_rows():
    return [
        ev("obd_attempt_failed", "5: UNABLE TO CONNECT var=V2"),
        ev("obd_attempt_failed", "5: no supported PIDs [] var=V2"),
        ev("obd_connected", "proto=5 var=V3"),
        ev("obd_trace", TRACE_OK),
        ev("obd_trace", TRACE_FAIL),
        ev("obd_trace", "something unexpected"),
        ev("diag", "gps.no_fix 130s without fix"),
        ev("diag", "gps.no_fix x3 again"),
        ev("diag", "upload.failing HTTP 500"),
        ev("diag", "???"),
        health({"queue_pending": 4, "battery_pct": 80}, NOW - 3_600_000),
        health({"queue_pending": 9, "battery_pct": 70}, NOW - 3_000_000),
        health({"queue_pending": 2, "battery_pct": 60}, NOW - 100_000),
    ]


def test_variant_stats():
    vs = dr.variant_stats(seeded_rows())
    assert vs == {"V2": {"fail": 2, "ok": 0}, "V3": {"fail": 0, "ok": 1}}


def test_diag_summary_groups_and_sums():
    ds = dr.diag_summary(seeded_rows())
    assert ds["gps.no_fix"]["events"] == 2
    assert ds["gps.no_fix"]["total"] == 4
    assert ds["upload.failing"]["total"] == 1
    assert ds["unparsed"]["total"] == 1


def test_probe_cross():
    table, st = dr.probe_summary(seeded_rows())
    assert dr.parse_trace(TRACE_OK)["unparsed"] == 0
    assert table[("sesión viva (41 00)", "ok")] == 1
    assert table[("0100 timeout", "fail")] == 1
    assert st["glued"] == 2 and st["unparsed"] == 2 and st["attempts"] == 2


def test_report_sections_from_db(tmp_path):
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    for i, r in enumerate(seeded_rows()):
        conn.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
                     (str(i), "d", "s", i, r["ts"], r["type"], json.dumps(r["data"]), NOW))
    conn.execute("INSERT INTO records VALUES ('old','d','s',99,?,'event',?,?)",
                 (NOW - 500 * 3_600_000, json.dumps({"event": "obd_connected",
                                                      "detail": "var=V1"}), NOW))
    conn.commit()
    conn.close()
    buf = io.StringIO()
    assert dr.main(["--db", str(db), "--hours", "48"], buf) == 0
    text = buf.getvalue()
    for sec in ("Variantes", "Sonda", "Trazas", "Diagnósticos", "Salud"):
        assert sec in text
    assert "V1:" not in text  # outside --hours window
    assert "huecos sin latido (>10 min): 1" in text
    assert "max queue_pending=9" in text


def test_probe_separates_timeout_from_no_data():
    table, _ = dr.probe_summary(
        [ev("obd_trace", "attempt n=1 variant=V1 session_age=5s result=fail\n"
                         "+0 > 0100 | ⏎> | 2000 | ERR timeout after 2000ms\n"
                         "+2100 > ATZ | ELM327 v1.5⏎⏎> | 900"),
         ev("obd_trace", "attempt n=2 variant=V2 session_age=9s result=fail\n"
                         "+0 > 0100 | NO DATA⏎⏎> | 300\n"
                         "+400 > ATZ | ELM327 v1.5⏎⏎> | 900")])
    assert table[("0100 timeout", "fail")] == 1
    assert table[("0100 sin datos", "fail")] == 1


def _att(n, var, age, res, volts):
    return ev("obd_trace",
              f"attempt n={n} variant={var} session_age={age} result={res}\n"
              "+0 > open | OK | 5\n"
              f"+10 > ATRV | {volts}⏎⏎> | 40\n"
              "+60 > 0100 | ⏎> | 2000 | ERR timeout\n"
              "+2100 > ATZ | ELM327 v1.5⏎⏎> | 900\n"
              f"+3000 > ATRV | 14.9V⏎⏎> | 40", ts=NOW + n)


def test_sessions_summary_lists_attempts_in_order_with_probe_volts():
    rows = [
        {**_att(2, "V2", "20s", "fail", "12.4V"), "session": "A"},
        {**_att(1, "V1", "5s", "fail", "11.9V"), "session": "A"},
        {**ev("obd_trace", "attempt n=1 variant=V3 session_age=7s result=ok\n+0 > open | OK | 5",
              ts=NOW + 9), "session": "B"},
        {**ev("obd_trace", "lost n=1 variant=V1", ts=NOW + 10), "session": "B"},
    ]
    ss = dr.sessions_summary(rows)
    assert ss["A"] == [
        {"n": "1", "variant": "V1", "result": "fail", "age": "5s", "volts": "11.9"},
        {"n": "2", "variant": "V2", "result": "fail", "age": "20s", "volts": "12.4"},
    ]
    assert ss["B"][0]["volts"] == "?" and len(ss["B"]) == 1
    buf = io.StringIO()
    dr.render(rows, 0, buf)
    text = buf.getvalue()
    assert "== Sesiones ==" in text
    assert "  1 V1 fail 5s v=11.9" in text and "  2 V2 fail 20s v=12.4" in text
