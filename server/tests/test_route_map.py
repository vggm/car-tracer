import io

import pytest
from PIL import Image

from app import route_map
from app.location import GpsPoint
from app.route_map import HEIGHT, WIDTH, render_route_png


def gp(lat, lon):
    return GpsPoint(ts=0, lat=lat, lon=lon, acc_m=5.0, speed_mps=10.0)


def solid_tile():
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (200, 220, 200)).save(buf, "PNG")
    return buf.getvalue()


class Fetcher:
    def __init__(self, data=None, fill=True):
        self.calls = []
        self.data = solid_tile() if fill else None

    def __call__(self, z, x, y):
        self.calls.append((z, x, y))
        return self.data


def route(km, n=30):
    d = km / 111.195
    return [gp(40.4168 + d * i / (n - 1), -3.7038 + 0.3 * d * i / (n - 1)) for i in range(n)]


def decode(png):
    return Image.open(io.BytesIO(png)).convert("RGB")


def pixel_of(points, f, zoom, idx):
    # re-derive projection using module helpers
    pts = [route_map.to_pixel(p.lat, p.lon, zoom) for p in points]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    px, py = pts[idx]
    return round(WIDTH / 2 + px - cx), round(HEIGHT / 2 + py - cy)


def test_renders_png_with_markers():
    pts = route(1.0)
    f = Fetcher()
    img = decode(render_route_png(pts, f))
    assert img.size == (1024, 768)
    zoom = max(z for z, _, _ in f.calls)
    sx, sy = pixel_of(pts, f, zoom, 0)
    ex, ey = pixel_of(pts, f, zoom, -1)
    r, g, b = img.getpixel((sx, sy))
    assert g > r and g > b
    r, g, b = img.getpixel((ex, ey))
    assert r > g and r > b


def test_zoom_depends_on_route_length():
    short, long_ = Fetcher(), Fetcher()
    render_route_png(route(1.0), short)
    render_route_png(route(60.0), long_)
    zs, zl = short.calls[0][0], long_.calls[0][0]
    assert zs >= 15
    assert zl < zs


def test_none_tiles_still_render():
    img = decode(render_route_png(route(1.0), Fetcher(fill=False)))
    assert img.size == (1024, 768)


def test_undecodable_tile_still_renders():
    img = decode(render_route_png(route(1.0), lambda z, x, y: b"junk"))
    assert img.size == (1024, 768)


def test_needs_two_points():
    with pytest.raises(ValueError):
        render_route_png([gp(40.4, -3.7)], Fetcher())
    with pytest.raises(ValueError):
        render_route_png([], Fetcher())


def test_only_valid_tile_coordinates():
    for pts in (route(1.0), route(60.0), [gp(40.0, 179.99), gp(40.0, -179.99)],
                [gp(84.0, 10.0), gp(85.0, 10.1)]):
        f = Fetcher()
        render_route_png(pts, f)
        assert f.calls
        for z, x, y in f.calls:
            assert 0 <= x < 2 ** z and 0 <= y < 2 ** z
