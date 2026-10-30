"""Hermetic tests for T2: calibration, betting sim, per-league HA, weights."""

from __future__ import annotations

import math
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import backtest_t2 as t2  # noqa: E402
from models.calibration import (  # noqa: E402
    apply_grouped_temperature,
    apply_temperature,
    cup_vs_league_group,
    fit_grouped_temperature_1x2,
    fit_isotonic_1x2,
    fit_temperature_1x2,
    isotonic_pava,
    isotonic_predict,
    nll_1x2,
)
from models.dc_model import MatchRecord, fit_dc  # noqa: E402
from scripts.backtest_dc import to_match_records  # noqa: E402


class TestIsotonic(unittest.TestCase):
    def test_pava_monotone_and_identity_on_perfect_data(self):
        pairs = [(0.1, 0.0)] * 20 + [(0.5, 0.0)] * 20 + [(0.9, 1.0)] * 20
        bp = isotonic_pava(pairs)
        ys = [y for _, y in bp]
        self.assertEqual(ys, sorted(ys))
        # near-perfect separation: fitted values at 0.9 should exceed 0.5's
        self.assertGreater(isotonic_predict(bp, 0.9), isotonic_predict(bp, 0.5))

    def test_predict_clamps_outside_range(self):
        bp = isotonic_pava([(0.2, 0.1), (0.8, 0.9)])
        self.assertEqual(isotonic_predict(bp, 0.0), 0.1)
        self.assertEqual(isotonic_predict(bp, 1.0), 0.9)


