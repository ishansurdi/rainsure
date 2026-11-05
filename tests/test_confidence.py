"""Tests for process.confidence and the percent/pooling helpers, with hand-worked cases."""

import unittest

import numpy as np
import xarray as xr

from process.confidence import confidence_checks, confidence_level
from process.ensemble import percent, pooled


def _p(values: list[float]) -> xr.DataArray:
    return xr.DataArray(np.array(values, dtype=np.float32), dims=("cell",))


def _count(values: list[int], members: int = 50) -> xr.DataArray:
    return xr.DataArray(np.array(values, dtype=np.uint8), dims=("cell",),
                        attrs={"members": members, "threshold_mm": 2.5, "units": "members"})


class TestPercentPooled(unittest.TestCase):
    def test_percent_and_equal_weight_pooling(self) -> None:
        ifs, aifs = _count([34, 0]), _count([6, 50])
        np.testing.assert_allclose(percent(ifs).values, [68.0, 0.0])
        both = pooled(ifs, aifs)
        self.assertEqual(both.attrs["members"], 100)
        np.testing.assert_allclose(percent(both).values, [40.0, 50.0])  # 40 of 100, 50 of 100


class TestConfidence(unittest.TestCase):
    def test_each_check(self) -> None:
        # cell 0: pooled 90 (decided), ifs 92 vs aifs 88 (agree), prev 85 (stable)       -> 3 high
        # cell 1: pooled 50 (not decided), ifs 60 vs aifs 40 (diff 20, not < 20), prev 45 -> 1 low
        # cell 2: pooled 10 (decided), ifs 15 vs aifs 5 (agree), prev 40 (diff 30)        -> 2 medium
        # cell 3: pooled 20 (not < 20), ifs 20 vs aifs 20 (agree), prev NaN (no run)      -> 1 low
        c = confidence_checks(_p([92, 60, 15, 20]), _p([88, 40, 5, 20]), _p([90, 50, 10, 20]),
                              _p([85, 45, 40, np.nan]))
        self.assertEqual(c["decided"].values.tolist(), [True, False, True, False])
        self.assertEqual(c["agree"].values.tolist(), [True, False, True, True])
        self.assertEqual(c["stable"].values.tolist(), [True, True, False, False])
        self.assertEqual(c["points"].values.tolist(), [3, 1, 2, 1])
        self.assertEqual([confidence_level(p) for p in c["points"].values], ["high", "low", "medium", "low"])

    def test_no_previous_run_is_not_stable(self) -> None:
        c = confidence_checks(_p([95]), _p([95]), _p([95]), None)
        self.assertEqual((bool(c["stable"][0]), int(c["points"][0])), (False, 2))
        self.assertFalse(c.attrs["has_previous_run"])


if __name__ == "__main__":
    unittest.main()
