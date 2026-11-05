"""Checks every archived run must pass before upload (CLAUDE.md §7, DECISIONS.md D46)."""

import numpy as np
import xarray as xr

from common import config

DIMS = ("step_h", "member", "latitude", "longitude")


def check_accumulated_tp(tp_mm: xr.DataArray, packing_mm: list[float]) -> int:
    """Raise ValueError if accumulated tp (mm, from forecast start) is unusable; return count of tolerated dips.

    packing_mm[i] is the GRIB packing error (mm, max over members) of step i. A drop between consecutive steps is
    tolerated up to packing_mm[a] + packing_mm[b] (D46); a 6-h amount above MAX_RAIN_6H_MM is rejected.
    """
    if tp_mm.dims != DIMS or tp_mm.attrs.get("units") != "mm":
        raise ValueError(f"expected dims {DIMS} in mm, got {tp_mm.dims} in {tp_mm.attrs.get('units')}")
    members = [int(m) for m in tp_mm["member"].values]
    if members != list(range(1, config.EXPECTED_MEMBERS + 1)):
        raise ValueError(f"expected members 1..{config.EXPECTED_MEMBERS}, got {len(members)}")
    steps = [int(s) for s in tp_mm["step_h"].values]
    if len(packing_mm) != len(steps):
        raise ValueError(f"{len(packing_mm)} packing errors for {len(steps)} steps")
    if steps[0] != config.BLOCK_HOURS or any(b - a != config.BLOCK_HOURS for a, b in zip(steps, steps[1:])):
        raise ValueError(f"steps must be {config.BLOCK_HOURS}, {2 * config.BLOCK_HOURS}, ...; got {steps[:4]}...")
    v = tp_mm.values
    if not np.isfinite(v).all():
        raise ValueError(f"{int((~np.isfinite(v)).sum())} non-finite tp values")
    if v.min() < 0.0:
        raise ValueError(f"negative accumulated tp: min {float(v.min())} mm")
    block = np.diff(v, axis=0, prepend=0.0)  # 6-h amounts; the first block is step 6 minus 0
    tol = np.array([packing_mm[0]] + [a + b for a, b in zip(packing_mm, packing_mm[1:])])[:, None, None, None]
    if (block < -tol).any():
        i = int(np.argwhere(block < -tol)[0][0])
        raise ValueError(f"accumulation drops by {float(-block[i].min()):.3f} mm before step {steps[i]}, "
                         f"tolerance {float(tol[i, 0, 0, 0]):.3f} mm")
    if block.max() > config.MAX_RAIN_6H_MM:
        raise ValueError(f"6-h rain {float(block.max()):.0f} mm above {config.MAX_RAIN_6H_MM} mm ceiling")
    return int((block < 0).sum())