class TestTemperature(unittest.TestCase):
    def _overconfident_rows(self, n=200, seed=1):
        """Rows where the model is systematically overconfident."""
        import random

        rng = random.Random(seed)
        rows, outs = [], []
        for _ in range(n):
            p_true = rng.uniform(0.2, 0.6)
            p_model = min(0.97, p_true + 0.3)  # overconfident
            home = rng.random() < p_true
            rows.append({"Home": p_model, "Draw": (1 - p_model) * 0.55, "Away": (1 - p_model) * 0.45})
            outs.append("Home" if home else rng.choice(["Draw", "Away"]))
        return rows, outs

    def test_apply_temperature_identity_and_flatten(self):
        row = {"Home": 0.6, "Draw": 0.25, "Away": 0.15}
        self.assertAlmostEqual(apply_temperature(row, 1.0)["Home"], 0.6, places=10)
        flat = apply_temperature(row, 10.0)
        for v in flat.values():
            self.assertLess(abs(v - 1 / 3), 0.05)
        self.assertAlmostEqual(sum(flat.values()), 1.0, places=10)

    def test_fit_temperature_improves_nll_on_overconfident(self):
        rows, outs = self._overconfident_rows()
        before = nll_1x2(rows, outs)
        t, ll_after = fit_temperature_1x2(rows, outs)
        self.assertGreater(t, 1.0)  # overconfidence -> T > 1
        self.assertLess(ll_after, before)

    def test_grouped_fit(self):
        rows, outs = self._overconfident_rows()
        groups = ["cup"] * (len(rows) // 2) + ["league"] * (len(rows) - len(rows) // 2)
        fitted = fit_grouped_temperature_1x2(rows, outs, groups)
        self.assertEqual(set(fitted.keys()), {"cup", "league"})
        applied = apply_grouped_temperature(rows, groups, fitted)  # fitted: {group: (T, ll)}
        self.assertEqual(len(applied), len(rows))
        self.assertAlmostEqual(sum(applied[0].values()), 1.0, places=10)


class TestCupGrouping(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(cup_vs_league_group("FA Cup"), "cup")
        self.assertEqual(cup_vs_league_group("Chinese FA Cup"), "cup")
        self.assertEqual(cup_vs_league_group("Premier League"), "league")
        self.assertEqual(cup_vs_league_group("J1 League"), "league")
        self.assertEqual(cup_vs_league_group("UCL"), "continental")
        self.assertEqual(cup_vs_league_group("AFC Champions League Two"), "continental")


class TestFlatStakeSim(unittest.TestCase):
    def _rows(self):
        # two bets: one winning at odds 3.0, one losing at odds 2.0
        return [
            {
                "p_model": {"Home": 0.60, "Draw": 0.20, "Away": 0.20},
                "p_market": {"Home": 0.50, "Draw": 0.25, "Away": 0.25},
                "odds": {"Home": 3.0, "Draw": 3.5, "Away": 3.5},
                "outcome": "Home",
            },
            {
                "p_model": {"Home": 0.20, "Draw": 0.20, "Away": 0.65},
                "p_market": {"Home": 0.30, "Draw": 0.25, "Away": 0.45},
                "odds": {"Home": 3.0, "Draw": 3.5, "Away": 2.0},
                "outcome": "Home",
            },
        ]

    def test_roi_math(self):
        res = t2.simulate_flat_stake(self._rows(), threshold=0.05)
        # bet 1: edge Home 0.10 -> odds 3.0 win -> payout 3; bet 2: edge Away 0.20 -> lose
        self.assertEqual(res["bets"], 2)
        self.assertAlmostEqual(res["staked"], 2.0)
        self.assertAlmostEqual(res["roi"], (3.0 - 2.0) / 2.0, places=9)
        self.assertAlmostEqual(res["hit_rate"], 0.5)

    def test_threshold_filters(self):
        res = t2.simulate_flat_stake(self._rows(), threshold=0.15)
        # bet 1 edge 0.10 filtered; bet 2 edge 0.20 kept (lost)
        self.assertEqual(res["bets"], 1)
        self.assertAlmostEqual(res["roi"], -1.0)

    def test_edge_buckets(self):
        res = t2.simulate_flat_stake(self._rows(), threshold=0.05)
        self.assertEqual(res["edge_buckets"]["0.10-0.20"]["bets"], 1)
        self.assertEqual(res["edge_buckets"]["0.20+"]["bets"], 1)


def _two_league_matches(n_per_league=160):
    """League X has strong home advantage, league Y has none."""
    import random

    rng = random.Random(11)
    matches = []
    start = date(2024, 1, 1)
    for i in range(n_per_league):
        day = start + timedelta(days=i % 300)
        # X: home wins 80%
        hg, ag = (2, 0) if rng.random() < 0.8 else (0, 1)
        matches.append(MatchRecord(day, "XH", "XA", hg, ag, league="X"))
        # Y: home wins 40% (roughly balanced)
        hg, ag = (1, 0) if rng.random() < 0.4 else (0, 2)
        matches.append(MatchRecord(day + timedelta(days=1), "YH", "YA", hg, ag, league="Y"))
    return matches


class TestPerLeagueHA(unittest.TestCase):
    def test_per_league_ha_differs_and_global_fits_between(self):
        matches = _two_league_matches()
        asof = date(2025, 1, 1)
        global_model = fit_dc(matches, asof=asof, min_matches=5, max_sweeps=20)
        pl_model = fit_dc(matches, asof=asof, min_matches=5, max_sweeps=20, per_league_home_adv=True)
        self.assertIn("X", pl_model.home_adv_by_league)
        self.assertIn("Y", pl_model.home_adv_by_league)
        self.assertGreater(pl_model.home_adv_by_league["X"], pl_model.home_adv_by_league["Y"])
        # global HA sits between the two league-specific values
        self.assertLess(pl_model.home_adv_by_league["Y"], global_model.home_adv)
        self.assertGreater(pl_model.home_adv_by_league["X"], global_model.home_adv)
        # backward compat: default fit has empty by-league map
        self.assertEqual(global_model.home_adv_by_league, {})

    def test_league_weights_downweight(self):
        matches = _two_league_matches()
        asof = date(2025, 1, 1)
        base = fit_dc(matches, asof=asof, min_matches=5, max_sweeps=20)
        weighted = fit_dc(matches, asof=asof, min_matches=5, max_sweeps=20,
                          league_weights={"X": 0.25, "Y": 1.0})
        # down-weighting league X pulls its (strong) HA influence toward the
        # pooled/global value
        self.assertLess(weighted.home_adv, base.home_adv)
        # params remain finite and gauge-fixed
        self.assertTrue(all(math.isfinite(v) for v in weighted.attack.values()))
        mean_attack = sum(weighted.attack.values()) / len(weighted.attack)
        self.assertAlmostEqual(mean_attack, 0.0, places=8)

    def test_records_default_league_none_backward_compatible(self):
        m = MatchRecord(date(2024, 1, 1), "A", "B", 1, 0)
        self.assertIsNone(m.league)
