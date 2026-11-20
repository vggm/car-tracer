"""Pure logic behind the /donde command: car state and message texts."""
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

MAX_ACC_M = 50.0
MAX_SPEED_MPS = 70.0
MOVING_WINDOW_MS = 300_000
MOVING_MIN_KMH = 5.0
GPS_GAP_MS = 120_000
OBD_WINDOW_MS = 60_000
VOLTAGE_WINDOW_MS = 180_000
ENGINE_ON_VOLTAGE = 13.2
GPS_CANDIDATES = 50


@dataclass(frozen=True)
class GpsPoint:
    ts: int
    lat: float
    lon: float
    acc_m: float
    speed_mps: float | None


@dataclass(frozen=True)
class CarStatus:
    state: Literal[
        "moving", "idle", "engine_off", "stopped", "no_signal", "parked", "no_data"
    ]
    last_ts: int | None
    point: GpsPoint | None
    speed_kmh: float | None
    engine_on: bool | None = None


def _haversine_m(a: GpsPoint, b: GpsPoint) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp = p2 - p1
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _plausible(newer: GpsPoint, older: GpsPoint) -> bool:
    dist = _haversine_m(newer, older)
    dt = (newer.ts - older.ts) / 1000.0
    if dt <= 0:
        return dist < 1.0
    return dist / dt <= MAX_SPEED_MPS


def last_valid_point(points_newest_first: list[GpsPoint]) -> GpsPoint | None:
    """Return the newest acceptable GPS point.

    Static checks first: acc_m <= 50 and not (0, 0). Among the statically
    valid points (newest to oldest), p_i is accepted when there is no older
    valid point, or when the implied speed between p_i and the next older
    valid point p_{i+1} is <= 70 m/s; otherwise p_i is skipped as a jump.
    """
    valid = [
        p for p in points_newest_first
        if p.acc_m <= MAX_ACC_M and not (abs(p.lat) < 1e-6 and abs(p.lon) < 1e-6)
    ]
    for i, p in enumerate(valid):
        if i + 1 >= len(valid) or _plausible(p, valid[i + 1]):
            return p
    return None


def _speed_kmh(conn: sqlite3.Connection, last_ts: int, point: GpsPoint | None) -> float | None:
    rows = conn.execute(
        "SELECT data FROM records WHERE type='obd' AND ts BETWEEN ? AND ?"
        " ORDER BY ts DESC",
        (last_ts - OBD_WINDOW_MS, last_ts),
    )
    for (data,) in rows:
        v = (json.loads(data).get("values") or {}).get("speed_kmh")
        if v is not None:
            return float(v)
    if point is not None and point.speed_mps is not None:
        return point.speed_mps * 3.6
    return None


def _engine_on(conn: sqlite3.Connection, last_ts: int) -> bool | None:
    """Engine state from OBD: rpm (last 60 s) first, else voltage (last 180 s)."""
    rows = [
        (ts, json.loads(d).get("values") or {})
        for (ts, d) in conn.execute(
            "SELECT ts, data FROM records WHERE type='obd' AND ts BETWEEN ? AND ?"
            " ORDER BY ts DESC",
            (last_ts - VOLTAGE_WINDOW_MS, last_ts),
        )
    ]
    for ts, v in rows:
        if ts >= last_ts - OBD_WINDOW_MS and v.get("rpm") is not None:
            return float(v["rpm"]) > 0
    for _, v in rows:
        if v.get("voltage_v") is not None:
            return float(v["voltage_v"]) >= ENGINE_ON_VOLTAGE
    return None


def car_status(conn: sqlite3.Connection, now_ms: int) -> CarStatus:
    last_ts = conn.execute("SELECT MAX(ts) FROM records").fetchone()[0]
    if last_ts is None:
        return CarStatus("no_data", None, None, None)
    points = []
    for (data, ts) in conn.execute(
        "SELECT data, ts FROM records WHERE type='gps' ORDER BY ts DESC LIMIT ?",
        (GPS_CANDIDATES,),
    ):
        d = json.loads(data)
        if d.get("lat") is None or d.get("lon") is None or d.get("acc_m") is None:
            continue
        points.append(GpsPoint(ts, d["lat"], d["lon"], d["acc_m"], d.get("speed_mps")))
    point = last_valid_point(points)
    speed = _speed_kmh(conn, last_ts, point)
    engine_on = _engine_on(conn, last_ts)
    fast = speed is not None and speed >= MOVING_MIN_KMH
    if now_ms - last_ts >= MOVING_WINDOW_MS:
        state = "no_signal" if fast else "parked"
    elif fast:
        state = "moving"
    elif engine_on is True:
        state = "idle"
    elif engine_on is False:
        state = "engine_off"
    else:
        state = "stopped"
    return CarStatus(state, last_ts, point, speed, engine_on)


def _rel(delta_ms: int) -> str:
    s = max(0, delta_ms) // 1000
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min"
    return f"{s // 3600} h {(s % 3600) // 60} min"


def _hhmm(ts_ms: int, tz: str) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, ZoneInfo(tz)).strftime("%H:%M")


def format_status(status: CarStatus, now_ms: int, tz: str) -> str:
    if status.state == "no_data" or status.last_ts is None:
        return "Todavía no hay datos del coche."
    rel = _rel(now_ms - status.last_ts)
    if status.state == "moving":
        text = f"🚗 En marcha · último dato hace {rel}"
        if status.speed_kmh is not None:
            text += f" · {round(status.speed_kmh)} km/h"
    elif status.state == "idle":
        text = f"⏸️ Parado pero encendido · último dato hace {rel}"
    elif status.state == "engine_off":
        text = f"🔑 Contacto puesto, motor apagado · último dato hace {rel}"
    elif status.state == "stopped":
        text = f"⏸️ Parado · último dato hace {rel}"
    elif status.state == "no_signal":
        text = f"📵 Sin señal desde las {_hhmm(status.last_ts, tz)} · iba en marcha"
    else:
        text = f"🅿️ Aparcado desde las {_hhmm(status.last_ts, tz)} (hace {rel})"
        if status.point is not None and status.last_ts - status.point.ts > GPS_GAP_MS:
            text += f"\nÚltima posición GPS de las {_hhmm(status.point.ts, tz)}"
    if status.point is None:
        text += "\nSin posición GPS todavía."
    return text
