"""Ensemble member counts ("N of 50 futures"), always from per-member totals (DECISIONS.md D2, D44)."""

import numpy as np
import xarray as xr


def members_at_least(rain_mm: xr.DataArray, threshold_mm: float) -> xr.DataArray:
    """Number of members (uint8) with rain >= threshold_mm; rain_mm is per-member block or day totals in mm."""
    if rain_mm.attrs.get("units") != "mm":
        raise ValueError(f"expected mm, got {rain_mm.attrs.get('units')}")
    n_members = rain_mm.sizes["member"]
    if n_members > np.iinfo(np.uint8).max - 1:  # top value is reserved for "missing" (D44)
        raise ValueError(f"{n_members} members do not fit the uint8 count")
    count = (rain_mm >= threshold_mm).sum("member").astype(np.uint8)
    return count.assign_attrs(units="members", threshold_mm=threshold_mm, members=n_members)
