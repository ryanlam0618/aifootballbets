"""Hermetic unit tests for the Dixon-Coles model (models/dc_model.py).

No DB access (afbdb connection is pytest-guarded); all tests run on synthetic
data so CI stays deterministic.
"""

from __future__ import annotations

import math
import unittest
from datetime import date, timedelta

from models.dc_model import (
    DCModel,
    MatchRecord,
    ah_probs,
    decay_weight,
    fit_dc,
    tau_corrected_matrix,
    tau_factor,
)


def _pois(k: int, lam: float) -> float:
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


class TestDecayWeights(unittest.TestCase):
    def test_half_life_semantics(self):
        self.assertAlmostEqual(decay_weight(0, 365), 1.0, places=12)
        self.assertAlmostEqual(decay_weight(365, 365), 0.5, places=12)
        self.assertAlmostEqual(decay_weight(730, 365), 0.25, places=12)

    def test_monotone_decreasing(self):
        prev = 1.1
        for age in (0, 30, 90, 180, 365, 730, 1460):
            w = decay_weight(age, 365)
            self.assertLess(w, prev)
            prev = w

    def test_zero_half_life_disables_decay(self):
        self.assertEqual(decay_weight(1000, 0), 1.0)


class TestTauCorrection(unittest.TestCase):
    def test_tau_factor_values(self):
        lam = mu = 1.3
        rho = 0.05
        self.assertAlmostEqual(tau_factor(0, 0, lam, mu, rho), 1 - lam * mu * rho)
        self.assertAlmostEqual(tau_factor(0, 1, lam, mu, rho), 1 + lam * rho)
        self.assertAlmostEqual(tau_factor(1, 0, lam, mu, rho), 1 + mu * rho)
        self.assertAlmostEqual(tau_factor(1, 1, lam, mu, rho), 1 - rho)
        self.assertEqual(tau_factor(2, 2, lam, mu, rho), 1.0)
        self.assertEqual(tau_factor(3, 1, lam, mu, rho), 1.0)

    def test_rho_zero_equals_independent(self):
        lam, mu = 1.4, 1.1
        m_rho = tau_corrected_matrix(lam, mu, 0.0, max_goals=8)
        # with rho=0 the matrix is the raw product renormalised on the grid
        total = sum(
            _pois(x, lam) * _pois(y, mu) for x in range(9) for y in range(9)
        )
        for x in range(9):
            for y in range(9):
                self.assertAlmostEqual(
                    m_rho[x][y], _pois(x, lam) * _pois(y, mu) / total, places=12
                )

    def test_matrix_normalized(self):
        mat = tau_corrected_matrix(1.6, 1.2, -0.08, max_goals=10)
        self.assertAlmostEqual(sum(sum(r) for r in mat), 1.0, places=10)
        for row in mat:
            for v in row:
                self.assertGreaterEqual(v, 0.0)

    def test_negative_rho_increases_low_score_mass(self):
        # DC (1997): fitting typically shifts mass toward 0-0/1-1 relative to
        # independent Poisson when observed draws are more frequent.
        lam = mu = 1.3
        indep00 = _pois(0, lam) * _pois(0, mu)
        rho = -0.10
        mat = tau_corrected_matrix(lam, mu, rho, max_goals=10)
        # tau(0,0) = 1 - lam*mu*rho = 1 + 0.169 > 1 with rho<0, but after
        # renormalisation the 0-0 cell must still exceed the independent one
        # for this parameterisation (correction > renormalisation shrink).
        self.assertGreater(mat[0][0], indep00 * (1 - lam * mu * rho) / (1 - lam * mu * rho))
        self.assertGreater(mat[0][0], indep00)


