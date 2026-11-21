"""GPX 1.1 export of a trip route."""
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.location import GpsPoint

GPX_NS = "http://www.topografix.com/GPX/1/1"
ET.register_namespace("", GPX_NS)


def _q(tag: str) -> str:
    return f"{{{GPX_NS}}}{tag}"


def to_gpx(points: list[GpsPoint], start_ts: int, tz: str) -> tuple[str, bytes]:
    """Return (filename, UTF-8 GPX bytes) for a trip.

    The filename uses the local time (``tz``) of ``start_ts`` (ms UTC).
    Raises ValueError when ``points`` is empty.
    """
    if not points:
        raise ValueError("cannot export an empty trip")
    local = datetime.fromtimestamp(start_ts / 1000, ZoneInfo(tz))
    name = f"trayecto-{local:%Y-%m-%d-%H%M}"

    gpx = ET.Element(_q("gpx"), {"version": "1.1", "creator": "car-trace"})
    trk = ET.SubElement(gpx, _q("trk"))
    ET.SubElement(trk, _q("name")).text = name
    seg = ET.SubElement(trk, _q("trkseg"))
    for p in points:
        trkpt = ET.SubElement(seg, _q("trkpt"), {"lat": str(p.lat), "lon": str(p.lon)})
        t = datetime.fromtimestamp(p.ts / 1000, UTC)
        ET.SubElement(trkpt, _q("time")).text = t.strftime("%Y-%m-%dT%H:%M:%SZ")

    data = ET.tostring(gpx, encoding="utf-8", xml_declaration=True)
    return f"{name}.gpx", data
