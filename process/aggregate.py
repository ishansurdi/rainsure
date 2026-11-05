"""Sum 6-h block rain into app-day totals per member (DECISIONS.md D1, D2, D3)."""

from datetime import datetime

import numpy as np
import xarray as xr

from common import config
from common.time import blocks_for_run

BLOCKS_PER_DAY = 24 // config.BLOCK_HOURS


def day_totals_mm(rain_6h_mm: xr.DataArray, run_time_utc: datetime) -> xr.DataArray:
    """Rain (mm) per full app day (05:30-05:30 IST) per member; a run's partial first day (12z) is left out.

    rain_6h_mm has dim step_h = block end steps of the run (6, 12, ...), as made by process.deaccumulate.
    """
    if rain_6h_mm.attrs.get("units") != "mm":
        raise ValueError(f"expected mm, got {rain_6h_mm.attrs.get('units')}")
    blocks = blocks_for_run(run_time_utc)
    steps = [int(s) for s in rain_6h_mm["step_h"].values]
    if steps != [b.end_step_h for b in blocks]:
        raise ValueError(f"steps {steps[:3]}...{steps[-1:]} do not match the run's blocks "
                         f"{blocks[0].end_step_h}...{blocks[-1].end_step_h}")
    days = sorted({b.app_day for b in blocks})
    full = [d for d in days if sum(b.app_day == d for b in blocks) == BLOCKS_PER_DAY]
    totals = [rain_6h_mm.isel(step_h=[i for i, b in enumerate(blocks) if b.app_day == d]).sum("step_h") for d in full]
    out = xr.concat(totals, dim="app_day").assign_coords(app_day=[np.datetime64(d, "D") for d in full])
    return out.assign_attrs(rain_6h_mm.attrs, units="mm")
