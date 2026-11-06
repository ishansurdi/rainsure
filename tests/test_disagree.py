"""Tests for process.disagree: one hand-built cell per rule on a 3-block, 5 x 5 grid near 13 N."""

import unittest

import numpy as np

from process.disagree import COMPASS, KIND, classify, neighbour_offsets

LAT = np.array([13.5, 13.25, 13.0, 12.75, 12.5])


def _grids():
    z = lambda: np.zeros((3, 5, 5))  # noqa: E731
    n_ifs, n_aifs, m_ifs, m_aifs, day = z(), z(), z(), z(), np.zeros((3, 5, 5), bool)
    # lighter at (2,2): physics 30/50 (median 3.1), AI 5/50 but median 1.8 mm
    n_ifs[1, 2, 2], n_aifs[1, 2, 2], m_ifs[1, 2, 2], m_aifs[1, 2, 2] = 30, 5, 3.1, 1.8
    # timing at (0,0): physics 30 now, AI 2 now (median 0.2) but 28 in the next block
    n_ifs[1, 0, 0], n_aifs[1, 0, 0], m_aifs[1, 0, 0], n_aifs[2, 0, 0] = 30, 2, 0.2, 28
    # position at (4,4): physics 30, AI 0 here but 27 one row north (~28 km)
    n_ifs[1, 4, 4], n_aifs[1, 3, 4] = 30, 27
    # day at (0,4): physics 30, AI 0, nothing near; the day agrees
    n_ifs[1, 0, 4], day[1, 0, 4] = 30, True
    # other at (4,0): physics 30, AI 0, nothing near, day disagrees
    n_ifs[1, 4, 0] = 30
    # agree at (2,0): 10 vs 8 (4 points)
    n_ifs[1, 2, 0], n_aifs[1, 2, 0] = 10, 8
    return n_ifs, n_aifs, m_ifs, m_aifs, day


class TestClassify(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.d = classify(*_grids(), lat=LAT, step_deg=0.25)

    def at(self, j: int, i: int) -> str:
        return [k for k, v in KIND.items() if v == self.d.kind[1, j, i]][0]

    def test_each_rule(self) -> None:
        self.assertEqual([self.at(2, 2), self.at(0, 0), self.at(4, 4), self.at(0, 4), self.at(4, 0), self.at(2, 0)],
                         ["lighter", "timing", "position", "day", "other", "none"])

    def test_facts_for_templates(self) -> None:
        d = self.d
        self.assertEqual(int(d.drier[1, 2, 2]), 1)  # AI drier
        self.assertEqual((int(d.shift[1, 0, 0]), int(d.other_n[1, 0, 0])), (1, 28))  # 6 h later, 28 of 50
        self.assertEqual(COMPASS[int(d.bearing[1, 4, 4])], "north")
        self.assertAlmostEqual(float(d.dist_km[1, 4, 4]), 27.8, delta=0.2)
        self.assertEqual(int(d.other_n[1, 4, 4]), 27)

    def test_first_rule_wins(self) -> None:
        n_ifs, n_aifs, m_ifs, m_aifs, day = _grids()
        n_aifs[2, 2, 2] = 29  # the lighter cell now also matches timing
        d = classify(n_ifs, n_aifs, m_ifs, m_aifs, day, LAT, 0.25)
        self.assertEqual(int(d.kind[1, 2, 2]), KIND["lighter"])
        self.assertEqual(int(d.match_count[1, 2, 2]), 2)
        self.assertEqual(int(d.shift[1, 2, 2]), 0)  # facts only for the winning rule

    def test_neighbours_within_50_km_at_13n(self) -> None:
        offs = neighbour_offsets(13.0, 0.25)
        self.assertEqual(len(offs), 8)  # 1 cell around: 27-39 km; 2 cells is > 50 km
        self.assertTrue(all(o[2] <= 50 for o in offs))
        self.assertLess(offs[0][2], 28)


if __name__ == "__main__":
    unittest.main()
