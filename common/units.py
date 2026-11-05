"""Precipitation unit conversion (CLAUDE.md §4, DECISIONS.md D9)."""

import xarray as xr

from common import config


def tp_to_mm(tp: xr.DataArray) -> xr.DataArray:
    """Convert total precipitation to mm using its `units` attribute (GRIB `units` key: 'm' or 'kg m**-2')."""
    units = tp.attrs.get("units")
    if units not in config.TP_UNIT_TO_MM:
        raise ValueError(f"unknown tp units {units!r}; expected one of {sorted(config.TP_UNIT_TO_MM)}")
    rain_mm = tp * config.TP_UNIT_TO_MM[units]
    rain_mm.attrs = {**tp.attrs, "units": "mm"}  # xarray arithmetic drops attrs; set them explicitly
    return rain_mm
