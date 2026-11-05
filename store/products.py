"""All numbers published for one run, on the full India grid (DECISIONS.md D2, D14-D16, D29, D44, D49)."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import xarray as xr

from common import config
from common.io import read_archive
from process.aggregate import day_totals_mm
from process.confidence import confidence_checks
from process.deaccumulate import block_rain_mm
from process.ensemble import members_at_least, percent, pooled

IFS, AIFS = "ifs-ens", "aifs-ens"
PERCENTILES = (10, 25, 50, 75, 90)


@dataclass(frozen=True)
class RunRain:
    """6-h block rain (mm; step_h, member, latitude, longitude) of both models for one run."""

    run_time_utc: datetime
    rain: dict[str, xr.DataArray]


def load_run(npz_by_model: dict[str, Path]) -> RunRain:
    """Read both models' archive files and de-accumulate them (clip counts are logged by block_rain_mm)."""
    if set(npz_by_model) != {IFS, AIFS}:
        raise ValueError(f"need archive files for {IFS} and {AIFS}, got {sorted(npz_by_model)}")
    rain, runs = {}, set()
    for model, path in npz_by_model.items():
        acc = read_archive(path)
        rain[model], _ = block_rain_mm(acc, acc.attrs["packing_error_mm_max"])
        runs.add(acc.attrs["run_time_utc"])
    if len(runs) != 1:
        raise ValueError(f"model files are from different runs: {sorted(runs)}")
    for d in ("step_h", "latitude", "longitude"):
        if not np.array_equal(rain[IFS][d].values, rain[AIFS][d].values):
            raise ValueError(f"models differ in {d}")
    return RunRain(datetime.fromisoformat(runs.pop()), rain)


def align_steps(prev: xr.DataArray, prev_run: datetime, cur_run: datetime, cur_steps: list[int]) -> xr.DataArray:
    """Previous run's values at the current run's steps, matched by valid time; NaN where it has none."""
    shift_h = int((cur_run - prev_run).total_seconds() // 3600)
    if shift_h <= 0:
        raise ValueError(f"previous run {prev_run} is not before {cur_run}")
    moved = prev.astype(np.float32).assign_coords(step_h=prev["step_h"].values - shift_h)
    return moved.reindex(step_h=cur_steps)


def pooled_rain(run: RunRain) -> xr.DataArray:
    """Both models' members on one 'member' axis 1..100 (IFS first, then AIFS)."""
    m = config.EXPECTED_MEMBERS
    a = run.rain[IFS].assign_coords(member=np.arange(1, m + 1))
    b = run.rain[AIFS].assign_coords(member=np.arange(m + 1, 2 * m + 1))
    return xr.concat([a, b], dim="member").assign_attrs(units="mm")


def block_products(cur: RunRain, prev: RunRain | None) -> xr.Dataset:
    """Per 6-h block: event counts per model and pooled, previous pooled count, checks, wet flag of each forecast."""
    n_ifs = members_at_least(cur.rain[IFS], config.EVENT_MM)
    n_aifs = members_at_least(cur.rain[AIFS], config.EVENT_MM)
    n_pool = pooled(n_ifs, n_aifs)
    steps = [int(s) for s in n_pool["step_h"].values]
    if prev is None:
        n_prev = xr.full_like(n_pool, np.nan, dtype=np.float32)
    else:
        p = pooled(members_at_least(prev.rain[IFS], config.EVENT_MM), members_at_least(prev.rain[AIFS], config.EVENT_MM))
        n_prev = align_steps(p, prev.run_time_utc, cur.run_time_utc, steps)
    checks = confidence_checks(percent(n_ifs), percent(n_aifs), percent(n_pool),
                               100.0 * n_prev / n_pool.attrs["members"])
    wet = pooled_rain(cur) >= config.EVENT_MM
    return xr.Dataset({"n_ifs": n_ifs, "n_aifs": n_aifs, "n_pooled": n_pool, "n_prev": n_prev,
                       "decided": checks["decided"], "agree": checks["agree"], "stable": checks["stable"],
                       "wet": wet})


def day_products(cur: RunRain, prev: RunRain | None) -> xr.Dataset:
    """Per full app day: counts per IMD threshold per model, pooled percentiles, model medians, checks."""
    days = {m: day_totals_mm(cur.rain[m], cur.run_time_utc) for m in (IFS, AIFS)}
    out = {}
    for t in config.DAY_THRESHOLDS_MM:
        out[f"n_ifs_{t:g}"] = members_at_least(days[IFS], t)
        out[f"n_aifs_{t:g}"] = members_at_least(days[AIFS], t)
    ev = f"{config.EVENT_MM:g}"
    n_pool = pooled(out[f"n_ifs_{ev}"], out[f"n_aifs_{ev}"])
    both = xr.concat([days[IFS], days[AIFS]], dim="member")
    q = np.percentile(both.values, PERCENTILES, axis=both.get_axis_num("member")).astype(np.float32)
    out["pct_mm"] = xr.DataArray(q, dims=("pct",) + tuple(d for d in both.dims if d != "member"),
                                 coords={"pct": list(PERCENTILES), **{d: both[d] for d in both.dims if d != "member"}})
    out["median_ifs_mm"] = days[IFS].median("member")
    out["median_aifs_mm"] = days[AIFS].median("member")
    out["n_zero"] = (both < 0.05).sum("member").astype(np.uint8)  # shown as 0.0 mm
    out["n_pooled"] = n_pool
    if prev is None:
        n_prev = xr.full_like(n_pool, np.nan, dtype=np.float32)
    else:
        pdays = {m: day_totals_mm(prev.rain[m], prev.run_time_utc) for m in (IFS, AIFS)}
        p = pooled(members_at_least(pdays[IFS], config.EVENT_MM), members_at_least(pdays[AIFS], config.EVENT_MM))
        n_prev = p.astype(np.float32).reindex(app_day=n_pool["app_day"].values)
    out["n_prev"] = n_prev
    checks = confidence_checks(percent(out[f"n_ifs_{ev}"]), percent(out[f"n_aifs_{ev}"]), percent(n_pool),
                               100.0 * n_prev / n_pool.attrs["members"])
    out.update({k: checks[k] for k in ("decided", "agree", "stable")})
    return xr.Dataset(out)


def window_day_counts(rain_100: xr.DataArray, start: int, n_blocks: int, app_days: list) -> dict:
    """For blocks start..start+n_blocks-1: per app day, forecasts (of 100) with >= EVENT_MM over that day's blocks.

    rain_100 is pooled block rain from pooled_rain(); returns {app_day: counts grid (latitude, longitude)} (D51).
    """
    out = {}
    idx = list(range(start, start + n_blocks))
    for day in sorted(set(app_days[i] for i in idx)):
        sel = [i for i in idx if app_days[i] == day]
        out[day] = (rain_100.isel(step_h=sel).sum("step_h") >= config.EVENT_MM).sum("member").astype(np.uint8)
    return out
