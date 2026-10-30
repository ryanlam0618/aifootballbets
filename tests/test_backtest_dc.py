"""Hermetic unit tests for the DC backtest framework (scripts/backtest_dc.py).

No DB access; synthetic matches only.
"""

from __future__ import annotations

import json
import math
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import backtest_dc as bt  # noqa: E402
from models.dc_model import fit_dc  # noqa: E402


def _mk(day, h, a, hg, ag, league="L1"):
    return {"match_date": day, "home": h, "away": a, "league": league, "home_goals": hg, "away_goals": ag}


def _pois(rng, lam, cap=10):
    L = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= L or k >= cap:
            return k
        k += 1


def _synthetic(n_days=300, seed=5):
    """Daily matches between 4 teams with stable strengths."""
    import random

    rng = random.Random(seed)
    teams = [("A", 1.8, 0.9), ("B", 1.5, 1.1), ("C", 1.2, 1.3), ("D", 0.9, 1.7)]
    start = date(2024, 1, 1)
    out = []
    for d in range(n_days):
        day = start + timedelta(days=d)
        h, a = rng.sample(range(4), 2)
        th, ta = teams[h], teams[a]
        hg = min(8, _pois(rng, th[1] * ta[2] * 1.15))
        ag = min(8, _pois(rng, ta[1] * th[2]))
        out.append(_mk(day, th[0], ta[0], hg, ag))
    return out


class TestTimeSplit(unittest.TestCase):
    def test_no_leakage(self):
        matches = _synthetic()
        boundary, train, val = bt.time_split(matches, 0.7)
        self.assertTrue(all(m["match_date"] < boundary for m in train))
        self.assertTrue(all(m["match_date"] >= boundary for m in val))
        self.assertEqual(min(m["match_date"] for m in val), boundary)

    def test_roughly_70_30(self):
        matches = _synthetic()
        _, train, val = bt.time_split(matches, 0.7)
        frac = len(train) / (len(train) + len(val))
        self.assertGreater(frac, 0.6)
        self.assertLess(frac, 0.8)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            bt.time_split([], 0.7)


class TestWalkforwardWindows(unittest.TestCase):
    def test_tiles_without_gaps(self):
        start, end = date(2025, 1, 1), date(2025, 12, 31)
        windows = bt.walkforward_windows(start, end, 91)
        self.assertEqual(windows[0][1], start)
        self.assertEqual(windows[-1][2], end)
        for (asof, ws, we), (_, ns, _ne) in zip(windows, windows[1:]):
            self.assertEqual(ns, we + timedelta(days=1))  # contiguous
            self.assertEqual(asof, ws)  # fit as-of window start

    def test_short_range_single_window(self):
        windows = bt.walkforward_windows(date(2025, 3, 1), date(2025, 3, 20), 91)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0][1], date(2025, 3, 1))
        self.assertEqual(windows[0][2], date(2025, 3, 20))

    def test_invalid_step(self):
        with self.assertRaises(ValueError):
            bt.walkforward_windows(date(2025, 1, 1), date(2025, 2, 1), 0)


class TestMetrics(unittest.TestCase):
    def test_logloss_perfect_and_uniform(self):
        prob_map = {0: {"Home": 1.0, "Draw": 0.0, "Away": 0.0}}
        self.assertAlmostEqual(bt.logloss_1x2(prob_map, ["Home"]), 0.0, places=9)
        prob_map = {0: {"Home": 1 / 3, "Draw": 1 / 3, "Away": 1 / 3}}
        self.assertAlmostEqual(bt.logloss_1x2(prob_map, ["Home"]), math.log(3), places=9)

    def test_hit_rate(self):
        prob_map = {
            0: {"Home": 0.5, "Draw": 0.3, "Away": 0.2},
            1: {"Home": 0.2, "Draw": 0.3, "Away": 0.5},
        }
        self.assertAlmostEqual(bt.hit_rate_1x2(prob_map, ["Home", "Home"]), 0.5)
        self.assertAlmostEqual(bt.hit_rate_1x2(prob_map, ["Home", "Away"]), 1.0)

    def test_calibration_buckets_perfect(self):
        pairs = [(0.25, 0)] * 10 + [(0.75, 1)] * 10
        buckets = bt.calibration_buckets(pairs, n_buckets=10)
        b25 = buckets[2]  # [0.2, 0.3)
        b75 = buckets[7]  # [0.7, 0.8)
        self.assertEqual(b25["n"], 10)
        self.assertAlmostEqual(b25["mean_pred"], 0.25)
        self.assertAlmostEqual(b25["realised"], 0.0)
        self.assertAlmostEqual(b75["realised"], 1.0)

    def test_calibration_top_bucket_includes_one(self):
        buckets = bt.calibration_buckets([(1.0, 1)], n_buckets=10)
        self.assertEqual(buckets[9]["n"], 1)


