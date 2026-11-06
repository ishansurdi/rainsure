"""Build the published data for the newest complete archived run (DECISIONS.md D20, D52).

Usage:
  python -m store.publish --pick --existing names.txt          # print "<run> <previous run or ->"
  python -m store.publish --archive-dir dl --run 2026110412 [--prev 2026110400] --site site
Writes site/data/latest.json and site/data/<run>/{meta.json, layers/*.gz, points/t<ti>_<tj>.json}.
"""

import argparse
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import config
from common.io import archive_stem
from common.time import block_label, blocks_for_run, day_label
from store import points
from store.layers import layer_arrays, write_layers
from store.products import (AIFS, IFS, block_disagreement, block_products, day_products, load_run, pooled_rain,
                            window_day_counts)

log = logging.getLogger("publish")
_NAME = re.compile(r"^tp_(ifs-ens|aifs-ens)_(\d{10})\.npz$")


def pick_runs(asset_names: set[str]) -> tuple[str, str | None]:
    """Newest run with both models archived, and the newest complete run before it (or None)."""
    found: dict[str, set[str]] = {}
    for n in asset_names:
        m = _NAME.match(n)
        if m:
            found.setdefault(m.group(2), set()).add(m.group(1))
    complete = sorted(r for r, models in found.items() if models == {IFS, AIFS})
    if not complete:
        raise ValueError("no run with both models in the archive")
    return complete[-1], (complete[-2] if len(complete) > 1 else None)


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def publish(archive_dir: Path, run_id: str, prev_id: str | None, site: Path) -> dict[str, Any]:
    """Build every product of run_id (stability against prev_id) into site/data; return the run metadata."""
    t0 = time.monotonic()
    run_time = datetime.strptime(run_id, "%Y%m%d%H").replace(tzinfo=timezone.utc)

    def paths(rid: str, rt: datetime) -> dict[str, Path]:
        return {m: archive_dir / f"{archive_stem(m, rt)}.npz" for m in (IFS, AIFS)}

    cur = load_run(paths(run_id, run_time))
    prev = None
    if prev_id:
        prev_time = datetime.strptime(prev_id, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        prev = load_run(paths(prev_id, prev_time))
    blocks = blocks_for_run(run_time)
    bp, dp = block_products(cur, prev), day_products(cur, prev)
    rain_100 = pooled_rain(cur)
    app_days = [b.app_day for b in blocks]
    summary_counts = [window_day_counts(rain_100, s, config.NEXT_HOURS_BLOCKS, app_days)
                      for s in range(config.SUMMARY_START_BLOCKS)]
    out = site / "data" / run_id
    layers = write_layers(layer_arrays(bp, dp), out / "layers")
    (out / "points").mkdir(parents=True, exist_ok=True)
    n_tiles = 0
    dis = block_disagreement(bp, dp, blocks)
    for (ti, tj), tile in points.build_tiles(run_id, blocks, bp, dp, summary_counts, dis):
        (out / "points" / f"t{ti}_{tj}.json").write_text(json.dumps(tile, ensure_ascii=False, separators=(",", ":")),
                                                        encoding="utf-8")
        n_tiles += 1
    lat, lon = cur.rain[IFS]["latitude"].values, cur.rain[IFS]["longitude"].values
    meta = {
        "run_id": run_id, "run_time_utc": run_time.isoformat(), "previous_run_id": prev_id,
        "processed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {m: {k: cur.rain[m].attrs.get(k) for k in ("sources", "grib_units", "processed_at_utc")}
                   for m in (IFS, AIFS)},
        "members_per_model": config.EXPECTED_MEMBERS, "event_mm": config.EVENT_MM,
        "day_thresholds_mm": list(config.DAY_THRESHOLDS_MM),
        "grid": {"lat_first": float(lat[0]), "lon_first": float(lon[0]), "step_deg": 0.25, "n_lat": len(lat),
                 "n_lon": len(lon), "order": "rows north to south, columns west to east"},
        "tile_cells": config.TILE_CELLS, "point_tile": "points/t{ti}_{tj}.json (ti = row // tile_cells, "
                                                       "tj = column // tile_cells)",
        "summary_start_blocks": config.SUMMARY_START_BLOCKS,
        "stale_after_h": config.STALE_AFTER_H,  # frontend reads thresholds from here, never re-declares them
        "blocks": [{"start_utc": b.start_utc.isoformat(), "end_utc": b.end_utc.isoformat(),
                    "app_day": b.app_day.isoformat(), "label": block_label(b)} for b in blocks],
        "days": [{"app_day": str(d)[:10], "label": day_label(datetime.fromisoformat(str(d)[:10]).date())}
                 for d in dp["app_day"].values],
        "layers": layers, "point_schema": points.__doc__,
        "sizes_bytes": {"points": _dir_size(out / "points"), "layers": _dir_size(out / "layers"), "tiles": n_tiles},
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    (site / "data" / "latest.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    log.info("published %s (previous %s): %d tiles, points %.1f MB, layers %.2f MB, %.0f s", run_id, prev_id,
             n_tiles, meta["sizes_bytes"]["points"] / 1e6, meta["sizes_bytes"]["layers"] / 1e6, time.monotonic() - t0)
    return meta


def main() -> None:
    """Command-line entry point."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--pick", action="store_true")
    p.add_argument("--existing", type=Path)
    p.add_argument("--archive-dir", type=Path)
    p.add_argument("--run")
    p.add_argument("--prev")
    p.add_argument("--site", type=Path, default=Path("site"))
    a = p.parse_args()
    if a.pick:
        cur, prev = pick_runs(set(a.existing.read_text().split()))
        print(cur, prev or "-")
        return
    publish(a.archive_dir, a.run, None if a.prev in (None, "-") else a.prev, a.site)


if __name__ == "__main__":
    main()
