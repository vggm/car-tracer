"""Render a GPS track over OpenStreetMap tiles as a PNG (pure: tiles come from a callable)."""
import io
import logging
import math
from collections.abc import Callable

from PIL import Image, ImageDraw, ImageFont

from app.location import GpsPoint

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 1024, 768
PADDING = 60
TILE = 256
MAX_ZOOM = 17
MIN_ZOOM = 3

_MAX_LAT = 85.05112878
_GREY = (221, 221, 221)
_BLUE = "#1f5fd6"
_GREEN = "#1e9e4a"
_RED = "#d62f2f"
_ATTRIBUTION = "© OpenStreetMap"


def to_pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Global Web Mercator pixel coordinates at the given zoom."""
    lat = max(-_MAX_LAT, min(_MAX_LAT, lat))
    scale = TILE * 2 ** zoom
    x = (lon + 180.0) / 360.0 * scale
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * scale
    return x, y


def _bbox_size(points: list[GpsPoint], zoom: int) -> tuple[float, float]:
    pts = [to_pixel(p.lat, p.lon, zoom) for p in points]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return max(xs) - min(xs), max(ys) - min(ys)


def _pick_zoom(points: list[GpsPoint]) -> int:
    avail_w, avail_h = WIDTH - 2 * PADDING, HEIGHT - 2 * PADDING
    for z in range(MAX_ZOOM, MIN_ZOOM - 1, -1):
        w, h = _bbox_size(points, z)
        if w <= avail_w and h <= avail_h:
            return z
    return MIN_ZOOM


def _tile_image(data: bytes | None) -> Image.Image:
    if data is not None:
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
            return img.convert("RGB")
        except Exception as e:
            log.warning("undecodable tile (%s)", type(e).__name__)
    return Image.new("RGB", (TILE, TILE), _GREY)


def _marker(draw: ImageDraw.ImageDraw, xy: tuple[int, int], color: str) -> None:
    x, y = xy
    r = 9
    draw.ellipse((x - r, y - r, x + r, y + r), fill=color, outline="white", width=3)


def _attribution(img: Image.Image) -> Image.Image:
    try:
        font = ImageFont.load_default(size=12)
    except TypeError:  # Pillow without FreeType size support
        font = ImageFont.load_default()
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    left, top, right, bottom = d.textbbox((0, 0), _ATTRIBUTION, font=font)
    tw, th = right - left, bottom - top
    x1, y1 = WIDTH, HEIGHT
    x0, y0 = x1 - tw - 10, y1 - th - 8
    d.rectangle((x0, y0, x1, y1), fill=(255, 255, 255, 180))
    d.text((x0 + 5 - left, y0 + 4 - top), _ATTRIBUTION, font=font, fill=(40, 40, 40, 255))
    return Image.alpha_composite(img, overlay)


def render_route_png(points: list[GpsPoint],
                     fetch_tile: Callable[[int, int, int], bytes | None]) -> bytes:
    if len(points) < 2:
        raise ValueError("a route needs at least 2 points")
    zoom = _pick_zoom(points)
    pix = [to_pixel(p.lat, p.lon, zoom) for p in points]
    xs = [p[0] for p in pix]
    ys = [p[1] for p in pix]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    origin_x, origin_y = cx - WIDTH / 2, cy - HEIGHT / 2  # global pixel of the image's top-left

    n = 2 ** zoom
    img = Image.new("RGB", (WIDTH, HEIGHT), _GREY)
    for ty in range(math.floor(origin_y / TILE), math.floor((origin_y + HEIGHT - 1) / TILE) + 1):
        if not 0 <= ty < n:
            continue
        for tx in range(math.floor(origin_x / TILE),
                        math.floor((origin_x + WIDTH - 1) / TILE) + 1):
            tile = _tile_image(fetch_tile(zoom, tx % n, ty))
            img.paste(tile, (round(tx * TILE - origin_x), round(ty * TILE - origin_y)))

    img = img.convert("RGBA")
    draw = ImageDraw.Draw(img)
    line = [(round(x - origin_x), round(y - origin_y)) for x, y in pix]
    draw.line(line, fill="white", width=10, joint="curve")
    draw.line(line, fill=_BLUE, width=6, joint="curve")
    _marker(draw, line[0], _GREEN)
    _marker(draw, line[-1], _RED)
    img = _attribution(img)

    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    return out.getvalue()
