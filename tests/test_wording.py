"""Tests for process.wording: exact sentences for hand-picked counts (2026-11-05 is a Thursday)."""

import unittest
from datetime import datetime, timezone

from common.time import blocks_for_run
from process.wording import (BlockCounts, block_sentence, confidence_sentence, day_sentence, disagree_sentence,
                             prob_word, rain_category, summary_48h)

BLOCKS = blocks_for_run(datetime(2026, 11, 5, 0, tzinfo=timezone.utc), n_full_days=2)  # Thu morning .. Fri night


def _window(pairs: list[tuple[int, int]]) -> list[BlockCounts]:
    return [BlockCounts(b, i, a) for b, (i, a) in zip(BLOCKS, pairs)]


class TestProbWord(unittest.TestCase):
    def test_boundaries_of_100(self) -> None:
        cases = {0: "unlikely", 24: "unlikely", 25: "likely", 50: "likely", 51: "very likely",
                 75: "very likely", 76: "most likely", 100: "most likely"}
        for n, w in cases.items():
            self.assertEqual(prob_word(n, 100), w, n)

    def test_boundaries_of_50(self) -> None:
        # 12/50 = 24 %, 13/50 = 26 %, 25/50 = 50 %, 26/50 = 52 %, 37/50 = 74 %, 38/50 = 76 %
        cases = {12: "unlikely", 13: "likely", 25: "likely", 26: "very likely", 37: "very likely", 38: "most likely"}
        for n, w in cases.items():
            self.assertEqual(prob_word(n, 50), w, n)

    def test_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            prob_word(51, 50)


class TestRainCategory(unittest.TestCase):
    def test_edges_on_displayed_value(self) -> None:
        cases = {0.04: "no rain", 0.05: "very light rain", 2.44: "very light rain", 2.45: "light rain",
                 15.5: "light rain", 15.55: "moderate rain", 64.5: "heavy rain", 115.6: "very heavy rain",
                 204.4: "very heavy rain", 204.5: "extremely heavy rain"}
        for mm, cat in cases.items():
            self.assertEqual(rain_category(mm), cat, mm)


class TestSentences(unittest.TestCase):
    def test_block_and_disagree(self) -> None:
        label = "Thu afternoon · 11:30–17:30 IST"
        self.assertEqual(block_sentence(label, 54),
                         "Rain very likely Thu afternoon · 11:30–17:30 IST: 54 of 100 forecasts give ≥ 2.5 mm.")
        self.assertEqual(disagree_sentence(label, 1, 28),
                         "Models disagree on rain Thu afternoon · 11:30–17:30 IST: physics 1 of 50, AI 28 of 50.")

    def test_confidence(self) -> None:
        self.assertEqual(confidence_sentence(54, False, True, False, 20),
                         "Confidence low: not clear-cut (54 of 100), up 34 points since the previous forecast.")
        self.assertEqual(confidence_sentence(0, True, True, True, 0), "Confidence high.")
        self.assertEqual(confidence_sentence(90, True, True, False, None),
                         "Confidence medium: no earlier forecast to compare.")
        self.assertEqual(confidence_sentence(10, True, False, False, 40),
                         "Confidence low: physics and AI models disagree, down 30 points since the previous forecast.")

    def test_day(self) -> None:
        label = "Thu · 05:30 Thu – 05:30 Fri IST"
        self.assertEqual(day_sentence(label, True, 2.4, 4.0, 5.5, 3.6, 4.4),
                         "Day total Thu · 05:30 Thu – 05:30 Fri IST: likely light rain "
                         "(median 4.0 mm, middle half 2.4–5.5 mm).")
        self.assertEqual(day_sentence(label, True, 0.0, 0.0, 0.0, 0.0, 0.0),
                         "Day total Thu · 05:30 Thu – 05:30 Fri IST: likely no rain (median 0.0 mm).")
        self.assertEqual(day_sentence(label, False, 1.2, 1.8, 2.9, 2.7, 1.3),
                         "Day total Thu · 05:30 Thu – 05:30 Fri IST: models disagree: physics median 2.7 mm "
                         "(light rain), AI median 1.3 mm (very light rain).")


class TestSummary48h(unittest.TestCase):
    def test_dry(self) -> None:
        self.assertEqual(summary_48h(_window([(0, 0)] * 8)), "Dry for the next 48 hours, until Sat 05:30 IST.")

    def test_one_spell_then_dry(self) -> None:
        # 24 of 100 is still dry; Thu evening 26+24 = 50 likely (gap 4 points: no disagreement note)
        w = _window([(0, 0), (12, 12), (26, 24), (0, 0), (0, 0), (0, 0), (0, 0), (0, 0)])
        self.assertEqual(summary_48h(w), "Dry until Thu evening. Rain likely Thu evening · 17:30–23:30 IST.")

    def test_two_spells_word_is_spell_max(self) -> None:
        # spell 1: Thu afternoon 47+46 = 93, evening 14+23 = 37 -> most likely; spell 2: Fri afternoon 20+19 = 39
        w = _window([(1, 1), (47, 46), (14, 23), (2, 7), (1, 6), (20, 19), (3, 6), (1, 5)])
        self.assertEqual(summary_48h(w), "Dry until Thu afternoon. Rain most likely Thu afternoon – evening · "
                                         "11:30–23:30 IST, and likely again Fri afternoon · 11:30–17:30 IST.")

    def test_on_and_off_with_disagreement(self) -> None:
        # wet: Thu night 28, Fri afternoon 29 (1 vs 28: 54-point gap), Fri night 30
        w = _window([(3, 3), (0, 11), (2, 0), (18, 10), (10, 12), (1, 28), (4, 8), (14, 16)])
        self.assertEqual(summary_48h(w), "Dry until Thu night. Then on and off until Sat 05:30 IST: rain likely in "
                                         "3 of 8 blocks. Models disagree on Fri afternoon · 11:30–17:30 IST: "
                                         "physics 1 of 50, AI 28 of 50.")

    def test_wet_from_the_start(self) -> None:
        w = _window([(40, 40), (0, 0), (20, 20), (0, 0), (20, 20), (0, 0), (0, 0), (0, 0)])
        self.assertEqual(summary_48h(w), "On and off until Fri 11:30 IST: rain most likely in 3 of 8 blocks.")  # last wet = Fri morning

    def test_wrong_length(self) -> None:
        with self.assertRaises(ValueError):
            summary_48h(_window([(0, 0)] * 4))


if __name__ == "__main__":
    unittest.main()
