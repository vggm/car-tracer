"""Read-only JSON API for the web panel."""
import contextlib
import threading
import time
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.alerts import compute_alerts, recent_count
from app import db as db_mod
from app import journeys as journeys_mod
from app.panel import stats
from app.trips import get_trip, parse_trip_ts, range_trips

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
    items = journeys_mod.group_items(trips, journeys_mod.load_journeys(db))
    alerts = _alerts(state, db)
    return {
        "month": _month_str(year, mon),
        "totals": stats.totals(stats.items_in_month(items, year, mon, tz)),
        "months": stats.months_series(items, year, mon, tz),
        "days": stats.days_series(items, year, mon, tz),
        "alerts_recent": recent_count(alerts, state.clock()),
    }


@router.get("/trips")
def trips(request: Request, month: str | None = None) -> dict:
    state = request.app.state
    db = state.readers.get()
    tz = state.settings.tz
    year, mon = _month(request, month)
    items = journeys_mod.group_items(
        state.trip_cache.all_trips(db), journeys_mod.load_journeys(db))
    key = _month_str(year, mon)
    # group_items is newest first; gaps look at the next (older) item of the whole list,
    # but only the requested month is summarised
    return {
        "month": key,
        "trips": stats.with_gaps(items, tz, keep=lambda i: stats.month_key(i.start_ts, tz) == key),
    }


@router.get("/trips/{trip_id}")
def trip(request: Request, trip_id: str) -> dict:
    state = request.app.state
    db = state.readers.get()
    all_trips = state.trip_cache.all_trips(db)
    ts = parse_trip_ts(trip_id)
    meta = None if ts is None else next(
        (t for t in all_trips if t.start_ts <= ts <= t.end_ts), None)
    found = None
    if meta is not None:
        found = next((t for t in range_trips(db, meta.start_ts, meta.end_ts)
                      if t.start_ts == meta.start_ts), None)
    if found is None:
        found = get_trip(db, trip_id)
    if found is None:
        raise HTTPException(status_code=404, detail="trip not found")
    jid = journeys_mod.journey_of(
        found, journeys_mod.load_journeys(db), all_trips)
    return {**stats.trip_detail(db, found), "journey_id": jid}


@router.get("/journeys/{jid}")
def journey(request: Request, jid: str) -> dict:
    state = request.app.state
    db = state.readers.get()
    n = journeys_mod.parse_journey_id(jid)
    view = None if n is None else journeys_mod.find_journey(
        state.trip_cache.all_trips(db), journeys_mod.load_journeys(db), n)
    detail = None if view is None else stats.journey_detail(db, view)
    if detail is None:
        raise HTTPException(status_code=404, detail="journey not found")
    return detail


class JoinBody(BaseModel):
    trip_ids: list[str] = Field(min_length=2, max_length=2)


@router.post("/journeys", status_code=201)
def join_journey(request: Request, body: JoinBody) -> dict:
    state = request.app.state
    trips_ = state.trip_cache.all_trips(state.readers.get())
    with contextlib.closing(db_mod.connect_writer(state.settings.db_path)) as conn:
        try:
            n = journeys_mod.join(conn, trips_, body.trip_ids[0], body.trip_ids[1], state.clock())
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
    state.alerts_memo = None
    return {"id": f"v{n}"}


@router.delete("/journeys/{jid}", status_code=204)
def separate_journey(request: Request, jid: str) -> Response:
    state = request.app.state
    n = journeys_mod.parse_journey_id(jid)
    with contextlib.closing(db_mod.connect_writer(state.settings.db_path)) as conn:
        removed = n is not None and journeys_mod.separate(conn, n)
    if not removed:
        raise HTTPException(status_code=404, detail="journey not found")
    state.alerts_memo = None
    return Response(status_code=204)


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
