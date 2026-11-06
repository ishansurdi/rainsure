"""Tests for process.wording: exact sentences for hand-picked counts (2026-11-05 is a Thursday)."""

import random
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from common import config
from common.time import blocks_for_run
from process.wording import (BlockCounts, block_sentence, confidence_sentence, day_sentence, disagree_explanation,
                             prob_word, rain_category, summary_48h)

BLOCKS = blocks_for_run(datetime(2026, 11, 5, 0, tzinfo=timezone.utc), n_full_days=2)  # Thu morning .. Fri night
THU, FRI = date(2026, 11, 5), date(2026, 11, 6)
NO_SPREAD = {THU: 0, FRI: 0}


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
        cases = {0.04: None, 0.05: "very light rain", 2.44: "very light rain", 2.45: "light rain",
                 15.5: "light rain", 15.55: "moderate rain", 64.5: "heavy rain", 115.6: "very heavy rain",
                 204.4: "very heavy rain", 204.5: "extremely heavy rain"}
        for mm, cat in cases.items():
            self.assertEqual(rain_category(mm), cat, mm)


class TestSentences(unittest.TestCase):
    def test_block_sentence(self) -> None:
        label = "Thu afternoon · 11:30–17:30 IST"
        self.assertEqual(block_sentence(label, 54),
                         "Rain very likely Thu afternoon · 11:30–17:30 IST: 54 of 100 forecasts show at least 2.5 mm.")

    def test_disagreement_explained_once_by_kind(self) -> None:
        lead = "Physics and AI models disagree: physics 30 of 50, AI 5 of 50. "
        self.assertEqual(disagree_explanation("lighter", 30, 5, 1, 3.1, 1.8),
                         lead + "Both expect rain; the AI model's is lighter (median 1.8 mm against 3.1 mm), "
                                "so fewer of its forecasts reach 2.5 mm.")
        self.assertEqual(disagree_explanation("timing", 30, 5, 1, 3.1, 0.2, shift=1, other_n=28,
                                              other_span="Fri 17:30–23:30 IST"),
                         lead + "The AI model has this rain about 6 hours later: 28 of 50 in Fri 17:30–23:30 IST.")
        self.assertEqual(disagree_explanation("position", 5, 30, 0, 0.0, 4.0, other_n=27, dist_km=27.8,
                                              direction="north"),
                         "Physics and AI models disagree: physics 5 of 50, AI 30 of 50. "
                         "The physics model puts this rain about 30 km north: 27 of 50 there.")
        self.assertEqual(disagree_explanation("day", 30, 5, 1, 3.1, 0.0),
                         lead + "They agree on the day as a whole and differ on timing within it.")
        self.assertEqual(disagree_explanation("other", 30, 5, 1, 3.1, 0.0),
                         lead + "The two models expect different outcomes here.")
        with self.assertRaises(ValueError):
            disagree_explanation("none", 1, 1, 0, 0.0, 0.0)

    def test_settled_wording(self) -> None:
        self.assertEqual(confidence_sentence(54, False, True, False, 20),
                         "Forecast unsettled: not clear-cut (54 of 100), up 34 points since the previous forecast.")
        self.assertEqual(confidence_sentence(0, True, True, True, 0), "Forecast settled.")
        self.assertEqual(confidence_sentence(90, True, True, False, None),
                         "Forecast fairly settled: no earlier forecast to compare.")
        self.assertEqual(confidence_sentence(10, True, False, False, 40),
                         "Forecast unsettled: down 30 points since the previous forecast.")  # disagreement said once, elsewhere

    def test_day(self) -> None:
        label = "Thu · 05:30 Thu – 05:30 Fri IST"
        self.assertEqual(day_sentence(label, True, 2.4, 4.0, 5.5, 3.6, 4.4, 0, 73),
                         "Day total Thu · 05:30 Thu – 05:30 Fri IST: median 4.0 mm (light rain), "
                         "middle half 2.4–5.5 mm.")
        self.assertEqual(day_sentence(label, True, 0.0, 0.0, 0.0, 0.0, 0.0, 100, 0),
                         "Day total Thu · 05:30 Thu – 05:30 Fri IST: under 0.1 mm in 100 of 100 forecasts.")
        self.assertEqual(day_sentence(label, True, 0.0, 0.02, 1.3, 0.0, 0.1, 58, 12),
                         "Day total Thu · 05:30 Thu – 05:30 Fri IST: under 0.1 mm in 58 of 100 forecasts; "
                         "12 of 100 show at least 2.5 mm.")
        self.assertEqual(day_sentence(label, False, 1.2, 1.8, 2.9, 2.7, 0.0, 10, 33),
                         "Day total Thu · 05:30 Thu – 05:30 Fri IST: models disagree: physics median 2.7 mm "
                         "(light rain), AI median 0.0 mm.")


