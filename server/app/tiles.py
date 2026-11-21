"""On-disk cache for OpenStreetMap tiles (polite: sequential, identified, cached)."""
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = "car-trace-bot/1.0 (self-hosted, personal use)"
MAX_AGE_S = 7 * 24 * 3600
TIMEOUT_S = 5.0
BACKOFF_S = 60.0


class TileCache:
    def __init__(self, directory: Path, http: httpx.Client,
                 now: Callable[[], float] = time.time):
        self._dir = Path(directory)
        self._http = http
        self._now = now
        self._down_until = 0.0

    def fetch(self, z: int, x: int, y: int) -> bytes | None:
        path = self._dir / str(z) / str(x) / f"{y}.png"
        stale: bytes | None = None
        try:
            age = self._now() - path.stat().st_mtime
            data = path.read_bytes()
            if age < MAX_AGE_S:
                return data
            stale = data
        except OSError:
            pass
        if self._now() < self._down_until:
            return stale
        try:
            resp = self._http.get(URL.format(z=z, x=x, y=y),
                                  headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S)
            resp.raise_for_status()
            data = resp.content
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{y}.png.tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)
            self._down_until = 0.0
            return data
        except Exception as e:
            self._down_until = self._now() + BACKOFF_S
            log.warning("tile %s/%s/%s fetch failed (%s)", z, x, y, type(e).__name__)
            return stale
