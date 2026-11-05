"""Tests for common.units and common.grid with tiny hand-computed arrays."""

import unittest

import numpy as np
import xarray as xr

from common import config
from common.config import Box
from common.grid import crop_to_box, normalise_longitude
from common.units import tp_to_mm


def _field(values: list[float], units: str | None) -> xr.DataArray:
    """1-D tp field over a 'member' axis with an optional units attribute."""
    attrs = {} if units is None else {"units": units}
    return xr.DataArray(np.array(values), dims="member", coords={"member": range(1, len(values) + 1)}, attrs=attrs)


class TestTpToMm(unittest.TestCase):
    def test_ifs_metres(self) -> None:
        out = tp_to_mm(_field([0.0025, 0.0, 0.1], "m"))
        np.testing.assert_allclose(out.values, [2.5, 0.0, 100.0])
        self.assertEqual(out.attrs["units"], "mm")
        self.assertEqual(list(out["member"].values), [1, 2, 3])

    def test_aifs_kg_per_m2_is_mm(self) -> None:
        out = tp_to_mm(_field([2.5, 187.25], "kg m**-2"))
        np.testing.assert_allclose(out.values, [2.5, 187.25])
        self.assertEqual(out.attrs["units"], "mm")

    def test_missing_units_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tp_to_mm(_field([1.0], None))

    def test_unknown_units_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tp_to_mm(_field([1.0], "mm"))


def _grid(lats: list[float], lons: list[float]) -> xr.DataArray:
    """lat x lon field with values 0..n-1 in row-major order."""
    data = np.arange(len(lats) * len(lons), dtype=float).reshape(len(lats), len(lons))
    return xr.DataArray(data, dims=("latitude", "longitude"), coords={"latitude": lats, "longitude": lons})


class TestNormaliseLongitude(unittest.TestCase):
    def test_grid_starting_at_180_like_grib(self) -> None:
        da = xr.DataArray([1.0, 2.0, 3.0, 4.0], dims="longitude", coords={"longitude": [180.0, 270.0, 0.0, 90.0]})
        out = normalise_longitude(da)
        self.assertEqual(list(out["longitude"].values), [-180.0, -90.0, 0.0, 90.0])
        self.assertEqual(list(out.values), [1.0, 2.0, 3.0, 4.0])

    def test_0_to_360_grid_is_reordered(self) -> None:
        da = xr.DataArray([10.0, 20.0, 30.0, 40.0], dims="longitude", coords={"longitude": [0.0, 90.0, 180.0, 270.0]})
        out = normalise_longitude(da)
        self.assertEqual(list(out["longitude"].values), [-180.0, -90.0, 0.0, 90.0])
        self.assertEqual(list(out.values), [30.0, 40.0, 10.0, 20.0])


class TestCropToBox(unittest.TestCase):
    def test_descending_latitudes(self) -> None:
        da = _grid([3.0, 2.0, 1.0, 0.0], [-1.0, 0.0, 1.0, 2.0])  # values 0..15
        out = crop_to_box(da, Box(west=0.0, east=1.0, south=1.0, north=2.0))
        self.assertEqual(list(out["latitude"].values), [2.0, 1.0])
        self.assertEqual(list(out["longitude"].values), [0.0, 1.0])
        np.testing.assert_array_equal(out.values, [[5.0, 6.0], [9.0, 10.0]])

    def test_unnormalised_longitude_rejected(self) -> None:
        with self.assertRaises(ValueError):
            crop_to_box(_grid([0.0], [90.0, 270.0]), Box(0.0, 100.0, -1.0, 1.0))

    def test_box_outside_grid_rejected(self) -> None:
        with self.assertRaises(ValueError):
            crop_to_box(_grid([0.0, 1.0], [0.0, 1.0]), Box(50.0, 60.0, 10.0, 20.0))

    def test_india_box_on_grib_shaped_grid_is_119_by_124(self) -> None:
        # Same layout as the verified GRIB header: 721 x 1440, first point lat 90, lon 180, 0.25 deg.
        lats = [90.0 - 0.25 * j for j in range(721)]
        lons = [(180.0 + 0.25 * i) % 360.0 for i in range(1440)]
        da = xr.DataArray(np.zeros((721, 1440), dtype=np.float32), dims=("latitude", "longitude"),
                          coords={"latitude": lats, "longitude": lons})
        out = crop_to_box(normalise_longitude(da), config.INDIA_BOX)
        self.assertEqual(out.shape, (124, 119))
        self.assertEqual((float(out["longitude"][0]), float(out["longitude"][-1])), (68.0, 97.5))
        self.assertEqual((float(out["latitude"][0]), float(out["latitude"][-1])), (37.25, 6.5))


if __name__ == "__main__":
    unittest.main()