class TestSummary48h(unittest.TestCase):
    def test_dry(self) -> None:
        self.assertEqual(summary_48h(_window([(0, 0)] * 8), NO_SPREAD),
                         "Rain unlikely for the next 48 hours, until Sat 05:30 IST.")

    def test_one_spell(self) -> None:
        # 24 of 100 is unlikely; Thu evening 26+24 = 50 likely (gap 4 points: no disagreement note)
        w = _window([(0, 0), (12, 12), (26, 24), (0, 0), (0, 0), (0, 0), (0, 0), (0, 0)])
        self.assertEqual(summary_48h(w, NO_SPREAD), "Rain unlikely until Thu evening. Rain likely Thu 17:30–23:30 IST.")

    def test_two_spells_up_to(self) -> None:
        # spell 1: Thu afternoon 47+46 = 93 most likely, evening 14+23 = 37 likely -> "up to most likely"
        # spell 2: Fri afternoon 20+19 = 39, one block -> "likely"; largest model gap 18 points -> no note
        w = _window([(1, 1), (47, 46), (14, 23), (2, 7), (1, 6), (20, 19), (3, 6), (1, 5)])
        self.assertEqual(summary_48h(w, NO_SPREAD),
                         "Rain unlikely until Thu afternoon. Rain up to most likely Thu 11:30–23:30 IST. "
                         "Rain likely again Fri 11:30–17:30 IST.")

    def test_on_and_off_with_disagreement(self) -> None:
        # wet: Thu night 28, Fri afternoon 29 (1 vs 28: 54-point gap), Fri night 30 -> all "likely", no "up to"
        w = _window([(3, 3), (0, 11), (2, 0), (18, 10), (10, 12), (1, 28), (4, 8), (14, 16)])
        self.assertEqual(summary_48h(w, NO_SPREAD),
                         "Rain unlikely until Thu night. Then on and off until Sat 05:30 IST: rain likely in "
                         "3 of the next 8 six-hour periods.")  # no disagreement note in the summary any more (D60)

    def test_wet_from_the_start(self) -> None:
        w = _window([(40, 40), (0, 0), (20, 20), (0, 0), (20, 20), (0, 0), (0, 0), (0, 0)])
        self.assertEqual(summary_48h(w, NO_SPREAD),
                         "On and off until Fri 11:30 IST: rain up to most likely in 3 of the next 8 six-hour periods.")

    def test_spread_day_without_wet_block(self) -> None:
        # Hyderabad-like: every block 24 of 100 or less, but 33 of 100 reach 2.5 mm over Thu
        w = _window([(4, 0), (8, 0), (4, 0), (0, 0), (0, 0), (4, 0), (3, 0), (0, 0)])
        self.assertEqual(summary_48h(w, {THU: 33, FRI: 7}),
                         "Rain likely, spread thinly over Thu 05:30 – Fri 05:30 IST: 33 of 100 forecasts show at least "
                         "2.5 mm over the whole day.")

    def test_spread_day_before_wet_spell_in_time_order(self) -> None:
        w = _window([(4, 0), (8, 0), (4, 0), (0, 0), (0, 0), (20, 20), (3, 0), (0, 0)])
        self.assertEqual(summary_48h(w, {THU: 30, FRI: 45}),
                         "Rain likely, spread thinly over Thu 05:30 – Fri 05:30 IST: 30 of 100 forecasts show at least "
                         "2.5 mm over the whole day. Rain likely Fri 11:30–17:30 IST.")

    def test_consecutive_spread_days_merge(self) -> None:
        # Chennai-like: no block >= 25 of 100, but both days are wet in total -> one sentence, count range
        w = _window([(6, 6)] * 8)
        self.assertEqual(summary_48h(w, {THU: 30, FRI: 79}),
                         "Rain up to most likely, spread thinly over Thu 05:30 – Sat 05:30 IST: 30–79 of 100 forecasts "
                         "show at least 2.5 mm a day.")

    def test_limit_keeps_nearest_and_points_to_timeline(self) -> None:
        # from Thu afternoon: wet Thu afternoon, spread Fri (60 of 100 over the day), wet Sat morning.
        blocks = blocks_for_run(datetime(2026, 11, 5, 0, tzinfo=timezone.utc), n_full_days=3)[1:9]
        counts = [(20, 20), (0, 0), (0, 0), (10, 10), (10, 10), (10, 10), (10, 10), (20, 20)]
        w = [BlockCounts(b, i, a) for b, (i, a) in zip(blocks, counts)]
        days = {THU: 40, FRI: 60, date(2026, 11, 7): 40}
        full = summary_48h(w, days)  # everything fits in 200
        self.assertTrue(full.startswith("Rain likely Thu 11:30–17:30 IST. Rain very likely, spread thinly over Fri"))
        self.assertTrue(full.endswith("Rain likely again Sat 05:30–11:30 IST."))
        with patch.object(config, "SUMMARY_MAX_CHARS", 80):
            self.assertEqual(summary_48h(w, days), "Rain likely Thu 11:30–17:30 IST. More rain later: see the timeline.")

    def test_never_over_limit_random(self) -> None:
        rng = random.Random(20261105)
        blocks = blocks_for_run(datetime(2026, 11, 4, 12, tzinfo=timezone.utc))  # 12z: partial first day
        for _ in range(5000):
            s = rng.randrange(0, config.SUMMARY_START_BLOCKS)
            sel = blocks[s:s + 8]
            w = [BlockCounts(b, rng.choice([0, 0, 3, 12, 13, 25, 26, 40, 50]), rng.choice([0, 0, 2, 12, 13, 25, 38, 50]))
                 for b in sel]
            days = {b.app_day: rng.choice([0, 10, 24, 25, 60, 100]) for b in sel}
            text = summary_48h(w, days)
            self.assertLessEqual(len(text), config.SUMMARY_MAX_CHARS, text)
            if text.startswith("Rain unlikely for the next 48 hours"):
                self.assertTrue(all(b.n_pooled < 25 for b in w))

    def test_wrong_length(self) -> None:
        with self.assertRaises(ValueError):
            summary_48h(_window([(0, 0)] * 4), NO_SPREAD)


if __name__ == "__main__":
    unittest.main()