class TestAHRealisedEff(unittest.TestCase):
    def test_integer_line_push(self):
        self.assertAlmostEqual(bt.ah_realised_eff(1, 1, 0.0), 0.5)
        self.assertAlmostEqual(bt.ah_realised_eff(2, 1, 0.0), 1.0)
        self.assertAlmostEqual(bt.ah_realised_eff(0, 1, 0.0), 0.0)

    def test_half_line_no_push(self):
        self.assertAlmostEqual(bt.ah_realised_eff(1, 1, 0.5), 1.0)  # draw = win for +0.5
        self.assertAlmostEqual(bt.ah_realised_eff(0, 1, 0.5), 0.0)
        self.assertAlmostEqual(bt.ah_realised_eff(1, 1, -0.5), 0.0)  # draw = loss for -0.5
        self.assertAlmostEqual(bt.ah_realised_eff(2, 1, -0.5), 1.0)

    def test_quarter_line_splits(self):
        # +0.25 = (0, +0.5)/2
        self.assertAlmostEqual(bt.ah_realised_eff(1, 1, 0.25), 0.75)  # push + win
        self.assertAlmostEqual(bt.ah_realised_eff(0, 1, 0.25), 0.0)
        self.assertAlmostEqual(bt.ah_realised_eff(2, 1, 0.25), 1.0)
        # -0.25 = (-0.5, 0)/2
        self.assertAlmostEqual(bt.ah_realised_eff(1, 1, -0.25), 0.25)  # lose + push
        self.assertAlmostEqual(bt.ah_realised_eff(2, 1, -0.25), 1.0)
        # +0.75 = (+0.5, +1)/2
        self.assertAlmostEqual(bt.ah_realised_eff(1, 1, 0.75), 1.0)
        self.assertAlmostEqual(bt.ah_realised_eff(2, 2, 0.75), 1.0)  # both halves win
        self.assertAlmostEqual(bt.ah_realised_eff(2, 3, 0.75), 0.25)  # lose(-0.5... ) push(+1): (0 + 0.5)/2

    def test_complementarity_all_scorelines(self):
        # swapped-perspective complementarity: home side of (H +L) plus the
        # home side of the mirrored market (A -L) covers all outcomes
        for line in bt.AH_LINES:
            for hg in range(4):
                for ag in range(4):
                    self.assertAlmostEqual(
                        bt.ah_realised_eff(hg, ag, line) + bt.ah_realised_eff(ag, hg, -line), 1.0
                    )


class TestScoringWithModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        matches = _synthetic(n_days=200)
        cls.model = fit_dc(
            bt.to_match_records(matches[:140]),
            asof=date(2024, 5, 20),
            half_life_days=365.0,
            min_matches=10,
            max_sweeps=15,
        )
        cls.val = matches[140:]

    def test_score_1x2_structure(self):
        s = bt.score_1x2(self.model, self.val, max_goals=10)
        self.assertEqual(s["n"], len(self.val))
        self.assertTrue(0.0 <= s["hit_rate"] <= 1.0)
        self.assertGreater(s["logloss"], 0.0)
        self.assertEqual(len(s["calibration"]), 10)

    def test_score_ah_structure(self):
        s = bt.score_ah(self.model, self.val, max_goals=10)
        self.assertEqual(set(s.keys()), {0.0, 0.25, 0.5, 0.75, 1.0})
        for v in s.values():
            self.assertTrue(0.0 <= v["mean_real_eff"] <= 1.0)
            self.assertTrue(0.0 <= v["pick_hit_rate"] <= 1.0)
            self.assertTrue(0.0 <= v["pick_pts_per_bet"] <= 1.0)


class TestFractionalOdds(unittest.TestCase):
    def test_fractional_to_decimal(self):
        f = bt._fractional_to_decimal
        self.assertAlmostEqual(f("5/4"), 2.25)
        self.assertAlmostEqual(f("12/5"), 3.4)
        self.assertAlmostEqual(f("10/11"), 1 + 10 / 11)
        self.assertAlmostEqual(f("3"), 3.0)
        self.assertIsNone(f(""))
        self.assertIsNone(f(None))
        self.assertIsNone(f("EVS"))
        self.assertIsNone(f("abc/def"))
        self.assertIsNone(f("0"))


class TestReportRender(unittest.TestCase):
    def test_render_contains_markers(self):
        report = {
            "meta": {"min_date": "2015-01-01", "generated": "2026-10-29T00:00:00Z"},
            "holdout": {
                "_meta": {"boundary": "2024-01-01", "train_n": 100, "val_n": 50},
                "overall": {"n": 50, "hit_rate": 0.52, "logloss": 1.05},
                "ah_by_line_overall": {
                    "0.5": {"n": 50, "mean_pred_eff": 0.5, "mean_real_eff": 0.48, "pick_hit_rate": 0.5, "pick_pts_per_bet": 0.5}
                },
                "market": {"n_matches_with_odds": 30, "mean_edge": {"Home": 0.01}},
                "per_league": {"L1": {"n": 50, "hit_rate": 0.52, "logloss": 1.05}},
            },
        }
        txt = bt.render_txt(report)
        self.assertIn("DIXON-COLES BACKTEST REPORT", txt)
        self.assertIn("MODE: HOLDOUT", txt)
        self.assertIn("AH 0.5", txt)
        self.assertIn("league L1", txt)
        json.dumps(report)  # serialisable


if __name__ == "__main__":
    unittest.main()
