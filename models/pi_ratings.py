"""Pi-Ratings (Constantinou & Fenton, pi-ratings system) — Layer-2 afb-T2.

Sequential match-result rating system: every team carries a HOME rating and
an AWAY rating that evolve after each match.

Mechanism implemented (faithful to the published system; all constants are
configurable and data-tuned rather than copied from the paper, which fitted
them on its own dataset):

- Expected goal supremacy (home perspective):
      sup = h_i - a_j
  where h_i is the home rating of the home team and a_j the away rating of
  the away team (ratings live on a goal-difference scale, league average 0).
- After the match with observed supremacy y = home_goals - away_goals:
      delta = y - sup
      h_i <- h_i + kappa * omega * delta          (home team's home rating)
      a_i <- a_i + kappa * (1-omega) * delta      (home team's away rating)
      a_j <- a_j - kappa * omega * delta          (away team's away rating)
      h_j <- h_j - kappa * (1-omega) * delta      (away team's home rating)
  i.e. the playing-condition rating absorbs an `omega` share of the error and
  the other condition the remainder (symmetric for both teams).

Probabilities: supremacy -> Poisson goal means
      lambda_home = (mu_total + sup) / 2,  lambda_away = (mu_total - sup) / 2
(mu_total = expected total goals, as-of per league with shrinkage to global),
then a plain Poisson score matrix (no tau — pi-ratings has no DC correction).

Walk-forward by construction: predictions always use ratings as they stand
BEFORE the match; the update happens after. Zero leakage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models.dc_model import tau_corrected_matrix


@dataclass
class PiParams:
    kappa: float = 0.18          # overall learning rate
    omega_home: float = 0.75     # share of the error absorbed by the
                                 # playing-condition rating (home team's
                                 # home rating / away team's away rating)
    supremacy_cap: float = 2.2   # clamp on expected supremacy


@dataclass
class PiRatingModel:
    params: PiParams = field(default_factory=PiParams)
    home_r: Dict[str, float] = field(default_factory=dict)
    away_r: Dict[str, float] = field(default_factory=dict)
    n_matches: int = 0

    # ------------------------------------------------------------ ratings
    def ratings(self, team: str) -> Tuple[float, float]:
        return self.home_r.get(team, 0.0), self.away_r.get(team, 0.0)

    def expected_supremacy(self, home: str, away: str) -> float:
        h_i = self.home_r.get(home, 0.0)
        a_j = self.away_r.get(away, 0.0)
        return h_i - a_j

    # ------------------------------------------------------------ update
    def update(self, home: str, away: str, home_goals: int, away_goals: int) -> float:
        """Apply one match result; returns the prediction error (delta)."""
        sup = self.expected_supremacy(home, away)
        delta = float(home_goals) - float(away_goals) - sup
        k = self.params.kappa
        w = self.params.omega_home
        c = 1.0 - w
        self.home_r[home] = self.home_r.get(home, 0.0) + k * w * delta
        self.away_r[home] = self.away_r.get(home, 0.0) + k * c * delta
        self.away_r[away] = self.away_r.get(away, 0.0) - k * w * delta
        self.home_r[away] = self.home_r.get(away, 0.0) - k * c * delta
        self.n_matches += 1
        return delta

    # ------------------------------------------------------- probabilities
    def goal_means(
        self,
        home: str,
        away: str,
        mu_total: float,
        league: Optional[str] = None,
    ) -> Tuple[float, float]:
        d = self.expected_supremacy(home, away)
        cap = self.params.supremacy_cap
        d = max(-cap, min(cap, d))
        mu = mu_total
        lam_home = max(0.15, (mu + d) / 2.0)
        lam_away = max(0.15, (mu - d) / 2.0)
        return lam_home, lam_away

    def probs_1x2(
        self,
        home: str,
        away: str,
        mu_total: float,
        league: Optional[str] = None,
        max_goals: int = 10,
    ) -> Dict[str, float]:
        lam_h, lam_a = self.goal_means(home, away, mu_total, league)
        mat = tau_corrected_matrix(lam_h, lam_a, 0.0, max_goals=max_goals)
        home_w = draw = away_w = 0.0
        for x in range(len(mat)):
            row = mat[x]
            for y in range(len(row)):
                p = row[y]
                if x > y:
                    home_w += p
                elif x == y:
                    draw += p
                else:
                    away_w += p
        return {"Home": home_w, "Draw": draw, "Away": away_w}

    def score_matrix(self, home: str, away: str, mu_total: float, max_goals: int = 10) -> List[List[float]]:
        lam_h, lam_a = self.goal_means(home, away, mu_total)
        return tau_corrected_matrix(lam_h, lam_a, 0.0, max_goals=max_goals)


# ------------------------------------------------------------------- tuning


def supremacy_mae(
    model: PiRatingModel,
    matches: Sequence,  # MatchRecord-like: match_date/home/away/home_goals/away_goals
) -> float:
    """Sequential walk over matches; mean absolute supremacy error.

    Mutates the model (updates ratings) — caller passes a fresh model.
    """
    if not matches:
        return float("nan")
    total = 0.0
    for m in matches:
        sup = model.expected_supremacy(m.home, m.away)
        total += abs((m.home_goals - m.away_goals) - sup)
        model.update(m.home, m.away, m.home_goals, m.away_goals)
    return total / len(matches)


def tune_pi_params(
    matches: Sequence,
    kappas: Sequence[float] = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30),
    omegas: Sequence[float] = (0.5, 0.6, 0.7, 0.8, 0.9),
) -> Tuple[PiParams, dict]:
    """Grid-search (kappa, omega) on the training sequence by supremacy MAE.

    The whole training sequence is walked once per grid point (ratings are
    sequential, so tuning on train is leakage-free — val is untouched).
    Returns (best_params, report).
    """
    best: Optional[PiParams] = None
    best_mae = float("inf")
    report = {}
    for kappa in kappas:
        for omega in omegas:
            model = PiRatingModel(params=PiParams(kappa=kappa, omega_home=omega))
            mae = supremacy_mae(model, matches)
            report[f"k{kappa:g}_w{omega:g}"] = round(mae, 5)
            if mae < best_mae:
                best_mae, best = mae, PiParams(kappa=kappa, omega_home=omega)
    return best, {"best_mae": round(best_mae, 5), "grid": report}


# ----------------------------------------------------------- league mu_total


def league_mu_totals(
    matches: Sequence,
    asof: date,
    half_life_days: float = 365.0,
    shrink_matches: float = 50.0,
) -> Dict[str, float]:
    """As-of expected total goals per league (time-decayed, shrunk to global).

    Keys: league name -> mu_total; special key "" holds the global value.
    """
    from models.dc_model import decay_weight

    lg_num: Dict[str, float] = {}
    lg_den: Dict[str, float] = {}
    for m in matches:
        if m.match_date >= asof or m.home_goals is None or m.away_goals is None:
            continue
        age = (asof - m.match_date).days
        if age < 0:
            continue
        w = decay_weight(age, half_life_days)
        lg = (m.league or "") if hasattr(m, "league") else ""
        lg_num[lg] = lg_num.get(lg, 0.0) + w * (m.home_goals + m.away_goals)
        lg_den[lg] = lg_den.get(lg, 0.0) + w
    if not lg_den:
        return {"": 2.6}
    global_num = sum(lg_num.values())
    global_den = sum(lg_den.values())
    global_mu = global_num / global_den if global_den > 0 else 2.6
    out: Dict[str, float] = {"": round(global_mu, 6)}
    for lg, den in lg_den.items():
        if den <= 0:
            continue
        raw = lg_num[lg] / den
        shrink = den / (den + shrink_matches)
        out[lg] = round(shrink * raw + (1.0 - shrink) * global_mu, 6)
    return out


from datetime import date  # noqa: E402  (kept at bottom to preserve import order used above)

__all__ = [
    "PiParams",
    "PiRatingModel",
    "league_mu_totals",
    "supremacy_mae",
    "tune_pi_params",
]
