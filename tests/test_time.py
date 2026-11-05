"""Tests for common.time with hand-computed expectations (2026-11-05 is a Thursday)."""

import unittest
from datetime import date, datetime, timezone

from common.time import (block_label, block_name, blocks_for_run, day_label, span_label, time_label, to_ist,
                         validate_run_time)

UTC = timezone.utc


class TestToIst(unittest.TestCase):
    def test_midnight_utc_is_0530_ist(self) -> None:
        ist = to_ist(datetime(2026, 11, 5, 0, 0, tzinfo=UTC))
        self.assertEqual((ist.year, ist.month, ist.day, ist.hour, ist.minute), (2026, 11, 5, 5, 30))

    def test_late_utc_crosses_into_next_ist_day(self) -> None:
        ist = to_ist(datetime(2026, 11, 5, 18, 30, tzinfo=UTC))
        self.assertEqual((ist.day, ist.hour, ist.minute), (6, 0, 0))

    def test_naive_datetime_rejected(self) -> None:
        with self.assertRaises(ValueError):
            to_ist(datetime(2026, 11, 5, 0, 0))


class TestBlocksFor00zRun(unittest.TestCase):
    def setUp(self) -> None:
        self.blocks = blocks_for_run(datetime(2026, 11, 5, 0, tzinfo=UTC), n_full_days=1)

    def test_four_blocks_one_day(self) -> None:
        self.assertEqual([(b.start_step_h, b.end_step_h) for b in self.blocks], [(0, 6), (6, 12), (12, 18), (18, 24)])
        self.assertEqual([b.name for b in self.blocks], ["morning", "afternoon", "evening", "night"])
        self.assertTrue(all(b.app_day == date(2026, 11, 5) for b in self.blocks))

    def test_default_lead_is_ten_days_40_blocks(self) -> None:
        blocks = blocks_for_run(datetime(2026, 11, 5, 0, tzinfo=UTC))
        self.assertEqual(len(blocks), 40)
        self.assertEqual(blocks[-1].end_step_h, 240)


class TestBlocksFor12zRun(unittest.TestCase):
    def setUp(self) -> None:
        self.blocks = blocks_for_run(datetime(2026, 11, 5, 12, tzinfo=UTC), n_full_days=1)

    def test_partial_first_day_then_full_day(self) -> None:
        # Run starts 17:30 IST Thu: evening + night of Thu are partial day, then Fri boundary at step 12.
        self.assertEqual([(b.start_step_h, b.end_step_h) for b in self.blocks],
                         [(0, 6), (6, 12), (12, 18), (18, 24), (24, 30), (30, 36)])
        self.assertEqual([b.name for b in self.blocks],
                         ["evening", "night", "morning", "afternoon", "evening", "night"])
        self.assertEqual([b.app_day.day for b in self.blocks], [5, 5, 6, 6, 6, 6])

    def test_default_lead_ends_at_step_252(self) -> None:
        blocks = blocks_for_run(datetime(2026, 11, 5, 12, tzinfo=UTC))
        self.assertEqual(len(blocks), 42)
        self.assertEqual(blocks[-1].end_step_h, 252)


class TestLabels(unittest.TestCase):
    def test_night_block_crosses_midnight(self) -> None:
        night = blocks_for_run(datetime(2026, 11, 5, 0, tzinfo=UTC), n_full_days=1)[3]
        self.assertEqual(block_label(night), "Thu night · 23:30 Thu – 05:30 Fri IST")

    def test_afternoon_block_same_day(self) -> None:
        afternoon = blocks_for_run(datetime(2026, 11, 5, 0, tzinfo=UTC), n_full_days=1)[1]
        self.assertEqual(block_label(afternoon), "Thu afternoon · 11:30–17:30 IST")

    def test_spans_short_names_and_points(self) -> None:
        b = blocks_for_run(datetime(2026, 11, 5, 0, tzinfo=UTC), n_full_days=2)
        self.assertEqual(span_label(b[1], b[2]), "Thu afternoon – evening · 11:30–23:30 IST")
        self.assertEqual(span_label(b[1], b[3]), "Thu afternoon – night · 11:30 Thu – 05:30 Fri IST")
        self.assertEqual(span_label(b[3], b[5]), "Thu night – Fri afternoon · 23:30 Thu – 17:30 Fri IST")
        self.assertEqual(block_name(b[3]), "Thu night")
        self.assertEqual(time_label(b[2].start_utc), "Thu 17:30 IST")

    def test_day_label(self) -> None:
        self.assertEqual(day_label(date(2026, 11, 5)), "Thu · 05:30 Thu – 05:30 Fri IST")


class TestValidation(unittest.TestCase):
    def test_06z_run_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_run_time(datetime(2026, 11, 5, 6, tzinfo=UTC))

    def test_not_on_the_hour_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_run_time(datetime(2026, 11, 5, 0, 30, tzinfo=UTC))

    def test_zero_days_rejected(self) -> None:
        with self.assertRaises(ValueError):
            blocks_for_run(datetime(2026, 11, 5, 0, tzinfo=UTC), n_full_days=0)


if __name__ == "__main__":
    unittest.main()