class TestAsianHandicap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mat = tau_corrected_matrix(1.7, 1.1, -0.05, max_goals=10)

    def _sum(self, mat):
        return sum(sum(r) for r in mat)

    def test_half_line_home_plus_half_includes_draw(self):
        res = ah_probs(self.mat, 0.5)
        draw_p = sum(self.mat[x][x] for x in range(len(self.mat)))
        win_p = sum(
            self.mat[x][y] for x in range(len(self.mat)) for y in range(len(self.mat)) if x > y
        )
        self.assertAlmostEqual(res["home"]["win"], win_p + draw_p, places=10)
        self.assertEqual(res["home"]["push"], 0.0)
        self.assertAlmostEqual(res["home"]["eff"], win_p + draw_p, places=10)

    def test_half_line_home_minus_half_excludes_draw(self):
        res = ah_probs(self.mat, -0.5)
        win_p = sum(
            self.mat[x][y] for x in range(len(self.mat)) for y in range(len(self.mat)) if x > y
        )
        self.assertAlmostEqual(res["home"]["win"], win_p, places=10)
        self.assertAlmostEqual(res["home"]["fair_odds"], 1.0 / win_p, places=8)

    def test_sides_are_complementary(self):
        for line in (0.0, 0.25, 0.5, 0.75, 1.0):
            res = ah_probs(self.mat, line)
            self.assertAlmostEqual(res["home"]["eff"] + res["away"]["eff"], 1.0, places=10)
            self.assertAlmostEqual(res["home"]["push"], res["away"]["push"], places=10)

    def test_quarter_line_is_split_of_adjacent_lines(self):
        # home +0.25 == half stake on 0 and half on +0.5
        r0 = ah_probs(self.mat, 0.0)["home"]
        r05 = ah_probs(self.mat, 0.5)["home"]
        r025 = ah_probs(self.mat, 0.25)["home"]
        eff_expected = 0.5 * (r0["win"] + 0.5 * r0["push"]) + 0.5 * (r05["win"] + 0.5 * r05["push"])
        self.assertAlmostEqual(r025["eff"], eff_expected, places=10)
        fair_expected = (2 - r0["push"] - r05["push"]) / (r0["win"] + r05["win"])
        self.assertAlmostEqual(r025["fair_odds"], fair_expected, places=8)

    def test_quarter_line_075_split(self):
        r05 = ah_probs(self.mat, 0.5)["home"]
        r1 = ah_probs(self.mat, 1.0)["home"]
        r075 = ah_probs(self.mat, 0.75)["home"]
        eff_expected = 0.5 * (r05["win"] + 0.5 * r05["push"]) + 0.5 * (r1["win"] + 0.5 * r1["push"])
        self.assertAlmostEqual(r075["eff"], eff_expected, places=10)

    def test_probability_mass_partition(self):
        for line in (0.0, 0.25, 0.5, 0.75, 1.0):
            res = ah_probs(self.mat, line)
            for side in ("home", "away"):
                s = res[side]
                self.assertAlmostEqual(s["win"] + s["push"] + s["lose"], 1.0, places=10)


