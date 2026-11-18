#!/usr/bin/env python3
"""Simulate the car tablet: send a fake drive to the ingest endpoint (stdlib only, Python 3.9+)."""
import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
import uuid

START_LAT = 40.4702
START_LON = -3.7722
SPEED_MPS = 13.9
TICK_S = 3


def build_records(minutes, ago_min, now_ms):
    ticks = int(minutes * 60 / TICK_S)
    start_ms = now_ms - int((ago_min + minutes) * 60000)
    session = str(uuid.uuid4())
    records = []

    def add(offset_ms, rtype, **fields):
        rec = {"id": str(uuid.uuid4()), "session_id": session, "seq": len(records),
               "ts": start_ms + offset_ms, "type": rtype}
        rec.update(fields)
        records.append(rec)

    add(0, "event", event="session_start")
    add(0, "dtc", active=[], pending=[])
    m_per_deg_lon = 111320.0 * math.cos(math.radians(START_LAT))
    for i in range(ticks):
        off = i * TICK_S * 1000
        lon = START_LON + (SPEED_MPS * i * TICK_S) / m_per_deg_lon
        add(off, "gps", lat=START_LAT, lon=round(lon, 6), acc_m=5.0,
            speed_mps=SPEED_MPS, bearing=90.0, alt_m=410.0)
        add(off, "obd", values={
            "rpm": 1800 + (i * 37) % 400,
            "speed_kmh": 50,
            "coolant_c": min(90, 70 + i),
            "intake_kpa": 100 + (i * 7) % 40,
            "load_pct": 35 + (i * 3) % 15,
        })
    return records


def post(url, token, records):
    body = json.dumps({"device_id": "simulator", "app_version": "0.1.0",
                       "records": records}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--minutes", type=float, default=10)
    p.add_argument("--batch", type=int, default=100)
    p.add_argument("--ago-min", type=float, default=0)
    p.add_argument("--repeat", action="store_true",
                   help="re-send the last batch at the end (expects all duplicates)")
    a = p.parse_args(argv)
    if a.batch < 1:
        p.error("--batch must be >= 1")

    records = build_records(a.minutes, a.ago_min, int(time.time() * 1000))
    batches = [records[i:i + a.batch] for i in range(0, len(records), a.batch)]
    if a.repeat:
        batches.append(batches[-1])

    ok = True
    for batch in batches:
        status, text = post(a.url, a.token, batch)
        if status != 200:
            print("HTTP %d: %s" % (status, text))
            ok = False
            break
        print(json.dumps(json.loads(text)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
