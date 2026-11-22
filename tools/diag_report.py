#!/usr/bin/env python3
"""Diagnostics report for car-trace (stdlib only, read-only DB access).

    ssh lnk-server 'podman exec -i car-trace-api python - --hours 48' < tools/diag_report.py
"""
import argparse
import json
import re
import sqlite3
import sys
import time

HOUR_MS = 3_600_000
HEARTBEAT_GAP_MS = 10 * 60_000  # heartbeat is every 5 min; >10 min counts as a gap

_VAR = re.compile(r"\bvar=(V\d+)\b")
_HEADER = re.compile(r"^(attempt|lost)\b(.*)$")
_KV = re.compile(r"(\w+)=(\S+)")
_LINE = re.compile(
    r"^\+(\d+)\s+>\s+(.*?)\s+\|\s+(.*?)\s+\|\s+(\d+)(?:\s+\|\s+ERR\s+(.*))?$")
_DIAG = re.compile(r"^([A-Za-z_]+)\.([A-Za-z_0-9]+)(?:\s+x(\d+))?(?:\s+(.*))?$", re.S)
_NOTE = re.compile(r"^\+\d+\s+#\s*(.*)$")
_RESET_CMDS = {"ATZ", "ATWS"}


def _norm(row):
    """Accept dicts {ts,type,data} or (ts,type,data) tuples; data may be a JSON string."""
    if isinstance(row, dict):
        ts, typ, data = row.get("ts"), row.get("type"), row.get("data")
        if data is None:
            data = {k: v for k, v in row.items() if k not in ("ts", "type")}
    else:
        try:
            ts, typ, data = row[0], row[1], row[2]
        except Exception:
            return None
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    return {"ts": ts if isinstance(ts, (int, float)) else 0, "type": typ, "data": data}


def _events(rows, *names):
    for row in rows:
        r = _norm(row)
        if r and r["type"] == "event" and r["data"].get("event") in names:
            yield r


def _detail(r):
    d = r["data"].get("detail")
    return d if isinstance(d, str) else ""


def variant_stats(rows):
    """{variant: {"fail": n, "ok": n}} from obd_attempt_failed / obd_connected (var=Vx)."""
    out = {}
    for r in _events(rows, "obd_attempt_failed", "obd_connected"):
        m = _VAR.search(_detail(r))
        var = m.group(1) if m else "?"
        slot = out.setdefault(var, {"fail": 0, "ok": 0})
        slot["ok" if r["data"]["event"] == "obd_connected" else "fail"] += 1
    return out


def diag_summary(rows):
    """{"comp.code": {"events": n, "total": sum of xN, "last_ts": ms, "text": last text}}."""
    out = {}
    for r in _events(rows, "diag"):
        m = _DIAG.match(_detail(r).strip())
        if not m:
            key, n, text = "unparsed", 1, _detail(r)
        else:
            key, n, text = f"{m.group(1)}.{m.group(2)}", int(m.group(3) or 1), m.group(4) or ""
        s = out.setdefault(key, {"events": 0, "total": 0, "last_ts": 0, "text": ""})
        s["events"] += 1
        s["total"] += n
        if r["ts"] >= s["last_ts"]:
            s["last_ts"], s["text"] = r["ts"], text
    return out


def parse_trace(detail):
    """-> {"kind", "attrs", "lines": [(ms, cmd, resp, dur, err)], "unparsed": n} or None."""
    if not isinstance(detail, str) or not detail.strip():
        return None
    parts = detail.splitlines()
    m = _HEADER.match(parts[0].strip())
    if not m:
        return None
    attrs = dict(_KV.findall(m.group(2)))
    lines, notes, unparsed = [], [], 0
    for raw in parts[1:]:
        raw = raw.strip()
        if not raw or raw.startswith("…"):
            continue
        nm = _NOTE.match(raw)
        if nm:
            notes.append(nm.group(1))
            continue
        lm = _LINE.match(raw)
        if not lm:
            unparsed += 1
            continue
        lines.append((int(lm.group(1)), lm.group(2), lm.group(3), int(lm.group(4)), lm.group(5)))
    return {"kind": m.group(1), "attrs": attrs, "lines": lines, "notes": notes, "unparsed": unparsed}


