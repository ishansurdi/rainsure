"""Decode tp GRIB messages into a labelled array, checking every message (DECISIONS.md D9, D45)."""

import math

import eccodes
import numpy as np
import xarray as xr

from common import config
from common.config import GridSpec

_KEYS = ("shortName", "units", "stepType", "stepRange", "number", "Ni", "Nj", "iScansNegatively",
         "jScansPositively", "latitudeOfFirstGridPointInDegrees", "longitudeOfFirstGridPointInDegrees",
         "iDirectionIncrementInDegrees", "bitmapPresent", "packingError")


def grid_coords(grid: GridSpec) -> tuple[np.ndarray, np.ndarray]:
    """Latitudes (north->south) and longitudes (0..360, from lon_first) of a GRIB grid, in degrees."""
    lats = grid.lat_first - grid.step_deg * np.arange(grid.nj)
    lons = (grid.lon_first + grid.step_deg * np.arange(grid.ni)) % 360.0
    return lats, lons


def _check(meta: dict, number: int, step_h: int, grid: GridSpec) -> None:
    """Raise if a message is not the accumulated tp field on the verified grid."""
    expected = {"shortName": "tp", "stepType": "accum", "stepRange": f"0-{step_h}", "number": number,
                "Ni": grid.ni, "Nj": grid.nj, "iScansNegatively": 0, "jScansPositively": 0, "bitmapPresent": 0}
    bad = {k: meta[k] for k, v in expected.items() if meta[k] != v}
    for key, want in (("latitudeOfFirstGridPointInDegrees", grid.lat_first),
                      ("longitudeOfFirstGridPointInDegrees", grid.lon_first),
                      ("iDirectionIncrementInDegrees", grid.step_deg)):
        if not math.isclose(meta[key], want, abs_tol=1e-6):
            bad[key] = meta[key]
    if bad:
        raise ValueError(f"member {number} step {step_h}: unexpected GRIB keys {bad}")


def decode_tp_members(messages: list[tuple[int, bytes]], step_h: int,
                      grid: GridSpec = config.SOURCE_GRID) -> xr.DataArray:
    """Decode (member, GRIB bytes) pairs into tp (member, latitude, longitude) with its GRIB units; one thread only.

    attrs['packing_error_max'] is the largest GRIB packing error over members, in the GRIB units (DECISIONS.md D10).
    """
    fields, units, packing_errors = [], set(), []
    for number, msg in messages:
        h = eccodes.codes_new_from_message(msg)
        try:
            meta = {k: eccodes.codes_get(h, k) for k in _KEYS}
            _check(meta, number, step_h, grid)
            fields.append(eccodes.codes_get_values(h).reshape(grid.nj, grid.ni).astype(np.float32))
            units.add(meta["units"])
            packing_errors.append(float(meta["packingError"]))
        finally:
            eccodes.codes_release(h)
    if len(units) != 1:
        raise ValueError(f"step {step_h}: mixed or missing tp units {units}")
    lats, lons = grid_coords(grid)
    return xr.DataArray(np.stack(fields), dims=("member", "latitude", "longitude"), name="tp",
                        coords={"member": [n for n, _ in messages], "latitude": lats, "longitude": lons},
                        attrs={"units": units.pop(), "packing_error_max": max(packing_errors)})
