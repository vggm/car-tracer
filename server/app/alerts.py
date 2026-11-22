"""Alerts derived on the fly from stored telemetry (read-only)."""
import json
import sqlite3
from dataclasses import dataclass

from app import fmt
from app.dtc import describe
from app.location import ENGINE_ON_VOLTAGE
from app.trips import Trip

DAY_MS = 86_400_000
WINDOW_MS = 90 * DAY_MS
OVERHEAT_C = 105.0
BATTERY_LOW_V = 12.0
CHARGE_MIN_V = 13.0
CHARGE_MAX_V = 14.8
STALE_MS = 3 * DAY_MS
RECENT_MS = 7 * DAY_MS


@dataclass(frozen=True)
class Alert:
    id: str
    kind: str
    severity: str
    ts: int
    title: str
    detail: str
    trip_id: str | None


def _records(conn: sqlite3.Connection, type_: str, since: int):
    for session_id, ts, data in conn.execute(
        "SELECT session_id, ts, data FROM records WHERE type=? AND ts >= ? ORDER BY ts, seq",
        (type_, since),
    ):
        yield session_id, ts, json.loads(data)


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def _trip_id(trips: list[Trip], ts: int) -> str | None:
    for t in trips:
        if t.start_ts <= ts <= t.end_ts:
            return t.id
    return None


def _codes(data: dict) -> list[str]:
    seen: list[str] = []
    for c in list(data.get("active") or []) + list(data.get("pending") or []):
        if c not in seen:
            seen.append(c)
    return seen


def _new_dtc(conn, trips, since) -> list[Alert]:
    out: list[Alert] = []
    prev = conn.execute(
        "SELECT data FROM records WHERE type='dtc' AND ts < ? ORDER BY ts DESC, seq DESC LIMIT 1",
        (since,),
    ).fetchone()
    previous = _codes(json.loads(prev[0])) if prev else None
    for session_id, ts, data in _records(conn, "dtc", since):
        codes = _codes(data)
        if previous is not None:
            new = [c for c in codes if c not in previous]
            if new:
                title = ("Avería nueva: " if len(new) == 1 else "Averías nuevas: ") + ", ".join(new)
                out.append(Alert(
                    f"new_dtc:{session_id}:{ts}", "new_dtc", "high", ts, title,
                    "; ".join(describe(c) for c in new), _trip_id(trips, ts),
                ))
        previous = codes
    return out


def _overheat(trips, since, tz) -> list[Alert]:
    return [
        Alert(
            f"overheat:{t.id}", "overheat", "high", t.start_ts,
            f"Motor caliente: {fmt.num(t.coolant_max)} °C",
            f"Trayecto del {_lower_first(fmt.full_day(t.start_ts, tz))} a las {fmt.hhmm(t.start_ts, tz)}",
            t.id,
        )
        for t in trips
        if t.start_ts >= since and t.coolant_max is not None and t.coolant_max >= OVERHEAT_C
    ]


def _no_obd(trips, since, tz) -> list[Alert]:
    return [
        Alert(
            f"no_obd:{t.id}", "no_obd", "info", t.start_ts,
            "Trayecto sin datos del motor",
            f"{fmt.num(t.distance_m / 1000, 1)} km · {_lower_first(fmt.full_day(t.start_ts, tz))}"
            f" a las {fmt.hhmm(t.start_ts, tz)}",
            t.id,
        )
        for t in trips
        if t.start_ts >= since and not t.has_obd
    ]


def _obd_alerts(conn, trips, since, now_ms, tz) -> list[Alert]:
    lows: dict[str, tuple[float, int]] = {}
    running: dict[str, list[tuple[int, float]]] = {}
    for session_id, ts, data in _records(conn, "obd", since):
        values = data.get("values") or {}
        v = values.get("voltage_v")
        if v is None:
            continue
        v = float(v)
        rpm = values.get("rpm")
        if rpm is None:
            stopped = v < ENGINE_ON_VOLTAGE
        else:
            stopped = rpm == 0
            if rpm > 0:
                running.setdefault(session_id, []).append((ts, v))
        if stopped and v < BATTERY_LOW_V:
            best = lows.get(session_id)
            if best is None or v < best[0]:
                lows[session_id] = (v, ts)
    out: list[Alert] = []
    for session_id, (v, ts) in lows.items():
        out.append(Alert(
            f"battery_low:{session_id}:{ts}", "battery_low", "warn", ts,
            f"Batería baja: {fmt.num(v, 1)} V",
            f"Con el motor parado, {fmt.when(ts, now_ms, tz)}",
            _trip_id(trips, ts),
        ))

    def bad(v: float) -> bool:
        return v < CHARGE_MIN_V or v > CHARGE_MAX_V

    for session_id, samples in running.items():
        for (t1, v1), (_, v2) in zip(samples, samples[1:]):
            if bad(v1) and bad(v2):
                out.append(Alert(
                    f"charging:{session_id}:{t1}", "charging", "warn", t1,
                    f"Carga anómala: {fmt.num(v1, 1)} V en marcha",
                    f"Lo normal en marcha es entre {fmt.num(CHARGE_MIN_V, 1)} y "
                    f"{fmt.num(CHARGE_MAX_V, 1)} V",
                    _trip_id(trips, t1),
                ))
                break
    return out


def _stale(conn, trips, now_ms, tz) -> list[Alert]:
    # Deliberately counts every type, health included: a heartbeat means the app is alive.
    row = conn.execute(
        "SELECT session_id, ts FROM records ORDER BY ts DESC, seq DESC LIMIT 1"
    ).fetchone()
    if row is None or now_ms - row[1] <= STALE_MS:
        return []
    session_id, ts = row
    days = (now_ms - ts) // DAY_MS
    return [Alert(
        f"stale:{session_id}:{ts}", "stale", "info", ts,
        f"Sin datos desde hace {days} días",
        f"Último dato: {fmt.when(ts, now_ms, tz)}", _trip_id(trips, ts),
    )]


def compute_alerts(conn: sqlite3.Connection, trips: list[Trip], now_ms: int, tz: str) -> list[Alert]:
    since = now_ms - WINDOW_MS
    alerts = (
        _new_dtc(conn, trips, since)
        + _overheat(trips, since, tz)
        + _obd_alerts(conn, trips, since, now_ms, tz)
        + _no_obd(trips, since, tz)
        + _stale(conn, trips, now_ms, tz)
    )
    alerts.sort(key=lambda a: a.id)
    alerts.sort(key=lambda a: a.ts, reverse=True)
    return alerts


def recent_count(alerts: list[Alert], now_ms: int) -> int:
    return sum(1 for a in alerts if a.ts >= now_ms - RECENT_MS)
