"""Record runner facts (Python, installed packages, ecCodes, mirror timings) as JSON for the archive release.

Usage: python -m ingest.runner_checks --out runner_checks.json
"""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from common import config
from ingest.fetch import file_url


def mirror_check(url: str, *, opener: Callable[..., Any] = urllib.request.urlopen,
                 clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """One GET without retries: HTTP status, bytes, seconds and MD5 (8 hex), or the error."""
    t0 = clock()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": config.HTTP_USER_AGENT})
        with opener(req, timeout=config.MIRROR_CHECK_TIMEOUT_S) as resp:
            body = resp.read()
        return {"url": url, "status": 200, "bytes": len(body), "seconds": round(clock() - t0, 2),
                "md5": hashlib.md5(body).hexdigest()[:8]}
    except urllib.error.HTTPError as e:
        return {"url": url, "status": e.code, "seconds": round(clock() - t0, 2)}
    except (urllib.error.URLError, OSError) as e:  # timeouts, DNS, resets
        return {"url": url, "status": None, "seconds": round(clock() - t0, 2), "error": f"{type(e).__name__}: {e}"}


def installed_packages() -> list[str]:
    """Installed distributions as sorted 'name==version' lines (like pip freeze)."""
    return sorted({f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions()}, key=str.lower)


def check_run(now_utc: datetime) -> datetime:
    """Yesterday's 00z run: always published and not yet expired (retention 2-3 days, PLAN.md facts)."""
    day = (now_utc - timedelta(days=1)).date()
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def main() -> None:
    """Command-line entry point."""
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    out = p.parse_args().out
    import eccodes  # here so the mirror/package helpers stay importable without the ecCodes library
    now = datetime.now(timezone.utc)
    run = check_run(now)
    report = {
        "checked_at_utc": now.isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "eccodes_python": eccodes.__version__,
        "eccodes_lib": eccodes.codes_get_api_version(),
        "packages": installed_packages(),
        "mirror_file": f"ifs-ens {run:%Y%m%d%H} step 24 .index",
        "mirrors": {s: mirror_check(file_url(s, run, "ifs-ens", 24, "index")) for s in config.SOURCE_URLS},
    }
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
