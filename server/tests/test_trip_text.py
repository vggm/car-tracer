from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from urllib.parse import parse_qs, urlsplit

from app.location import GpsPoint, _haversine_m
from app.trip_text import (
    format_trip_detail, format_trip_list, maps_url, trip_detail_keyboard, trip_list_keyboard,
)
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


def straight(n):
    return [gp(40.4168 + i * 0.001, -3.7038, ts=i * 1000) for i in range(n)]


def query(url):
    return parse_qs(urlsplit(url).query)


def test_maps_url_two_points_no_waypoints():
    url = maps_url([gp(40.4168, -3.7038), gp(40.4268, -3.6938)])
    assert url == ("https://www.google.com/maps/dir/?api=1&origin=40.41680%2C-3.70380"
                   "&destination=40.42680%2C-3.69380&travelmode=driving")
    assert "waypoints" not in url


def test_maps_url_long_route_has_eight_ordered_waypoints():
    pts = straight(50)
    url = maps_url(pts)
    q = query(url)
    assert q["origin"] == ["40.41680,-3.70380"]
    assert q["destination"] == [f"{40.4168 + 49 * 0.001:.5f},-3.70380"]
    wps = q["waypoints"][0].split("|")
    assert len(wps) == 8
    lats = [float(w.split(",")[0]) for w in wps]
    assert lats == sorted(lats) and len(set(lats)) == 8
    steps = [b - a for a, b in zip([40.4168] + lats, lats + [40.4168 + 49 * 0.001])]
    assert max(steps) - min(steps) < 0.0025  # roughly even (point granularity 0.001)
    assert url.index("origin") < url.index("destination") < url.index("travelmode") < url.index("waypoints")


def test_maps_url_even_by_distance_not_by_index():
    # 40 points bunched near the start, 10 spread far away: index sampling would
    # put all waypoints in the bunch; distance sampling must reach the far part.
    pts = [gp(40.4168 + i * 0.00001, -3.7038) for i in range(40)]
    pts += [gp(40.4168 + 0.01 * (j + 1), -3.7038) for j in range(10)]
    wps = query(maps_url(pts))["waypoints"][0].split("|")
    assert len(wps) == 8
    assert float(wps[-1].split(",")[0]) > 40.4168 + 0.05


def test_maps_url_coordinates_five_decimals_and_encoding():
    url = maps_url([gp(40.416812345, -3.703812345), gp(40.426, -3.69), gp(40.43, -3.68)])
    assert "origin=40.41681%2C-3.70381" in url
    assert "%7C" not in url or "waypoints" in url
    url = maps_url(straight(20))
    assert "%2C" in url and "%7C" in url
    assert "," not in url.split("?", 1)[1] and "|" not in url


def test_maps_url_none_for_few_or_zero_distance_points():
    assert maps_url([]) is None
    assert maps_url([gp(40.4168, -3.7038)]) is None
    assert maps_url([gp(40.4168, -3.7038)] * 5) is None


def test_maps_url_skips_repeated_coordinates():
    pts = [gp(40.4168, -3.7038)] * 5 + [gp(40.4178, -3.7038)] * 5 + [gp(40.4188, -3.7038)] * 5
    q = query(maps_url(pts))
    assert q["waypoints"][0].split("|") == ["40.41780,-3.70380"]


def test_trip_detail_keyboard_shape():
    url = maps_url(straight(5))
    assert trip_detail_keyboard(straight(5)) == {
        "inline_keyboard": [[{"text": "🗺️ Ver en Google Maps", "url": url}]]}


def test_trip_detail_keyboard_none_without_url():
    assert trip_detail_keyboard([]) is None
    assert trip_detail_keyboard([gp(40.4168, -3.7038)]) is None
