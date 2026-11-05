"""Save every 00z/12z run's India tp (all members, all 6-h steps) before ECMWF deletes it (DECISIONS.md D20).

Usage:
  python -m ingest.archive_run --pending --existing names.txt   # print runs still to archive
  python -m ingest.archive_run --run 2026110500 --out data/archive
"""

import argparse
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from common import config
from common.grid import crop_to_box, normalise_longitude
from common.io import archive_stem, write_archive
from common.time import blocks_for_run, recent_runs, validate_run_time
from common.units import tp_to_mm
from ingest.decode import decode_tp_members
from ingest.fetch import DownloadError, fetch_tp_messages, file_url, http_get

log = logging.getLogger("archive")
EXIT_NOT_PUBLISHED = 3  # lets the workflow tell "try later" apart from a real failure


def archive_steps(run_time_utc: datetime) -> list[int]:
    """Forecast steps (h) needed for all 6-h blocks of a run: 6, 12, ... up to the last block end."""
    return [b.end_step_h for b in blocks_for_run(run_time_utc)]


def run_available(run_time_utc: datetime, model: str, source: str) -> bool:
    """True if the last needed step's index file exists, i.e. the run is fully published."""
    try:
        http_get(file_url(source, run_time_utc, model, archive_steps(run_time_utc)[-1], "index"))
        return True
    except DownloadError as e:
        if "HTTP 404" in str(e) or "HTTP 403" in str(e):
            return False
        raise


def _fetch_step(run_time_utc: datetime, model: str, step_h: int) -> tuple[list[tuple[int, bytes]], str]:
    """Fetch one step from the first source that works (Google mirror, then ECMWF)."""
    errors = []
    for source in config.SOURCE_ORDER:
        try:
            return fetch_tp_messages(run_time_utc, model, step_h, source), source
        except DownloadError as e:
            errors.append(f"{source}: {e}")
            log.warning("step %d from %s failed, trying next source: %s", step_h, source, e)
    raise DownloadError(f"{model} step {step_h}: all sources failed: {errors}")


def archive_model_run(run_time_utc: datetime, model: str, out_dir: Path) -> Path:
    """Download, check, crop and save one model run; returns the .npz path."""
    t0, n_bytes, sources, grib_units, fields, packing_mm = time.monotonic(), 0, set(), set(), [], []
    steps = archive_steps(run_time_utc)
    for step_h in steps:
        messages, source = _fetch_step(run_time_utc, model, step_h)
        n_bytes += sum(len(m) for _, m in messages)
        sources.add(source)
        tp = decode_tp_members(messages, step_h)  # single thread (D45)
        grib_units.add(tp.attrs["units"])
        packing_mm.append(tp.attrs["packing_error_max"] * config.TP_UNIT_TO_MM[tp.attrs["units"]])
        fields.append(crop_to_box(normalise_longitude(tp), config.INDIA_BOX))
    fetch_s = time.monotonic() - t0
    tp_all = xr.concat(fields, dim="step_h").assign_coords(step_h=steps).transpose("step_h", "member", "latitude", "longitude")
    tp_mm = tp_to_mm(tp_all)
    if not bool(np.isfinite(tp_mm.values).all()):
        raise ValueError(f"{model} {run_time_utc:%Y%m%d%H}: non-finite tp values")
    if float(tp_mm.min()) < 0.0:  # accumulated from start: never negative in the source (min was 0 when checked)
        raise ValueError(f"{model} {run_time_utc:%Y%m%d%H}: negative accumulated tp {float(tp_mm.min())} mm")
    meta = {"stem": archive_stem(model, run_time_utc), "model": model, "run_time_utc": run_time_utc.isoformat(),
            "steps_h": steps, "members": int(tp_mm.sizes["member"]), "grib_units": sorted(grib_units),
            "packing_error_mm_max": packing_mm,  # per step, max over members; de-accumulation tolerance (D10)
            "sources": sorted(sources), "box": config.INDIA_BOX._asdict(), "bytes_downloaded": n_bytes,
            "fetch_seconds": round(fetch_s, 1), "processed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    npz, _ = write_archive(tp_mm, meta, out_dir)
    log.info("%s: %d steps, %.0f MB in %.0f s (%.1f MB/s), sources %s, wrote %s (%.1f MB)", meta["stem"], len(steps),
             n_bytes / 1e6, fetch_s, n_bytes / 1e6 / max(fetch_s, 1e-9), sorted(sources), npz.name, npz.stat().st_size / 1e6)
    return npz


def pending_runs(now_utc: datetime, existing_names: set[str]) -> list[datetime]:
    """Recent runs where at least one model's archive file is missing (oldest first, so nothing expires)."""
    todo = [r for r in recent_runs(now_utc, config.ARCHIVE_LOOKBACK_H)
            if any(f"{archive_stem(m, r)}.npz" not in existing_names for m in config.MODELS)]
    return sorted(todo)


def main() -> None:
    """Command-line entry point."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--pending", action="store_true", help="print runs still to archive, one per line")
    p.add_argument("--existing", type=Path, help="file with existing archive asset names, one per line")
    p.add_argument("--run", help="run time YYYYMMDDHH (UTC)")
    p.add_argument("--out", type=Path, default=Path("data/archive"))
    a = p.parse_args()
    if a.pending:
        names = set(a.existing.read_text().split()) if a.existing else set()
        for r in pending_runs(datetime.now(timezone.utc), names):
            print(f"{r:%Y%m%d%H}")
        return
    run = datetime.strptime(a.run, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    validate_run_time(run)
    for model in config.MODELS:
        if not run_available(run, model, config.SOURCE_ORDER[0]) and not run_available(run, model, config.SOURCE_ORDER[-1]):
            log.warning("%s %s: not (fully) published yet or already expired", model, a.run)
            raise SystemExit(EXIT_NOT_PUBLISHED)
    for model in config.MODELS:
        archive_model_run(run, model, a.out)


if __name__ == "__main__":
    main()