def probe_summary(rows):
    """Cross the pre-ATZ 0100 probe (live session or not) with the attempt result."""
    table = {}  # (probe, result) -> n
    stats = {"traces": 0, "attempts": 0, "lost": 0, "unparsed": 0, "glued": 0}
    for r in _events(rows, "obd_trace"):
        stats["traces"] += 1
        t = parse_trace(_detail(r))
        if t is None:
            stats["unparsed"] += 1
            continue
        stats["unparsed"] += t["unparsed"]
        if t["kind"] == "lost":
            stats["lost"] += 1
            continue
        stats["attempts"] += 1
        if (t["attrs"].get("glued") == "1"
                or any("glued=1" in n for n in t["notes"])):
            stats["glued"] += 1
        probe = "sin 0100 previo"
        for _ms, cmd, resp, _dur, _err in t["lines"]:
            c = cmd.strip().upper()
            if c in _RESET_CMDS:
                break
            if c == "0100":
                probe = ("sesión viva (41 00)"
                         if "4100" in re.sub(r"[\s⏎↵>]", "", resp) else "0100 sin datos")
        res = t["attrs"].get("result", "?")
        table[(probe, res)] = table.get((probe, res), 0) + 1
    return table, stats


def health_summary(rows):
    recs = sorted((r for r in map(_norm, rows) if r and r["type"] == "health"),
                  key=lambda r: r["ts"])
    if not recs:
        return None
    last = {}
    maxes = {}
    for r in recs:
        vals = r["data"].get("values")
        if not isinstance(vals, dict):
            continue
        last = vals
        for k in ("queue_pending", "queue_dropped_total"):
            v = vals.get(k)
            if isinstance(v, (int, float)):
                maxes[k] = max(maxes.get(k, v), v)
    gaps = [(a["ts"], b["ts"]) for a, b in zip(recs, recs[1:])
            if b["ts"] - a["ts"] > HEARTBEAT_GAP_MS]
    return {"count": len(recs), "last": last, "max": maxes, "gaps": gaps,
            "first_ts": recs[0]["ts"], "last_ts": recs[-1]["ts"]}


def _t(ms):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ms / 1000)) + "Z"


def render(rows, traces_n, out):
    def p(s=""):
        print(s, file=out)

    p("== Variantes ==")
    vs = variant_stats(rows)
    if not vs:
        p("(sin intentos OBD)")
    for var in sorted(vs):
        ok, fail = vs[var]["ok"], vs[var]["fail"]
        p(f"{var}: ok={ok} fail={fail} tasa={100 * ok / (ok + fail):.0f}%")
    p()
    p("== Sonda ==")
    table, st = probe_summary(rows)
    if not table:
        p("(sin trazas de intento)")
    for (probe, res), n in sorted(table.items()):
        p(f"{probe} -> {res}: {n}")
    p(f"trazas={st['traces']} intentos={st['attempts']} lost={st['lost']} "
      f"glued={st['glued']} sin_parsear={st['unparsed']}")
    p()
    p(f"== Trazas (últimas {traces_n}) ==")
    traces = (sorted(_events(rows, "obd_trace"), key=lambda r: r["ts"])[-traces_n:]
              if traces_n > 0 else [])
    if not traces:
        p("(ninguna)")
    for r in traces:
        p(f"--- {_t(r['ts'])}")
        p(_detail(r))
    p()
    p("== Diagnósticos ==")
    ds = diag_summary(rows)
    if not ds:
        p("(ninguno)")
    for key in sorted(ds, key=lambda k: -ds[k]["total"]):
        s = ds[key]
        p(f"{key}: total={s['total']} eventos={s['events']} último={_t(s['last_ts'])} "
          f"{s['text']}".rstrip())
    p()
    p("== Salud ==")
    h = health_summary(rows)
    if not h:
        p("(sin latidos)")
    else:
        p(f"latidos={h['count']} primero={_t(h['first_ts'])} último={_t(h['last_ts'])}")
        p("últimos valores: " + ", ".join(f"{k}={v}" for k, v in sorted(h["last"].items())))
        for k, v in sorted(h["max"].items()):
            p(f"max {k}={v}")
        p(f"huecos sin latido (>10 min): {len(h['gaps'])}")
        for a, b in h["gaps"][:20]:
            p(f"  {_t(a)} -> {_t(b)} ({(b - a) // 60000} min)")


def load_rows(db, hours, now_ms=None):
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    since = now_ms - int(hours * HOUR_MS)
    uri = "file:" + db.replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        cur = conn.execute(
            "SELECT ts, type, data FROM records WHERE ts >= ? AND type IN "
            "('event','health') ORDER BY ts", (since,))
        return [{"ts": ts, "type": typ, "data": data} for ts, typ, data in cur]
    finally:
        conn.close()


def main(argv=None, out=None):
    ap = argparse.ArgumentParser(description="car-trace diagnostics report")
    ap.add_argument("--db", default="/data/car-trace.db")
    ap.add_argument("--hours", type=float, default=48)
    ap.add_argument("--traces", type=int, default=5)
    args = ap.parse_args(argv)
    render(load_rows(args.db, args.hours), args.traces, out or sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
