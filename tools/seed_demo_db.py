#!/usr/bin/env python3
"""Build a deterministic demo SQLite database for the web panel (central Madrid only).

Run from the server dir so the app package resolves:
    cd server && uv run python ../tools/seed_demo_db.py <db_path> [--days 420] [--seed 42]
"""
import argparse
import json
import math
import os
import random
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))

from app.db import connect  # noqa: E402

CENTER_LAT = 40.4168
CENTER_LON = -3.7038
TICK_S = 3
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
DEVICE = "demo"
MAX_RADIUS_M = 6000.0
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(CENTER_LAT))

QUIET_DAYS = 4          # no data in the last N days (stale alert)
OVERHEAT_DAYS = 15      # trip reaching 107 C
PARKED_LOW_DAYS = 5     # engine off, 11.8 V
WEAK_CHARGE_DAYS = 30   # two 12.6 V readings with the engine running
DTC1_DAYS, DTC1_CODE = 60, "P0401"
DTC2_DAYS, DTC2_CODE = 20, "P0409"
CLEAR_DAYS = 10         # dtc_clear event at 06:00 of that day; later readings are empty


class Seeder:
    def __init__(self, seed, now_ms):
        self.rng = random.Random(seed)
        self.now_ms = now_ms
        self.today0 = now_ms - now_ms % DAY_MS
        self.rows = []
        self.sessions = 0

    def uid(self):
        return str(uuid.UUID(int=self.rng.getrandbits(128), version=4))

    def session(self, start_ms):
        self.sessions += 1
        return Session(self, start_ms)

    def dtc_codes(self, ts):
        if ts >= self.today0 - CLEAR_DAYS * DAY_MS + 6 * HOUR_MS:
            return []
        codes = []
        if ts >= self.today0 - DTC1_DAYS * DAY_MS:
            codes.append(DTC1_CODE)
        if ts >= self.today0 - DTC2_DAYS * DAY_MS:
            codes.append(DTC2_CODE)
        return codes


class Session:
    def __init__(self, seeder, start_ms):
        self.s = seeder
        self.id = seeder.uid()
        self.start_ms = start_ms
        self.seq = 0

    def add(self, offset_ms, rtype, data):
        ts = self.start_ms + offset_ms
        self.s.rows.append((self.s.uid(), "demo", self.id, self.seq, ts, rtype,
                            json.dumps(data), ts + 1000))
        self.seq += 1


def drive(sd, sess, minutes, with_obd, overheat=False, weak_charge=False):
    rng = sd.rng
    ticks = int(minutes * 60 / TICK_S)
    sess.add(0, "event", {"event": "session_start", "detail": None})
    if with_obd:
        sess.add(0, "dtc", {"active": sd.dtc_codes(sess.start_ms), "pending": []})
    x = rng.uniform(-1500, 1500)   # metres east of the centre
    y = rng.uniform(-1500, 1500)   # metres north of the centre
    heading = rng.uniform(0, 360)
    speed = 0.0
    stop_left = 0
    volt_n = 0
    for i in range(ticks):
        off = i * TICK_S * 1000
        if stop_left > 0:
            stop_left -= 1
            speed = 0.0
        else:
            if i > 5 and rng.random() < 0.02:
                stop_left = rng.randint(2, 8)
            target = rng.uniform(25, 55)
            speed = min(65.0, max(10.0, speed + (target - speed) * 0.2 + rng.uniform(-3, 3)))
        heading += rng.gauss(0, 6) + (rng.choice([-80, 80]) if rng.random() < 0.01 else 0)
        if math.hypot(x, y) > MAX_RADIUS_M:   # steer back towards the centre
            back = math.degrees(math.atan2(-x, -y))
            diff = (back - heading + 540) % 360 - 180
            heading += max(-25, min(25, diff))
        heading %= 360
        mps = speed / 3.6
        x += mps * TICK_S * math.sin(math.radians(heading))
        y += mps * TICK_S * math.cos(math.radians(heading))
        sess.add(off, "gps", {
            "lat": round(CENTER_LAT + y / M_PER_DEG_LAT, 6),
            "lon": round(CENTER_LON + x / M_PER_DEG_LON, 6),
            "acc_m": 5.0, "speed_mps": round(mps, 2), "bearing": round(heading, 1), "alt_m": 650.0,
        })
        if not with_obd:
            continue
        coolant = min(90.0, 20.0 + 70.0 * (i * TICK_S) / 600.0)
        if overheat and i > ticks * 0.6:
            coolant = min(107.0, 90.0 + (i - ticks * 0.6) * 0.5)
        values = {
            "rpm": int(800 + speed * 28 + rng.uniform(-60, 60)) if speed > 0 else int(rng.uniform(760, 840)),
            "speed_kmh": round(speed),
            "coolant_c": 107.0 if coolant >= 107.0 else round(coolant + rng.uniform(-0.4, 0.4), 1),
        }
        if i > 0 and i % 20 == 0:   # every 60 s
            volt_n += 1
            if not weak_charge:
                values["voltage_v"] = round(14.1 + rng.uniform(-0.15, 0.15), 2)
            elif volt_n <= 2:
                values["voltage_v"] = 12.6
        sess.add(off, "obd", {"values": values})


