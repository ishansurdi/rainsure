"""Tests for store products, point tiles and layers on a tiny synthetic run (2026-11-05 00z = Thursday)."""

import unittest
from datetime import datetime, timezone

import numpy as np
import xarray as xr

from common import config
from common.time import blocks_for_run
from store.layers import layer_arrays
from store.points import build_tiles, dots_hex
from store.products import (AIFS, IFS, RunRain, align_steps, block_products, day_products, pooled_rain,
                            window_day_counts)
from store.publish import pick_runs

UTC = timezone.utc
RUN = datetime(2026, 11, 5, 0, tzinfo=UTC)
BLOCKS = blocks_for_run(RUN)


def _rain() -> dict[str, xr.DataArray]:
    """Zero rain on a 2 x 2 grid; IFS members 1-30 get 3 mm in block 1 (Thu afternoon) at cell (0, 0)."""
    steps = [b.end_step_h for b in BLOCKS]
    out = {}
    for m in (IFS, AIFS):
        v = np.zeros((len(steps), 50, 2, 2), dtype=np.float32)
        if m == IFS:
            v[1, :30, 0, 0] = 3.0
        out[m] = xr.DataArray(v, dims=("step_h", "member", "latitude", "longitude"),
                              coords={"step_h": steps, "member": np.arange(1, 51), "latitude": [13.0, 12.75],
                                      "longitude": [80.0, 80.25]}, attrs={"units": "mm"})
    return out


class TestAlignAndPick(unittest.TestCase):
    def test_previous_run_matched_by_valid_time(self) -> None:
        prev = xr.DataArray(np.arange(4, dtype=np.uint8), dims=("step_h",), coords={"step_h": [6, 12, 18, 24]})
        out = align_steps(prev, datetime(2026, 11, 4, 12, tzinfo=UTC), RUN, [6, 12, 18])
        # current step 6 = previous step 18 (value 2), step 12 = previous 24 (3), step 18 has no previous
        np.testing.assert_array_equal(out.values[:2], [2, 3])
        self.assertTrue(np.isnan(out.values[2]))

    def test_pick_runs_needs_both_models(self) -> None:
        names = {"tp_ifs-ens_2026110400.npz", "tp_aifs-ens_2026110400.npz", "tp_ifs-ens_2026110412.npz",
                 "tp_aifs-ens_2026110412.npz", "tp_ifs-ens_2026110500.npz", "runner_checks.json"}
        self.assertEqual(pick_runs(names), ("2026110412", "2026110400"))


class TestProductsAndTile(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cur = RunRain(RUN, _rain())
        cls.bp, cls.dp = block_products(cur, None), day_products(cur, None)
        counts = [window_day_counts(pooled_rain(cur), s, config.NEXT_HOURS_BLOCKS, [b.app_day for b in BLOCKS])
                  for s in range(config.SUMMARY_START_BLOCKS)]
        cls.tiles = dict(build_tiles("2026110500", BLOCKS, cls.bp, cls.dp, counts))

    def test_block_counts(self) -> None:
        self.assertEqual([int(self.bp[k][1, 0, 0]) for k in ("n_ifs", "n_aifs", "n_pooled")], [30, 0, 30])
        self.assertFalse(bool(self.bp["agree"][1, 0, 0]))  # 60 % vs 0 %

    def test_dots(self) -> None:
        wet = np.zeros(100, dtype=bool)
        wet[:30] = True  # IFS members 1-30
        self.assertEqual(str(dots_hex(wet)), "fffffffc" + "00" * 9)

    def test_tile_numbers_and_sentences(self) -> None:
        tile = self.tiles[(0, 0)]
        self.assertEqual(sorted(tile["cells"]), ["0_0", "0_1", "1_0", "1_1"])
        cell, s = tile["cells"]["0_0"], tile["strings"]
        # pooled 100: 70 zeros + 30 threes -> p10 0.0, p90 3.0 (index 89.1); IFS median 3.0, AIFS median 0.0
        self.assertEqual(cell["b"][1], [30, 0, -1, "fffffffc" + "00" * 9, 0.0, 3.0, 3.0, 0.0])
        self.assertEqual(s[cell["bt"][1][0]],
                         "Models disagree on rain Thu afternoon · 11:30–17:30 IST: physics 30 of 50, AI 0 of 50.")
        self.assertEqual(s[cell["bt"][1][1]], "Forecast unsettled: not clear-cut (30 of 100), physics and AI "
                                              "models disagree, no earlier forecast to compare.")
        self.assertEqual(s[cell["s"][0]], "Rain unlikely until Thu afternoon. Rain likely Thu 11:30–17:30 IST. "
                                          "Models disagree on Thu 11:30–17:30 IST: physics 30 of 50, AI 0 of 50.")
        # day: IFS 30 of 50 at 3 mm -> median of 50 = 3.0; pooled: 70 zeros + 30 threes -> p50 0, p75 3.0
        self.assertEqual(cell["d"][0][:2], [30, 0])
        self.assertEqual(cell["d"][0][6:], [-1, 0.0, 0.0, 0.0, 3.0, 3.0, 3.0, 0.0, 70])
        self.assertEqual(s[cell["dt"][0][0]], "Day total Thu · 05:30 Thu – 05:30 Fri IST: models disagree: "
                                              "physics median 3.0 mm (light rain), AI median 0.0 mm.")
        dry = tile["cells"]["1_1"]
        self.assertEqual(s[dry["s"][0]], "Rain unlikely for the next 48 hours, until Sat 05:30 IST.")

    def test_layers(self) -> None:
        a = layer_arrays(self.bp, self.dp)
        self.assertEqual(a["block_pooled"].shape, (40, 2, 2))
        self.assertEqual(int(a["block_pooled"][1, 0, 0]), 30)
        self.assertEqual(int(a["block_change"][1, 0, 0]), 255)  # no previous run
        self.assertEqual(int(a["block_settled"][1, 0, 0]), 0)  # not decided, models disagree, not stable
        self.assertEqual(int(a["block_settled"][1, 1, 1]), 0b011)  # dry cell: decided + agree, no previous run
        self.assertEqual(a["day_median"].dtype, np.uint16)
        self.assertEqual(int(a["block_gap"][1, 0, 0]), 20)  # AIFS 0 - IFS 30 + 50
        self.assertEqual(int(a["block_gap"][1, 1, 1]), 50)  # dry cell: no gap
        self.assertEqual(int(a["day_gap"][0, 0, 0]), 20)  # same members wet over Thu


if __name__ == "__main__":
    unittest.main()
