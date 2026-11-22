from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from app.location import GpsPoint
from app.trip_text import (
    format_trip_detail, format_trip_list, has_route, trip_list_keyboard,
)
from app.trips import Trip

TZ = "Europe/Madrid"


def ms(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=ZoneInfo(TZ)).timestamp() * 1000)


def mk(id_, start, end, km=6.3, **kw):
    base = dict(
        id=id_, start_ts=start, end_ts=end, distance_m=km * 1000,
        max_kmh=62.0, has_obd=True, idle_ms=3 * 60_000, coolant_start=40.0,
        coolant_max=87.0, rpm_avg=1450.0, rpm_max=3200.0, new_dtcs=[], points=[],
    )
    base.update(kw)
    return Trip(**base)


NOW = ms(2026, 11, 21, 20, 0)


def three():
    return [
        mk("a", ms(2026, 11, 21, 18, 26), ms(2026, 11, 21, 18, 33), km=2.1),
        mk("b", ms(2026, 11, 20, 23, 55) + 40_000, ms(2026, 11, 21, 0, 0), km=1.0),
        mk("c", ms(2026, 11, 20, 18, 12), ms(2026, 11, 20, 18, 26), km=5.2),
    ]


def test_list_text():
    assert format_trip_list(three(), NOW, TZ) == (
        "🚗 <b>Últimos trayectos</b>\n"
        "\n"
        "<b>Hoy</b>\n"
        "1️⃣ 18:26 → 18:33 · <b>2,1 km</b> · 7 min\n"
        "\n"
        "<b>Ayer</b>\n"
        "2️⃣ 23:55 → 00:00 · <b>1,0 km</b> · 4 min\n"
        "3️⃣ 18:12 → 18:26 · <b>5,2 km</b> · 14 min"
    )


def test_list_min_one_minute():
    t = mk("c", ms(2026, 11, 21, 18, 0), ms(2026, 11, 21, 18, 0) + 10_000, km=0.4)
    assert "<b>0,4 km</b> · 1 min" in format_trip_list([t], NOW, TZ)


def test_keyboard():
    ts = three()
    kb = trip_list_keyboard(ts, False)
    assert kb == {"inline_keyboard": [[
        {"text": "1️⃣", "callback_data": "trip:a"},
        {"text": "2️⃣", "callback_data": "trip:b"},
        {"text": "3️⃣", "callback_data": "trip:c"},
    ]]}
    kb = trip_list_keyboard(ts, True)
    assert kb["inline_keyboard"][1] == [
        {"text": "⬅️ Anteriores", "callback_data": f"trips:{ts[-1].start_ts}"}
    ]
    assert trip_list_keyboard([], True) is None


def full():
    return mk("a", ms(2026, 11, 20, 18, 12), ms(2026, 11, 20, 18, 26), km=5.2,
              max_kmh=80.0, idle_ms=int(3.78 * 60_000), coolant_start=74.0,
              coolant_max=91.0, rpm_avg=1305.0, rpm_max=2771.0)


def test_detail_full():
    assert format_trip_detail(full(), TZ, True) == (
        "🚗 <b>Viernes 20 de noviembre</b>\n"
        "🕒 18:12 → 18:26 · 14 min\n"
        "\n"
        "📏 <b>5,2 km</b> · media 22 km/h · máx. 80 km/h\n"
        "\n"
        "⚙️ <b>Motor</b>\n"
        "• Ralentí: 4 min (27 %)\n"
        "• Temperatura: de 74 a 91 °C\n"
        "• Revoluciones: media 1.305 · máx. 2.771 rpm\n"
        "\n"
        "⚠️ Averías nuevas: ninguna"
    )


def test_detail_no_obd():
    t = replace(full(), has_obd=False)
    assert format_trip_detail(t, TZ, True) == (
        "🚗 <b>Viernes 20 de noviembre</b>\n"
        "🕒 18:12 → 18:26 · 14 min\n"
        "\n"
        "📏 <b>5,2 km</b> · media 22 km/h · máx. 80 km/h\n"
        "\n"
        "⚙️ Sin datos del motor en este trayecto\n"
        "\n"
        "⚠️ Averías nuevas: ninguna"
    )


def test_detail_no_max_speed():
    t = replace(full(), max_kmh=None)
    assert "📏 <b>5,2 km</b> · media 22 km/h\n" in format_trip_detail(t, TZ, True)
    assert "máx. None" not in format_trip_detail(t, TZ, True)


def test_detail_dtcs():
    t = replace(full(), new_dtcs=["P0401", "P0409"])
    assert format_trip_detail(t, TZ, True).endswith("⚠️ Averías nuevas: P0401, P0409")


def test_detail_dtcs_escaped():
    t = replace(full(), new_dtcs=["<b>"])
    assert format_trip_detail(t, TZ, True).endswith("⚠️ Averías nuevas: &lt;b&gt;")


def test_detail_dtcs_none_omitted():
    t = replace(full(), new_dtcs=None)
    assert "Averías" not in format_trip_detail(t, TZ, True)


def test_detail_partial_obd_lines_omitted():
    t = replace(full(), coolant_start=None, rpm_avg=None)
    out = format_trip_detail(t, TZ, True)
    assert "Temperatura" not in out and "Revoluciones" not in out and "Ralentí" in out


def test_detail_no_route():
    out = format_trip_detail(full(), TZ, False)
    assert out.endswith("⚠️ Averías nuevas: ninguna\n\n📎 Sin posiciones GPS válidas para la ruta")


def test_midnight_crossing_shows_start_day():
    t = mk("a", ms(2026, 11, 20, 23, 50), ms(2026, 11, 21, 0, 20))
    assert format_trip_detail(t, TZ, True).startswith("🚗 <b>Viernes 20 de noviembre</b>")
    assert "<b>Ayer</b>\n1️⃣ 23:50 → 00:20" in format_trip_list([t], NOW, TZ)


def gp(lat, lon, ts=0):
    return GpsPoint(ts=ts, lat=lat, lon=lon, acc_m=5.0, speed_mps=10.0)


def test_has_route():
    assert has_route([gp(40.4168, -3.7038), gp(40.4268, -3.6938)])
    assert not has_route([])
    assert not has_route([gp(40.4168, -3.7038)])
    assert not has_route([gp(40.4168, -3.7038)] * 5)


def test_format_journey_detail_and_list_line():
    from app.journeys import JourneyView
    from app.trip_text import format_journey_detail

    a = mk("a", NOW - 7_200_000, NOW - 6_000_000, km=10)
    b = mk("b", NOW - 5_760_000, NOW - 4_800_000, km=5)
    v = JourneyView(1, [a, b])
    out = format_journey_detail(v, TZ, True)
    assert "• Tramo 1:" in out and "• Tramo 2:" in out and "⏸️ Parada de 4 min" in out
    assert "<b>15,0 km</b>" in out and "al volante" in out
    assert "2 tramos" in format_trip_list([v], NOW, TZ)
    assert trip_list_keyboard([v], False)["inline_keyboard"][0][0]["callback_data"] == "trip:v1"