def parked_low_battery(sess, minutes=6):
    sess.add(0, "event", {"event": "session_start", "detail": None})
    sess.add(0, "dtc", {"active": [], "pending": []})
    for i in range(int(minutes * 60 / TICK_S)):
        values = {"rpm": 0, "speed_kmh": 0, "coolant_c": 20.0}
        if i % 20 == 0:
            values["voltage_v"] = 11.8
        sess.add(i * TICK_S * 1000, "obd", {"values": values})


def build(db_path, days, seed):
    sd = Seeder(seed, int(time.time() * 1000))
    rng = sd.rng
    slots = list(range(7, 22, 2))
    special = {OVERHEAT_DAYS, WEAK_CHARGE_DAYS, CLEAR_DAYS}

    for d in range(days, QUIET_DAYS, -1):
        day0 = sd.today0 - d * DAY_MS
        if d == PARKED_LOW_DAYS:
            # the newest data: one parked session late in the day
            parked_low_battery(sd.session(day0 + 19 * HOUR_MS))
            continue
        if d not in special and rng.random() >= 4 / 7:
            continue
        n = 1 if d in special else rng.choices([1, 2, 3], [60, 30, 10])[0]
        for hour in sorted(rng.sample(slots, n)):
            start = day0 + hour * HOUR_MS + rng.randint(0, 30) * 60_000
            minutes = rng.uniform(8, 70)
            with_obd = rng.random() >= 0.10
            kw = {}
            if d == OVERHEAT_DAYS:
                minutes, with_obd, kw = 45, True, {"overheat": True}
            elif d == WEAK_CHARGE_DAYS:
                minutes, with_obd, kw = 15, True, {"weak_charge": True}
            elif d == CLEAR_DAYS:
                with_obd = True
            drive(sd, sd.session(start), minutes, with_obd, **kw)
        if d == CLEAR_DAYS:
            sd.session(day0 + 6 * HOUR_MS).add(
                0, "event", {"event": "dtc_clear", "detail": "cleared from the panel demo"})

    conn = connect(db_path)
    conn.execute("BEGIN")
    conn.executemany(
        "INSERT OR IGNORE INTO records(id, device_id, session_id, seq, ts, type, data, received_at)"
        " VALUES (?,?,?,?,?,?,?,?)", sd.rows)
    conn.execute("COMMIT")
    conn.close()
    return len(sd.rows), sd.sessions


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("db_path")
    p.add_argument("--days", type=int, default=420)
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args(argv)
    if a.days <= PARKED_LOW_DAYS:
        p.error("--days must be greater than %d" % PARKED_LOW_DAYS)
    if os.path.exists(a.db_path):
        p.error("db_path already exists: refusing to overwrite")
    n, s = build(a.db_path, a.days, a.seed)
    print("seeded %d records, %d sessions" % (n, s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
