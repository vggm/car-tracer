"""Read-only JSON API for the web panel."""
import threading
import time
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from app.alerts import compute_alerts, recent_count
from app.panel import stats
from app.trips import get_trip

router = APIRouter(prefix="/api/panel")

ALERTS_TTL_S = 60
_mono = time.monotonic
_alerts_lock = threading.Lock()


def _alerts(state, db) -> list:
    """compute_alerts memoized for ALERTS_TTL_S, invalidated when any session changes."""
    trips, fingerprint = state.trip_cache.snapshot(db)
    with _alerts_lock:
        memo = state.alerts_memo
        if memo is not None and memo[0] == fingerprint and _mono() < memo[1]:
            return memo[2]
    found = compute_alerts(db, trips, state.clock(), state.settings.tz)
    with _alerts_lock:
        state.alerts_memo = (fingerprint, _mono() + ALERTS_TTL_S, found)
    return found


def _month(request: Request, month: str | None) -> tuple[int, int]:
    if month is None:
        return stats.current_month(request.app.state.clock(), request.app.state.settings.tz)
    try:
        return stats.parse_month(month)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid month") from None


def _month_str(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


@router.get("/overview")
def overview(request: Request, month: str | None = None) -> dict:
    state = request.app.state
    db = state.readers.get()
    tz = state.settings.tz
    year, mon = _month(request, month)
    trips = state.trip_cache.all_trips(db)
    alerts = _alerts(state, db)
    return {
        "month": _month_str(year, mon),
        "totals": stats.totals(stats.trips_in_month(trips, year, mon, tz)),
        "months": stats.months_series(trips, year, mon, tz),
        "days": stats.days_series(trips, year, mon, tz),
        "alerts_recent": recent_count(alerts, state.clock()),
    }


@router.get("/trips")
def trips(request: Request, month: str | None = None) -> dict:
    state = request.app.state
    db = state.readers.get()
    year, mon = _month(request, month)
    in_month = stats.trips_in_month(
        state.trip_cache.all_trips(db), year, mon, state.settings.tz)
    in_month = sorted(in_month, key=lambda t: t.start_ts, reverse=True)
    return {
        "month": _month_str(year, mon),
        "trips": [stats.trip_summary(t) for t in in_month],
    }


@router.get("/trips/{trip_id}")
def trip(request: Request, trip_id: str) -> dict:
    state = request.app.state
    db = state.readers.get()
    found = get_trip(db, trip_id)
    if found is None:
        raise HTTPException(status_code=404, detail="trip not found")
    return stats.trip_detail(db, found)


@router.get("/dtc")
def dtc(request: Request) -> dict:
    db = request.app.state.readers.get()
    return {"current": stats.dtc_state(db), "history": stats.dtc_history(db)}


@router.get("/alerts")
def alerts(request: Request) -> dict:
    state = request.app.state
    db = state.readers.get()
    found = _alerts(state, db)
    return {"alerts": [asdict(a) for a in found]}
