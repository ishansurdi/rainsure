"""Tests for process.ensemble with hand-counted members."""

import unittest

import numpy as np
import xarray as xr

from process.ensemble import members_at_least


def _rain(values: list[list[float]]) -> xr.DataArray:
    """Per-member rain (mm), dims (member, longitude)."""
    v = np.array(values, dtype=np.float32)
    return xr.DataArray(v, dims=("member", "longitude"),
                        coords={"member": list(range(1, v.shape[0] + 1)), "longitude": [77.0, 77.25]},
                        attrs={"units": "mm"})


class TestMembersAtLeast(unittest.TestCase):
    def test_counts_inclusive_threshold(self) -> None:
        # cell 1: 2.5 counts (inclusive), 2.4 does not -> 2 of 4; cell 2: none -> 0
        rain = _rain([[2.5, 0.0], [2.4, 1.0], [10.0, 2.49], [0.0, 0.0]])
        c = members_at_least(rain, 2.5)
        np.testing.assert_array_equal(c.values, [2, 0])
        self.assertEqual(c.dtype, np.uint8)
        self.assertEqual((c.attrs["threshold_mm"], c.attrs["members"]), (2.5, 4))

    def test_rejects_non_mm(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected mm"):
            members_at_least(_rain([[1.0, 1.0]]).assign_attrs(units="m"), 2.5)


if __name__ == "__main__":
    unittest.main()
