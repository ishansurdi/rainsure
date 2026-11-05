"""Tests for the API: import isolation (D42) and endpoint logic on a hand-written published tile."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

import api.main as main
from api.data import Store, data_status

UTC = timezone.utc
META = {
    "run_id": "2026110500", "run_time_utc": "2026-11-05T00:00:00+00:00", "previous_run_id": None,
    "processed_at_utc": "2026-11-05T08:00:00+00:00", "day_thresholds_mm": [2.5, 15.6, 64.5],
    "grid": {"lat_first": 13.0, "lon_first": 80.0, "step_deg": 0.25, "n_lat": 2, "n_lon": 2},
    "tile_cells": 4, "summary_start_blocks": 2,
    "blocks": [{"start_utc": "2026-11-05T00:00:00+00:00", "end_utc": "2026-11-05T06:00:00+00:00",
                "label": "Thu morning · 05:30–11:30 IST"},
               {"start_utc": "2026-11-05T06:00:00+00:00", "end_utc": "2026-11-05T12:00:00+00:00",
                "label": "Thu afternoon · 11:30–17:30 IST"}],
    "days": [{"app_day": "2026-11-05", "label": "Thu · 05:30 Thu – 05:30 Fri IST"}],
}
CELL = {"b": [[0, 0, -1, "00" * 13], [30, 24, 20, "ff" * 13]], "bt": [[0, 1], [2, 3]],
        "d": [[30, 40, 2, 3, 0, 0, -1, 1.7, 2.4, 4.0, 5.5, 7.6, 3.6, 4.4, 5]], "dt": [[4, 1]], "s": [5, 6]}
TILE = {"run": "2026110500", "tile": [0, 0], "strings": ["s0", "s1", "s2", "s3", "s4", "s5", "s6"],
        "cells": {"0_0": CELL, "0_1": CELL, "1_0": CELL, "1_1": CELL}}


class TestImportIsolation(unittest.TestCase):
    def test_api_does_not_load_numpy_or_xarray(self) -> None:
        code = "import sys, api.main; print(sorted(m for m in ('numpy', 'xarray') if m in sys.modules))"
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                             cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(out.stdout.strip(), "[]")


class TestEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "2026110500" / "points").mkdir(parents=True)
        (root / "latest.json").write_text(json.dumps(META), encoding="utf-8")
        (root / "2026110500" / "points" / "t0_0.json").write_text(json.dumps(TILE), encoding="utf-8")
        os.environ["DATA_BASE_URL"] = root.as_uri()
        main.store = Store()

    def tearDown(self) -> None:
        os.environ.pop("DATA_BASE_URL", None)
        self.tmp.cleanup()

    def test_point_picks_cell_block_and_sentences(self) -> None:
        p = main.point(lat=12.9, lon=80.2, at=datetime(2026, 11, 5, 7, tzinfo=UTC))
        self.assertEqual((p.lat, p.lon), (13.0, 80.25))  # 12.9 N -> row 0 (13.0, nearer than 12.75); 80.2 E -> 80.25
        self.assertEqual(p.current_block, 1)
        self.assertEqual(p.summary_48h, "s6")
        self.assertTrue(p.blocks[0].past)
        self.assertFalse(p.blocks[1].past)
        self.assertEqual((p.blocks[1].n_pooled, p.blocks[1].n_previous, p.blocks[0].n_previous), (54, 20, None))
        self.assertEqual((p.blocks[1].answer, p.blocks[1].settled), ("s2", "s3"))
        d = p.days[0]
        self.assertEqual(d.counts["2.5"], {"ifs": 30, "aifs": 40, "pooled": 70})
        self.assertEqual(d.counts["15.6"]["pooled"], 5)
        self.assertEqual(d.percentiles_mm["p50"], 4.0)
        self.assertEqual((d.median_ifs_mm, d.median_aifs_mm, d.n_under_0_1_mm, d.n_previous), (3.6, 4.4, 5, None))
        self.assertEqual(d.text, "s4")

    def test_healthz_needs_no_data(self) -> None:
        os.environ["DATA_BASE_URL"] = "file:///nonexistent"
        self.assertEqual(main.healthz(), {"ok": True})

    def test_outside_grid_is_404(self) -> None:
        with self.assertRaises(HTTPException) as e:
            main.point(lat=20.0, lon=80.0, at=None)
        self.assertEqual(e.exception.status_code, 404)

    def test_naive_time_is_422(self) -> None:
        with self.assertRaises(HTTPException) as e:
            main.point(lat=13.0, lon=80.0, at=datetime(2026, 11, 5, 7))
        self.assertEqual(e.exception.status_code, 422)

    def test_expired_has_no_summary(self) -> None:
        p = main.point(lat=13.0, lon=80.0, at=datetime(2026, 11, 5, 13, tzinfo=UTC))  # after the last block
        self.assertIsNone(p.summary_48h)
        self.assertEqual(p.meta.data_status, "expired")


class TestStatus(unittest.TestCase):
    def test_fresh_stale_expired(self) -> None:
        m = dict(META, summary_start_blocks=2)
        m["blocks"] = [{"start_utc": f"2026-11-0{5 + h // 24}T{h % 24:02d}:00:00+00:00",
                        "end_utc": f"2026-11-0{5 + (h + 6) // 24}T{(h + 6) % 24:02d}:00:00+00:00"}
                       for h in range(0, 36, 6)]
        m["summary_start_blocks"] = 6
        self.assertEqual(data_status(m, datetime(2026, 11, 5, 9, tzinfo=UTC)), "fresh")
        self.assertEqual(data_status(m, datetime(2026, 11, 6, 1, tzinfo=UTC)), "stale")  # 25 h after run start
        m["summary_start_blocks"] = 2
        self.assertEqual(data_status(m, datetime(2026, 11, 5, 13, tzinfo=UTC)), "expired")


if __name__ == "__main__":
    unittest.main()
