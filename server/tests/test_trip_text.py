from datetime import datetime
from zoneinfo import ZoneInfo

from app.trip_text import format_trip_detail, format_trip_list, trip_list_keyboard
from app.trips import Trip

TZ = "Europe/Madrid"


def ms(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


def mk(id_, start, end, km=6.3, **kw):
    base = dict(
        id=id_, session_id="s", start_ts=start, end_ts=end, distance_m=km * 1000,
        max_kmh=62.0, has_obd=True, idle_ms=3 * 60_000, coolant_start=40.0,
        coolant_max=87.0, rpm_avg=1450.0, rpm_max=3200.0, new_dtcs=[], points=[],
    )
    base.update(kw)
    return Trip(**base)


NOW = ms(2026, 11, 21, 20, 0)


def two():
    return [
        mk("a", ms(2026, 11, 21, 18, 12), ms(2026, 11, 21, 18, 26)),
        mk("b", ms(2026, 11, 20, 13, 5), ms(2026, 11, 20, 13, 14), km=3.1),
    ]


def test_list_text():
    assert format_trip_list(two(), NOW, TZ) == (
        "🚗 Últimos trayectos\n"
        "1. Hoy 18:12 → 18:26 · 14 min · 6,3 km\n"
        "2. Ayer 13:05 → 13:14 · 9 min · 3,1 km"
    )


def test_list_min_one_minute():
    t = mk("c", ms(2026, 11, 21, 18, 0), ms(2026, 11, 21, 18, 0) + 10_000, km=0.4)
    assert "· 1 min · 0,4 km" in format_trip_list([t], NOW, TZ)


def test_keyboard():
    ts = two()
    kb = trip_list_keyboard(ts, False)
    assert kb == {"inline_keyboard": [[
        {"text": "1", "callback_data": "trip:a"},
        {"text": "2", "callback_data": "trip:b"},
    ]]}
    kb = trip_list_keyboard(ts, True)
    assert kb["inline_keyboard"][1] == [
        {"text": "⬅️ Anteriores", "callback_data": f"trips:{ts[-1].start_ts}"}
    ]
    assert trip_list_keyboard([], True) is None


def test_detail_spec_example():
    t = mk("a", ms(2026, 11, 20, 18, 12), ms(2026, 11, 20, 18, 26))
    assert format_trip_detail(t, TZ, True) == (
        "🚗 Trayecto del vie 20 nov\n"
        "🕒 18:12 → 18:26 (14 min)\n"
        "📏 6,3 km · media 27 km/h · máx. 62 km/h\n"
        "⏸️ Al ralentí: 3 min (21 %)\n"
        "🌡️ Motor: de 40 °C a 87 °C\n"
        "⚙️ Revoluciones: media 1.450 · máx. 3.200 rpm\n"
        "⚠️ Averías nuevas: ninguna"
    )


def test_detail_no_obd():
    t = mk("a", ms(2026, 11, 19, 18, 12), ms(2026, 11, 19, 18, 26), has_obd=False,
           coolant_start=None, coolant_max=None, rpm_avg=None, rpm_max=None)
    out = format_trip_detail(t, TZ, True)
    assert out.startswith("🚗 Trayecto del jue 19 nov")
    assert "Sin datos del motor en este trayecto" in out
    assert "ralentí" not in out and "Motor:" not in out and "Revoluciones" not in out


def test_detail_dtcs():
    t = mk("a", ms(2026, 11, 20, 18, 12), ms(2026, 11, 20, 18, 26),
           new_dtcs=["P0401", "P0420"])
    assert format_trip_detail(t, TZ, True).endswith("⚠️ Averías nuevas: P0401, P0420")


def test_detail_dtcs_none_omitted():
    t = mk("a", ms(2026, 11, 20, 18, 12), ms(2026, 11, 20, 18, 26), new_dtcs=None)
    assert "Averías" not in format_trip_detail(t, TZ, True)


def test_detail_no_route():
    t = mk("a", ms(2026, 11, 20, 18, 12), ms(2026, 11, 20, 18, 26))
    out = format_trip_detail(t, TZ, False)
    assert out.endswith("📎 Sin posiciones GPS válidas para la ruta")


def test_midnight_crossing_shows_start_day():
    t = mk("a", ms(2026, 11, 20, 23, 50), ms(2026, 11, 21, 0, 20))
    assert format_trip_detail(t, TZ, True).startswith("🚗 Trayecto del vie 20 nov")
    assert "Ayer 23:50 → 00:20 · 30 min" in format_trip_list([t], NOW, TZ)
