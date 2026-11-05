"""Longitude normalisation and box cropping on lat/lon grids (CLAUDE.md §4, DECISIONS.md D12)."""

import xarray as xr

from common.config import Box


def normalise_longitude(da: xr.DataArray) -> xr.DataArray:
    """Map the `longitude` coordinate (degrees) to [-180, 180) and sort it ascending."""
    lon = ((da["longitude"] + 180.0) % 360.0) - 180.0
    return da.assign_coords(longitude=lon).sortby("longitude")


def crop_to_box(da: xr.DataArray, box: Box) -> xr.DataArray:
    """Keep points inside the box (degrees, edges inclusive); longitudes must already be in [-180, 180)."""
    lon, lat = da["longitude"], da["latitude"]
    if bool((lon >= 180.0).any()) or bool((lon < -180.0).any()):
        raise ValueError("longitudes not normalised to [-180, 180); call normalise_longitude first")
    keep_lon = ((lon >= box.west) & (lon <= box.east)).values
    keep_lat = ((lat >= box.south) & (lat <= box.north)).values
    if not keep_lon.any() or not keep_lat.any():
        raise ValueError(f"box {box} does not overlap the grid")
    return da.isel(longitude=keep_lon, latitude=keep_lat)