class TestFitting(unittest.TestCase):
    def _synthetic_matches(self, n_rounds=12, seed=42):
        """4-team double round-robin with known strengths, seeded RNG."""
        import random

        rng = random.Random(seed)
        teams = {"A": (1.9, 0.9), "B": (1.5, 1.1), "C": (1.2, 1.3), "D": (0.9, 1.7)}
        matches = []
        day0 = date(2025, 1, 1)
        for r in range(n_rounds):
            day = day0 + timedelta(days=7 * r)
            pairs = [("A", "B"), ("C", "D")] if r % 2 == 0 else [("A", "C"), ("B", "D")]
            other = [("A", "D"), ("B", "C")] if r % 2 == 0 else [("A", "B"), ("C", "D")]
            for h, a in pairs + other:
                lam = teams[h][0] * teams[a][1] * 1.15
                mu = teams[a][0] * teams[h][1]
                hg = min(9, _sample_poisson(rng, lam))
                ag = min(9, _sample_poisson(rng, mu))
                matches.append(MatchRecord(day, h, a, hg, ag))
                matches.append(MatchRecord(day + timedelta(days=1), a, h, min(9, _sample_poisson(rng, teams[a][0] * teams[h][1] * 1.15)), min(9, _sample_poisson(rng, teams[h][0] * teams[a][1]))))
        return matches

    def test_fit_recovers_strength_ordering(self):
        matches = self._synthetic_matches()
        asof = date(2025, 6, 1)
        model = fit_dc(matches, asof=asof, half_life_days=400.0, min_matches=8, max_sweeps=30)
        self.assertEqual(model.n_teams, 4)
        # A strongest attack, D weakest (gauged: compare relative to others)
        self.assertGreater(model.attack["A"], model.attack["B"])
        self.assertGreater(model.attack["B"], model.attack["C"])
        self.assertGreater(model.attack["C"], model.attack["D"])
        # home advantage positive (synthetic data has 1.15 home boost)
        self.assertGreater(model.home_adv, 0.0)
        # rho within feasible range
        self.assertGreaterEqual(model.rho, -0.15)
        self.assertLessEqual(model.rho, 0.10)

    def test_fit_predictions_sum_to_one(self):
        matches = self._synthetic_matches(n_rounds=10)
        model = fit_dc(matches, asof=date(2025, 6, 1), min_matches=8)
        probs = model.probs_1x2("A", "D")
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=8)
        rows = model.predict_markets("A", "D")
        by_market = {}
        for r in rows:
            by_market.setdefault((r["market"], r["line"]), []).append(r["model_probability"])
        for (market, _line), plist in by_market.items():
            if market == "1X2":
                self.assertAlmostEqual(sum(plist), 1.0, places=8)
            else:
                # AH: Home(eff) + Away(eff) == 1 (complementary sides)
                self.assertAlmostEqual(sum(plist), 1.0, places=8)
        # 13 rows: 3 (1X2) + 5 lines x 2 sides
        self.assertEqual(len(rows), 13)

    def test_min_matches_pins_weak_teams_neutral(self):
        matches = self._synthetic_matches(n_rounds=12)
        # add a team with very few matches
        matches.append(MatchRecord(date(2025, 5, 1), "A", "Z", 2, 0))
        matches.append(MatchRecord(date(2025, 5, 2), "Z", "A", 0, 3))
        model = fit_dc(matches, asof=date(2025, 6, 1), min_matches=8)
        self.assertEqual(model.attack.get("Z", 0.0), 0.0)
        self.assertEqual(model.defense.get("Z", 0.0), 0.0)

    def test_gauge_mean_attack_zero(self):
        matches = self._synthetic_matches()
        model = fit_dc(matches, asof=date(2025, 6, 1), min_matches=8)
        mean_attack = sum(model.attack.values()) / len(model.attack)
        self.assertAlmostEqual(mean_attack, 0.0, places=8)

    def test_asof_excludes_future_matches(self):
        matches = self._synthetic_matches(n_rounds=12)
        asof = date(2025, 2, 1)  # ~4 rounds in
        model = fit_dc(matches, asof=asof, min_matches=4)
        self.assertEqual(model.n_matches, sum(1 for m in matches if m.match_date < asof))

    def test_fit_rho_improves_draw_calibration_on_draw_heavy_data(self):
        # generate draw-heavy low-scoring data; fitted rho should be feasible
        # and the tau matrix should assign more mass to 0-0/1-1 than rho=0
        import random

        rng = random.Random(7)
        matches = []
        day0 = date(2024, 1, 1)
        for i in range(400):
            day = day0 + timedelta(days=i % 300)
            h, a = ("A", "B") if i % 2 == 0 else ("B", "A")
            # draw-heavy: sample from a distribution with extra 0-0/1-1 mass
            u = rng.random()
            if u < 0.35:
                hg, ag = 0, 0
            elif u < 0.60:
                hg, ag = 1, 1
            else:
                hg, ag = rng.randint(0, 4), rng.randint(0, 4)
                if hg == ag:
                    ag = (ag + 1) % 5
            matches.append(MatchRecord(day, h, a, hg, ag))
        model = fit_dc(matches, asof=date(2025, 1, 1), min_matches=2)
        self.assertLessEqual(model.rho, 0.10)
        mat = model.score_matrix("A", "B")
        mat0 = tau_corrected_matrix(*model._params("A", "B"), 0.0, max_goals=10)
        # draw-heavy data -> corrected matrix should hold more low-draw mass
        low_draw = mat[0][0] + mat[1][1]
        low_draw0 = mat0[0][0] + mat0[1][1]
        self.assertGreater(low_draw, low_draw0)


def _sample_poisson(rng, lam: float, cap: int = 12) -> int:
    """Knuth's small-lambda Poisson sampler (deterministic via rng)."""
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        p *= rng.random()
        if p <= L or k >= cap:
            return k
        k += 1


if __name__ == "__main__":
    unittest.main()
