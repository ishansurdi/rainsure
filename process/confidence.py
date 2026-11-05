"""Confidence from three checks on P(rain >= event): decided, models agree, stable (DECISIONS.md D14, D15)."""

import numpy as np
import xarray as xr

from common import config


def confidence_checks(p_ifs_pct: xr.DataArray, p_aifs_pct: xr.DataArray, p_pooled_pct: xr.DataArray,
                      p_previous_pct: xr.DataArray | None) -> xr.Dataset:
    """Per cell: decided / agree / stable (bool), points (0-3, uint8). Inputs are percent, aligned on valid time.

    p_previous_pct is the previous run's pooled P for the same valid time; NaN or None means no earlier run, which
    counts as not stable (D15).
    """
    decided = (p_pooled_pct < config.DECIDED_BELOW_PCT) | (p_pooled_pct > config.DECIDED_ABOVE_PCT)
    agree = abs(p_ifs_pct - p_aifs_pct) < config.AGREE_MAX_DIFF_PCT
    if p_previous_pct is None:
        stable = xr.zeros_like(decided, dtype=bool)
    else:
        stable = abs(p_pooled_pct - p_previous_pct) < config.STABLE_MAX_DIFF_PCT  # NaN compares False
    points = (decided.astype(np.uint8) + agree.astype(np.uint8) + stable.astype(np.uint8)).astype(np.uint8)
    return xr.Dataset({"decided": decided, "agree": agree, "stable": stable, "points": points},
                      attrs={"has_previous_run": p_previous_pct is not None})


def confidence_level(points: int) -> str:
    """'high' (3 checks pass), 'medium' (2) or 'low' (0-1)."""
    return config.CONFIDENCE_BY_POINTS[int(points)]
