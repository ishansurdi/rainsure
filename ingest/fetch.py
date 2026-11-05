"""Byte-range download of tp members from ECMWF open data, with retries (DECISIONS.md D34, D35, D40)."""

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, NamedTuple

from common import config
from common.time import validate_run_time

log = logging.getLogger(__name__)


class IndexEntry(NamedTuple):
    """One GRIB message in a file, from its .index line."""

    number: int
    offset: int
    length: int


class DownloadError(RuntimeError):
    """A download failed after all retries, or returned the wrong number of bytes."""


def parse_index(text: str) -> list[dict[str, Any]]:
    """Parse an open-data .index file (one JSON object per line)."""
    rows = []
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"bad .index line {n}: {e}") from e
    return rows


def tp_member_entries(rows: list[dict[str, Any]], member_type: str, step_h: int) -> list[IndexEntry]:
    """Pick the tp messages of the given member type and step; require members 1..EXPECTED_MEMBERS exactly once."""
    picked = [r for r in rows if r.get("param") == "tp" and r.get("type") == member_type]
    wrong_step = [r for r in picked if int(r["step"]) != step_h]
    if wrong_step:
        raise ValueError(f"index has tp at step {wrong_step[0]['step']}, expected {step_h}")
    entries = sorted(IndexEntry(int(r["number"]), int(r["_offset"]), int(r["_length"])) for r in picked)
    numbers = [e.number for e in entries]
    if numbers != list(range(1, config.EXPECTED_MEMBERS + 1)):
        raise ValueError(f"expected tp members 1..{config.EXPECTED_MEMBERS}, got {len(numbers)}: {numbers[:5]}...")
    return entries


def file_url(source: str, run_time_utc: datetime, model: str, step_h: int, ext: str) -> str:
    """URL of a model's ensemble file for one step; ext is 'grib2' or 'index'."""
    validate_run_time(run_time_utc)
    spec = config.MODELS[model]
    stamp = run_time_utc.strftime("%Y%m%d%H0000")
    return (f"{config.SOURCE_URLS[source]}/{run_time_utc:%Y%m%d}/{run_time_utc:%H}z/{spec.directory}/"
            f"{stamp}-{step_h}h-enfo-{spec.file_type}.{ext}")


def _wait_s(err: urllib.error.HTTPError | None, attempt: int) -> float:
    """Seconds to wait before the next attempt: Retry-After if given, else exponential backoff."""
    retry_after = err.headers.get("Retry-After") if err is not None and err.headers else None
    if retry_after is not None and retry_after.strip().isdigit():
        return float(retry_after)
    return config.HTTP_BACKOFF_BASE_S * 2 ** (attempt - 1)


def http_get(url: str, byte_range: tuple[int, int] | None = None, *,
             opener: Callable[..., Any] = urllib.request.urlopen,
             sleep: Callable[[float], None] = time.sleep) -> bytes:
    """GET url (optionally bytes offset..offset+length-1) with timeout, retries and a length check."""
    headers = {"User-Agent": config.HTTP_USER_AGENT}
    if byte_range is not None:
        offset, length = byte_range
        headers["Range"] = f"bytes={offset}-{offset + length - 1}"
    last_error = "no attempt made"
    for attempt in range(1, config.HTTP_MAX_ATTEMPTS + 1):
        http_err = None
        try:
            with opener(urllib.request.Request(url, headers=headers), timeout=config.HTTP_TIMEOUT_S) as resp:
                body = resp.read()
            if byte_range is None or len(body) == byte_range[1]:
                return body
            last_error = f"got {len(body)} bytes, expected {byte_range[1]}"
        except urllib.error.HTTPError as e:
            if e.code not in config.HTTP_RETRY_STATUS:
                raise DownloadError(f"HTTP {e.code} for {url}") from e
            http_err, last_error = e, f"HTTP {e.code}"
        except (urllib.error.URLError, OSError) as e:  # timeouts, resets, TLS EOF
            last_error = f"{type(e).__name__}: {e}"
        if attempt < config.HTTP_MAX_ATTEMPTS:
            wait = _wait_s(http_err, attempt)
            log.warning("retry %d/%d in %.0fs for %s (%s)", attempt, config.HTTP_MAX_ATTEMPTS, wait, url, last_error)
            sleep(wait)
    raise DownloadError(f"{url}: failed after {config.HTTP_MAX_ATTEMPTS} attempts ({last_error})")


def fetch_tp_messages(run_time_utc: datetime, model: str, step_h: int, source: str) -> list[tuple[int, bytes]]:
    """Download the tp GRIB message of every member for one step; returns (member number, bytes) sorted."""
    index_rows = parse_index(http_get(file_url(source, run_time_utc, model, step_h, "index")).decode())
    entries = tp_member_entries(index_rows, config.MODELS[model].member_type, step_h)
    grib_url = file_url(source, run_time_utc, model, step_h, "grib2")
    with ThreadPoolExecutor(config.HTTP_WORKERS) as pool:
        bodies = list(pool.map(lambda e: http_get(grib_url, (e.offset, e.length)), entries))
    return [(e.number, b) for e, b in zip(entries, bodies)]
