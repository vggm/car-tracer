"""Read-only JSON API for the web panel."""
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from app.alerts import compute_alerts, recent_count
from app.panel import stats

router = APIRouter(prefix="/api/panel")


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
    tz = state.settings.tz
    year, mon = _month(request, month)
    trips = state.trip_cache.all_trips(state.db)
    alerts = compute_alerts(state.db, trips, state.clock(), tz)
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
    year, mon = _month(request, month)
    in_month = stats.trips_in_month(
        state.trip_cache.all_trips(state.db), year, mon, state.settings.tz)
    in_month = sorted(in_month, key=lambda t: t.start_ts, reverse=True)
    return {
        "month": _month_str(year, mon),
        "trips": [stats.trip_summary(t) for t in in_month],
    }


@router.get("/trips/{trip_id}")
def trip(request: Request, trip_id: str) -> dict:
    state = request.app.state
    found = state.trip_cache.get(state.db, trip_id)
    if found is None:
        raise HTTPException(status_code=404, detail="trip not found")
    return stats.trip_detail(state.db, found)


@router.get("/dtc")
def dtc(request: Request) -> dict:
    db = request.app.state.db
    return {"current": stats.dtc_state(db), "history": stats.dtc_history(db)}


@router.get("/alerts")
def alerts(request: Request) -> dict:
    state = request.app.state
    trips_ = state.trip_cache.all_trips(state.db)
    found = compute_alerts(state.db, trips_, state.clock(), state.settings.tz)
    return {"alerts": [asdict(a) for a in found]}
