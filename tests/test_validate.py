"""Tests for ingest.validate.check_accumulated_tp with tiny hand-built arrays."""

import unittest

import numpy as np
import xarray as xr

from common import config
from ingest.validate import check_accumulated_tp

M = config.EXPECTED_MEMBERS


def _tp(per_step_mm: list[float], members: int = M) -> xr.DataArray:
    """Accumulated tp, same value at every member and the 1x2 grid, steps 6, 12, ..."""
    v = np.broadcast_to(np.array(per_step_mm, dtype=np.float32)[:, None, None, None], (len(per_step_mm), members, 1, 2))
    return xr.DataArray(v.copy(), dims=("step_h", "member", "latitude", "longitude"),
                        coords={"step_h": [6 * (i + 1) for i in range(len(per_step_mm))],
                                "member": list(range(1, members + 1)), "latitude": [20.0], "longitude": [77.0, 77.25]},
                        attrs={"units": "mm"})


class TestCheckAccumulatedTp(unittest.TestCase):
    def test_valid_run_passes(self) -> None:
        self.assertEqual(check_accumulated_tp(_tp([0.0, 1.0, 1.0, 5.0]), [0.1] * 4), 0)

    def test_dip_within_tolerance_counted(self) -> None:
        # 2.0 -> 1.9 is a drop of 0.1 mm; tolerance 0.06 + 0.06 = 0.12 mm -> tolerated, every member and cell counts
        self.assertEqual(check_accumulated_tp(_tp([2.0, 1.9]), [0.06, 0.06]), M * 2)

    def test_dip_beyond_tolerance_fails(self) -> None:
        # drop 0.2 mm > 0.06 + 0.06
        with self.assertRaisesRegex(ValueError, "drops by 0.200 mm before step 12"):
            check_accumulated_tp(_tp([2.0, 1.8]), [0.06, 0.06])

    def test_nan_fails(self) -> None:
        tp = _tp([1.0, 2.0])
        tp[1, 0, 0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "1 non-finite"):
            check_accumulated_tp(tp, [0.1, 0.1])

    def test_negative_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "negative"):
            check_accumulated_tp(_tp([-0.5, 1.0]), [0.1, 0.1])

    def test_missing_members_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "members"):
            check_accumulated_tp(_tp([1.0], members=49), [0.1])

    def test_gap_in_steps_fails(self) -> None:
        tp = _tp([1.0, 2.0]).assign_coords(step_h=[6, 18])
        with self.assertRaisesRegex(ValueError, "steps"):
            check_accumulated_tp(tp, [0.1, 0.1])

    def test_implausible_block_fails(self) -> None:
        # 1 mm then 1201 mm: the second 6-h block is 1200 mm > 1144 mm (e.g. mm read as m)
        with self.assertRaisesRegex(ValueError, "1200 mm above"):
            check_accumulated_tp(_tp([1.0, 1201.0]), [0.1, 0.1])

    def test_wrong_units_fail(self) -> None:
        tp = _tp([1.0])
        tp.attrs["units"] = "m"
        with self.assertRaisesRegex(ValueError, "in m"):
            check_accumulated_tp(tp, [0.1])


if __name__ == "__main__":
    unittest.main()
