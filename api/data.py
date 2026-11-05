"""Read published products (latest.json, point tiles) with small in-memory caches. Standard library only."""

import json
import os
import threading
import time
import urllib.request
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from common import config


def base_url() -> str:
    """Published data root, from env DATA_BASE_URL or config."""
    return os.environ.get("DATA_BASE_URL", config.DATA_BASE_URL).rstrip("/")


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": config.HTTP_USER_AGENT})
    with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


class Store:
    """latest.json (re-read every META_CACHE_S) and point tiles (LRU, keyed by run and tile)."""

    def __init__(self, fetch: Callable[[str], Any] = _get_json, clock: Callable[[], float] = time.monotonic) -> None:
        self._fetch, self._clock, self._lock = fetch, clock, threading.Lock()
        self._meta: tuple[float, dict] | None = None
        self._tiles: OrderedDict[tuple[str, int, int], dict] = OrderedDict()

    def meta(self) -> dict:
        """Current run metadata."""
        with self._lock:
            if self._meta is None or self._clock() - self._meta[0] > config.META_CACHE_S:
                self._meta = (self._clock(), self._fetch(f"{base_url()}/latest.json"))
            return self._meta[1]

    def tile(self, run_id: str, ti: int, tj: int) -> dict:
        """One point tile of a run."""
        key = (run_id, ti, tj)
        with self._lock:
            if key in self._tiles:
                self._tiles.move_to_end(key)
                return self._tiles[key]
        t = self._fetch(f"{base_url()}/{run_id}/points/t{ti}_{tj}.json")
        with self._lock:
            self._tiles[key] = t
            while len(self._tiles) > config.TILE_CACHE_SIZE:
                self._tiles.popitem(last=False)
        return t


def cell_index(meta: dict, lat: float, lon: float) -> tuple[int, int]:
    """Nearest grid cell (row j north->south, column i west->east); ValueError outside the grid."""
    g = meta["grid"]
    j = round((g["lat_first"] - lat) / g["step_deg"])
    i = round((lon - g["lon_first"]) / g["step_deg"])
    if not (0 <= j < g["n_lat"] and 0 <= i < g["n_lon"]):
        raise ValueError(f"({lat}, {lon}) is outside the forecast area "
                         f"{g['lat_first'] - (g['n_lat'] - 1) * g['step_deg']}–{g['lat_first']} N, "
                         f"{g['lon_first']}–{g['lon_first'] + (g['n_lon'] - 1) * g['step_deg']} E")
    return j, i


def current_block(meta: dict, now_utc: datetime) -> int | None:
    """Index of the block containing now_utc, or None if now is outside the run's blocks."""
    for k, b in enumerate(meta["blocks"]):
        if datetime.fromisoformat(b["start_utc"]) <= now_utc < datetime.fromisoformat(b["end_utc"]):
            return k
    return None


def data_status(meta: dict, now_utc: datetime) -> str:
    """'fresh', 'stale' (a run was missed) or 'expired' (no 48-h summary for now)."""
    run = datetime.fromisoformat(meta["run_time_utc"])
    k = current_block(meta, now_utc)
    if k is None or k >= meta["summary_start_blocks"]:
        return "expired"
    return "stale" if now_utc - run > timedelta(hours=config.STALE_AFTER_H) else "fresh"
