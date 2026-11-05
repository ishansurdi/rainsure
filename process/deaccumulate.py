"""Accumulated tp -> 6-h block rain, with the packing-error tolerance of DECISIONS.md D46."""

import logging

import numpy as np
import xarray as xr

from common import config

log = logging.getLogger(__name__)


def block_rain_mm(tp_accum_mm: xr.DataArray, packing_mm: list[float]) -> tuple[xr.DataArray, int]:
    """6-h rain (mm) ending at each step, from tp accumulated since run start (mm); returns (rain, n_clipped).

    Steps must be 6, 12, ... (the first block is step 6 minus 0). A drop between steps a and b is GRIB packing noise
    if it is within packing_mm[a] + packing_mm[b]: it is clipped to 0 and counted. A larger drop raises ValueError.
    """
    if tp_accum_mm.attrs.get("units") != "mm":
        raise ValueError(f"expected mm, got {tp_accum_mm.attrs.get('units')}")
    steps = [int(s) for s in tp_accum_mm["step_h"].values]
    if len(packing_mm) != len(steps):
        raise ValueError(f"{len(packing_mm)} packing errors for {len(steps)} steps")
    if steps[0] != config.BLOCK_HOURS or any(b - a != config.BLOCK_HOURS for a, b in zip(steps, steps[1:])):
        raise ValueError(f"steps must be {config.BLOCK_HOURS}, {2 * config.BLOCK_HOURS}, ...; got {steps[:4]}...")
    axis = tp_accum_mm.get_axis_num("step_h")
    rain = np.diff(tp_accum_mm.values, axis=axis, prepend=0.0)
    tol_shape = [1] * rain.ndim
    tol_shape[axis] = len(steps)
    tol = np.array([packing_mm[0]] + [a + b for a, b in zip(packing_mm, packing_mm[1:])]).reshape(tol_shape)
    too_low = rain < -tol
    if too_low.any():
        i = int(np.argwhere(too_low)[0][axis])
        drop = float(-np.take(rain, i, axis=axis).min())
        raise ValueError(f"accumulation drops by {drop:.3f} mm before step {steps[i]}, "
                         f"tolerance {float(tol.flat[i]):.3f} mm")
    n_clipped = int((rain < 0).sum())
    rain = np.maximum(rain, 0.0)
    log.info("de-accumulated %d steps; clipped %d small negatives (packing noise, D46)", len(steps), n_clipped)
    return tp_accum_mm.copy(data=rain.astype(tp_accum_mm.dtype)).assign_attrs(units="mm"), n_clipped
