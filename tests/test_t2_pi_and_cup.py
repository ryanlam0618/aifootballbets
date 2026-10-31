"""Hermetic tests for afb-T2 Pi-Ratings and afb-T1.3 cup round adjustment."""

from __future__ import annotations

import math
import random
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from models.cup_round import fit_cup_round_adjustment, round_bucket  # noqa: E402
from models.dc_model import fit_dc  # noqa: E402
from models.metrics import rps_1x2  # noqa: E402
from scripts.backtest_dc import to_match_records  # noqa: E402
from models.pi_ratings import (  # noqa: E402
    PiParams,
    PiRatingModel,
    league_mu_totals,
    tune_pi_params,
)


def _pois(rng, lam, cap=10):
    L = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= L or k >= cap:
            return k
        k += 1


class _Match:
    def __init__(self, match_date, home, away, home_goals, away_goals, league=None):
        self.match_date = match_date
        self.home = home
        self.away = away
        self.home_goals = home_goals
        self.away_goals = away_goals
        self.league = league


def _synthetic_pi(n=400, seed=3):
    """Sequential matches where team A is strong."""
    rng = random.Random(seed)
    matches = []
    start = date(2024, 1, 1)
    pairs = [("A", "B"), ("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"), ("C", "D")]
    for i in range(n):
        day = start + timedelta(days=i % 300)
        h, a = pairs[i % len(pairs)]
        boost = 0.5 if h == "A" else 0.0
        matches.append(
            _Match(
                day, h, a,
                min(7, _pois(rng, 1.4 + boost)),
                min(7, _pois(rng, 1.0)),
                league="L",
            )
        )
    return matches


class TestPiRatings(unittest.TestCase):
    def test_update_direction(self):
        model = PiRatingModel(params=PiParams(kappa=0.2, omega_home=0.75))
        h0 = model.home_r.get("A", 0.0)
        model.update("A", "B", 3, 0)  # A wins big at home
        self.assertGreater(model.home_r["A"], h0)
        self.assertLess(model.away_r["B"], model.home_r.get("B", 0.0))

    def test_expected_supremacy_sign(self):
        model = PiRatingModel(params=PiParams(kappa=0.2, omega_home=0.75))
        for _ in range(30):
            model.update("A", "D", 3, 0)
        self.assertGreater(model.expected_supremacy("A", "D"), 0.0)
        self.assertLess(model.expected_supremacy("D", "A"), 0.0)

    def test_probs_sum_to_one_and_sane(self):
        model = PiRatingModel(params=PiParams(kappa=0.2, omega_home=0.75))
        for i in range(50):
            model.update("A", "B", 2, 1)
        probs = model.probs_1x2("A", "B", mu_total=2.6)
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=10)
        self.assertTrue(all(v >= 0 for v in probs.values()))

    def test_tuning_picks_sane_params(self):
        matches = _synthetic_pi()
        params, report = tune_pi_params(matches[:300], kappas=(0.05, 0.2), omegas=(0.5, 0.9))
        self.assertIn(params.kappa, (0.05, 0.2))
        self.assertIn(params.omega_home, (0.5, 0.9))
        self.assertTrue(math.isfinite(report["best_mae"]))

    def test_league_mu_totals_shrinkage(self):
        matches = [
            _Match(date(2024, 1, 1), "A", "B", 3, 0, league="High"),
            _Match(date(2024, 1, 2), "A", "B", 2, 1, league="High"),
            # other leagues with lower totals -> global mean below High's raw mean
            _Match(date(2024, 1, 3), "C", "D", 0, 0, league="Other"),
            _Match(date(2024, 1, 4), "C", "D", 1, 0, league="Other"),
            _Match(date(2024, 1, 5), "C", "D", 0, 1, league="Other"),
        ]
        mu = league_mu_totals(matches, asof=date(2024, 6, 1))
        self.assertIn("", mu)
        # High raw mean 3.0, global lower -> shrunk value between the two
        self.assertGreater(mu["High"], mu[""])
        self.assertLess(mu["High"], 3.0)


