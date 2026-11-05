"""Checks every archived run must pass before upload (CLAUDE.md §7, DECISIONS.md D46)."""

import numpy as np
import xarray as xr

from common import config
from process.deaccumulate import block_rain_mm

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
    v = tp_mm.values
    if not np.isfinite(v).all():
        raise ValueError(f"{int((~np.isfinite(v)).sum())} non-finite tp values")
    if v.min() < 0.0:
        raise ValueError(f"negative accumulated tp: min {float(v.min())} mm")
    rain, n_clipped = block_rain_mm(tp_mm, packing_mm)  # checks steps and the D46 tolerance
    if float(rain.max()) > config.MAX_RAIN_6H_MM:
        raise ValueError(f"6-h rain {float(rain.max()):.0f} mm above {config.MAX_RAIN_6H_MM} mm ceiling")
    return n_clipped
