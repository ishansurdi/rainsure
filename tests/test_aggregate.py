"""Tests for process.aggregate.day_totals_mm with hand-computed sums."""

import unittest
from datetime import datetime, timezone

import numpy as np
import xarray as xr

from common.time import blocks_for_run
from process.aggregate import day_totals_mm

UTC = timezone.utc


def _rain(run: datetime) -> xr.DataArray:
    """1 mm in every block for member 1, 0 for member 2; steps = the run's block end steps."""
    steps = [b.end_step_h for b in blocks_for_run(run)]
    v = np.zeros((len(steps), 2), dtype=np.float32)
    v[:, 0] = 1.0
    return xr.DataArray(v, dims=("step_h", "member"), coords={"step_h": steps, "member": [1, 2]}, attrs={"units": "mm"})


class TestDayTotals(unittest.TestCase):
    def test_00z_run_has_10_full_days(self) -> None:
        run = datetime(2026, 11, 5, 0, tzinfo=UTC)
        rain = _rain(run)
        rain[4:8, 1] = [0.5, 0.0, 2.0, 3.0]  # member 2, second day (06 Nov): 5.5 mm
        out = day_totals_mm(rain, run)
        self.assertEqual(out.dims, ("app_day", "member"))
        self.assertEqual(str(out["app_day"].values[0])[:10], "2026-11-05")
        self.assertEqual(out.sizes["app_day"], 10)
        np.testing.assert_allclose(out.sel(member=1).values, 4.0)
        np.testing.assert_allclose(out.sel(member=2).values[:3], [0.0, 5.5, 0.0])

    def test_12z_run_drops_partial_first_day(self) -> None:
        run = datetime(2026, 11, 5, 12, tzinfo=UTC)
        rain = _rain(run)
        rain[0:2, 0] = 100.0  # partial day 05 Nov (steps 6, 12) must not appear anywhere
        out = day_totals_mm(rain, run)
        self.assertEqual(str(out["app_day"].values[0])[:10], "2026-11-06")
        self.assertEqual(out.sizes["app_day"], 10)
        np.testing.assert_allclose(out.sel(member=1).values, 4.0)

    def test_mismatched_steps_rejected(self) -> None:
        run = datetime(2026, 11, 5, 0, tzinfo=UTC)
        with self.assertRaisesRegex(ValueError, "do not match"):
            day_totals_mm(_rain(run).isel(step_h=slice(0, 8)), run)


if __name__ == "__main__":
    unittest.main()