class TestRPS(unittest.TestCase):
    def test_known_values(self):
        self.assertAlmostEqual(rps_1x2({"Home": 1.0, "Draw": 0.0, "Away": 0.0}, "Home"), 0.0)
        # certain + wrong = maximum RPS 1.0 for 3 classes
        self.assertAlmostEqual(rps_1x2({"Home": 1.0, "Draw": 0.0, "Away": 0.0}, "Away"), 1.0)
        u = {"Home": 1 / 3, "Draw": 1 / 3, "Away": 1 / 3}
        self.assertAlmostEqual(rps_1x2(u, "Home"), ((1 / 3 - 1) ** 2 + (2 / 3 - 1) ** 2) / 2, places=10)

    def test_ordering(self):
        self.assertLess(
            rps_1x2({"Home": 0.6, "Draw": 0.25, "Away": 0.15}, "Home"),
            rps_1x2({"Home": 0.15, "Draw": 0.25, "Away": 0.6}, "Home"),
        )


class TestCupRound(unittest.TestCase):
    def test_bucket_parsing(self):
        self.assertEqual(round_bucket("Final"), "final")
        self.assertEqual(round_bucket("Semi-finals"), "late")
        self.assertEqual(round_bucket("Quarter-finals"), "late")
        self.assertEqual(round_bucket("Round of 16"), "late")
        self.assertEqual(round_bucket("5th Round"), "late")
        self.assertEqual(round_bucket("1st Round"), "early")
        self.assertEqual(round_bucket("Qualifying Round"), "early")
        self.assertEqual(round_bucket("Group Stage"), "early")
        self.assertEqual(round_bucket(None), "middle")
        self.assertEqual(round_bucket("Some odd name"), "middle")

    def _dict_matches(self):
        rng = random.Random(9)
        out = []
        start = date(2024, 1, 1)
        for i in range(300):
            league = "FA Cup" if i % 2 == 0 else "Premier League"
            is_final = league == "FA Cup" and i % 10 == 0
            out.append(
                {
                    "match_date": start + timedelta(days=i),
                    "home": f"H{i % 20}",
                    "away": f"A{i % 20}",
                    "league": league,
                    "round_name": "Final" if is_final else "1st Round",
                    "home_goals": 0 if is_final else 2,
                    "away_goals": 1,
                    "match_id": str(i),
                }
            )
        return out

    def test_cup_round_adjustment_normalised(self):
        dict_matches = self._dict_matches()
        boundary = date(2024, 12, 1)
        train = [m for m in dict_matches if m["match_date"] < boundary]
        base = fit_dc(to_match_records(train), asof=boundary, min_matches=3, max_sweeps=15)
        wrapped, detail = fit_cup_round_adjustment(
            base, train, {"FA Cup", "Premier League"}, asof=boundary, shrink_matches=50
        )
        self.assertIn("final", detail["buckets"])
        probs = wrapped.probs_1x2("H0", "A0", league="FA Cup", round_name="Final")
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=10)
        self.assertTrue(all(v >= 0 for v in probs.values()))

    def test_non_cup_passthrough(self):
        matches = [
            {
                "match_date": date(2024, 1, 1) + timedelta(days=i),
                "home": f"H{i % 10}", "away": f"A{i % 10}",
                "league": "Premier League", "round_name": None,
                "home_goals": 1, "away_goals": 1, "match_id": str(i),
            }
            for i in range(120)
        ]
        boundary = date(2024, 12, 1)
        base = fit_dc(to_match_records(matches), asof=boundary, min_matches=3, max_sweeps=15)
        wrapped, detail = fit_cup_round_adjustment(base, matches, {"FA Cup"}, asof=boundary)
        self.assertEqual(wrapped.n_train_cup, 0)
        self.assertTrue(all(v == 0.0 for v in wrapped.deltas.values()))
        p1 = base.probs_1x2("H0", "A1", league="Premier League")
        p2 = wrapped.probs_1x2("H0", "A1", league="Premier League", round_name="Final")
        for sel in p1:
            self.assertAlmostEqual(p1[sel], p2[sel], places=10)


if __name__ == "__main__":
    unittest.main()
