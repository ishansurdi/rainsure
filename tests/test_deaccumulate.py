"""Tests for process.deaccumulate with hand-computed values."""

import unittest

import numpy as np
import xarray as xr

from process.deaccumulate import block_rain_mm


def _acc(values: list[list[float]]) -> xr.DataArray:
    """Accumulated tp (mm), dims (step_h, member); steps 6, 12, ..."""
    return xr.DataArray(np.array(values, dtype=np.float32), dims=("step_h", "member"),
                        coords={"step_h": [6 * (i + 1) for i in range(len(values))], "member": [1, 2]},
                        attrs={"units": "mm"})


class TestBlockRain(unittest.TestCase):
    def test_differences_and_first_block_from_zero(self) -> None:
        rain, n = block_rain_mm(_acc([[1.0, 0.0], [3.5, 2.0], [3.5, 10.0]]), [0.1, 0.1, 0.1])
        np.testing.assert_allclose(rain.values, [[1.0, 0.0], [2.5, 2.0], [0.0, 8.0]])
        self.assertEqual(n, 0)
        self.assertEqual(rain.attrs["units"], "mm")
        self.assertEqual(list(rain["step_h"].values), [6, 12, 18])

    def test_small_drop_clipped_and_counted(self) -> None:
        # member 1: 2.0 -> 1.9 (drop 0.1 <= 0.06 + 0.06) -> 0; member 2 unaffected
        rain, n = block_rain_mm(_acc([[2.0, 1.0], [1.9, 1.5]]), [0.06, 0.06])
        np.testing.assert_allclose(rain.values, [[2.0, 1.0], [0.0, 0.5]], atol=1e-6)
        self.assertEqual(n, 1)

    def test_tolerance_uses_both_steps(self) -> None:
        # drop 0.3: fails with 0.1 + 0.1, passes with 0.1 + 0.25
        with self.assertRaisesRegex(ValueError, "drops by 0.300 mm before step 12, tolerance 0.200"):
            block_rain_mm(_acc([[2.0, 0.0], [1.7, 0.0]]), [0.1, 0.1])
        _, n = block_rain_mm(_acc([[2.0, 0.0], [1.7, 0.0]]), [0.1, 0.25])
        self.assertEqual(n, 1)

    def test_rejects_wrong_units_and_steps(self) -> None:
        bad_units = _acc([[1.0, 1.0]]).assign_attrs(units="m")
        with self.assertRaisesRegex(ValueError, "expected mm"):
            block_rain_mm(bad_units, [0.1])
        with self.assertRaisesRegex(ValueError, "steps"):
            block_rain_mm(_acc([[1.0, 1.0], [2.0, 2.0]]).assign_coords(step_h=[6, 18]), [0.1, 0.1])


if __name__ == "__main__":
    unittest.main()
