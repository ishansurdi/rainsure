"""Tests for ingest.decode, common.io and archive run selection, with synthetic GRIB and tiny arrays."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import eccodes
import numpy as np
import xarray as xr

from common.config import GridSpec
from common.io import archive_stem, read_archive, write_archive
from common.time import recent_runs
from ingest.archive_run import archive_steps, pending_runs
from ingest.decode import decode_tp_members

UTC = timezone.utc
TINY = GridSpec(ni=4, nj=3, lat_first=1.0, lon_first=180.0, step_deg=0.25)


def _grib(number: int, end_step: int, values: np.ndarray, start_step: int = 0) -> bytes:
    """Synthetic accumulated tp GRIB2 message (units m) on the TINY grid, built from an ecCodes sample."""
    h = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    for k, v in [("productDefinitionTemplateNumber", 11), ("discipline", 0), ("paramId", 228),
                 ("typeOfStatisticalProcessing", 1), ("startStep", start_step), ("endStep", end_step),
                 ("Ni", 4), ("Nj", 3), ("latitudeOfFirstGridPointInDegrees", 1.0),
                 ("longitudeOfFirstGridPointInDegrees", 180.0), ("latitudeOfLastGridPointInDegrees", 0.5),
                 ("longitudeOfLastGridPointInDegrees", 180.75), ("iDirectionIncrementInDegrees", 0.25),
                 ("jDirectionIncrementInDegrees", 0.25), ("number", number)]:
        eccodes.codes_set(h, k, v)
    eccodes.codes_set_values(h, values.astype(float))
    msg = eccodes.codes_get_message(h)
    eccodes.codes_release(h)
    return msg


class TestDecode(unittest.TestCase):
    def test_values_coords_and_units(self) -> None:
        v = np.arange(12) / 1000.0  # 0..0.011 m, row-major north->south, west->east
        da = decode_tp_members([(1, _grib(1, 6, v)), (2, _grib(2, 6, 2 * v))], 6, TINY)
        self.assertEqual(da.dims, ("member", "latitude", "longitude"))
        self.assertEqual(list(da["member"].values), [1, 2])
        np.testing.assert_allclose(da["latitude"].values, [1.0, 0.75, 0.5])
        np.testing.assert_allclose(da["longitude"].values, [180.0, 180.25, 180.5, 180.75])
        np.testing.assert_allclose(da.sel(member=1).values, v.reshape(3, 4), atol=1e-6)
        np.testing.assert_allclose(da.sel(member=2).values[2, 3], 0.022, atol=1e-6)
        self.assertEqual(da.attrs["units"], "m")
        self.assertGreater(da.attrs["packing_error_max"], 0.0)
        self.assertLess(da.attrs["packing_error_max"], 0.001)  # well under the 0.022 m range

    def test_step_range_not_from_zero_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "stepRange"):
            decode_tp_members([(1, _grib(1, 12, np.zeros(12), start_step=6))], 12, TINY)

    def test_wrong_member_number_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "number"):
            decode_tp_members([(3, _grib(4, 6, np.zeros(12)))], 6, TINY)

    def test_wrong_grid_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Ni"):
            decode_tp_members([(1, _grib(1, 6, np.zeros(12)))], 6, TINY._replace(ni=5))


class TestArchiveIo(unittest.TestCase):
    def test_round_trip(self) -> None:
        da = xr.DataArray(np.arange(16, dtype=np.float32).reshape(2, 2, 2, 2),
                          dims=("step_h", "member", "latitude", "longitude"),
                          coords={"step_h": [6, 12], "member": [1, 2], "latitude": [1.0, 0.75], "longitude": [68.0, 68.25]},
                          attrs={"units": "mm"})
        with tempfile.TemporaryDirectory() as d:
            npz, _ = write_archive(da, {"stem": "tp_x_2026110500", "model": "x"}, Path(d))
            back = read_archive(npz)
        np.testing.assert_array_equal(back.values, da.values)
        self.assertEqual(list(back["step_h"].values), [6, 12])
        self.assertEqual(back.attrs["units"], "mm")
        self.assertEqual(back.attrs["model"], "x")

    def test_rejects_non_mm(self) -> None:
        da = xr.DataArray(np.zeros((1, 1, 1, 1)), dims=("step_h", "member", "latitude", "longitude"), attrs={"units": "m"})
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(ValueError, "mm"):
            write_archive(da, {"stem": "s"}, Path(d))


class TestRunSelection(unittest.TestCase):
    def test_recent_runs_newest_first(self) -> None:
        runs = recent_runs(datetime(2026, 11, 5, 6, 9, tzinfo=UTC), 36)
        self.assertEqual([f"{r:%d%H}" for r in runs], ["0500", "0412", "0400"])

    def test_archive_steps_00z_and_12z(self) -> None:
        s0 = archive_steps(datetime(2026, 11, 5, 0, tzinfo=UTC))
        s12 = archive_steps(datetime(2026, 11, 5, 12, tzinfo=UTC))
        self.assertEqual((s0[0], s0[-1], len(s0)), (6, 240, 40))
        self.assertEqual((s12[0], s12[-1], len(s12)), (6, 252, 42))

    def test_pending_skips_complete_runs_oldest_first(self) -> None:
        now = datetime(2026, 11, 5, 6, 9, tzinfo=UTC)
        done_0412 = {f"{archive_stem(m, datetime(2026, 11, 4, 12, tzinfo=UTC))}.npz" for m in ("ifs-ens", "aifs-ens")}
        half_0400 = {f"{archive_stem('ifs-ens', datetime(2026, 11, 4, 0, tzinfo=UTC))}.npz"}
        todo = [f"{r:%Y%m%d%H}" for r in pending_runs(now, done_0412 | half_0400)]
        self.assertEqual(todo, ["2026110112", "2026110200", "2026110212", "2026110300", "2026110312",
                                "2026110400", "2026110500"])


if __name__ == "__main__":
    unittest.main()
