import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import pytest

from app.gpx import to_gpx
from app.location import GpsPoint

TZ = "Europe/Madrid"
GPX_NS = "{http://www.topografix.com/GPX/1/1}"


def ms(y, mo, d, h, mi, s=0):
    return int(datetime(y, mo, d, h, mi, s, tzinfo=UTC).timestamp() * 1000)


def P(ts, lat, lon):
    return GpsPoint(ts=ts, lat=lat, lon=lon, acc_m=5.0, speed_mps=None)


def test_gpx_is_valid_xml_with_points():
    start = ms(2025, 11, 18, 16, 0, 0)
    points = [
        P(start, 40.0001, -3.0001),
        P(start + 10_000, 40.0002, -3.0002),
        P(start + 20_000, 40.0003, -3.0003),
    ]
    _, data = to_gpx(points, start, TZ)

    root = ET.fromstring(data)
    assert root.tag == GPX_NS + "gpx"
    assert root.get("version") == "1.1"

    trkpts = root.findall(f"{GPX_NS}trk/{GPX_NS}trkseg/{GPX_NS}trkpt")
    assert len(trkpts) == 3
    for trkpt, src in zip(trkpts, points):
        assert float(trkpt.get("lat")) == src.lat
        assert float(trkpt.get("lon")) == src.lon
    assert trkpts[0].find(f"{GPX_NS}time").text == "2025-11-18T16:00:00Z"
    assert trkpts[0].find(f"{GPX_NS}ele") is None


def test_gpx_filename_uses_local_time():
    start = ms(2026, 11, 20, 17, 12, 0)
    name, _ = to_gpx([P(start, 40.0, -3.0)], start, TZ)
    assert name == "trayecto-2026-11-20-1812.gpx"


def test_gpx_empty_raises():
    with pytest.raises(ValueError):
        to_gpx([], ms(2025, 11, 18, 16, 0), TZ)


def test_gpx_coordinates_use_fixed_decimals():
    start = ms(2025, 11, 18, 16, 0, 0)
    _, data = to_gpx([P(start, 40.0, 0.00001)], start, TZ)
    pt = ET.fromstring(data).find(f".//{GPX_NS}trkpt")
    assert pt.get("lon") == "0.0000100"
    assert pt.get("lat") == "40.0000000"
