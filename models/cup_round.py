"""Cup round home-advantage adjustment (Layer-2 afb-T1.3, 平玩版).

T2 ③ found that cups have systematically higher home advantage than leagues
(Emperor's Cup +0.518, EFL Cup +0.409, ... vs leagues ~+0.25). The 平玩版
adds a ROUND-level adjustment on top of the per-league home advantage —
NOT separate attack/defence fits (進取版 deliberately excluded: overfitting
risk).

Mechanism:
- Round names from `matches.round_name` are bucketed into
  {early, middle, late, final} by keyword (see round_bucket()).
- For each bucket b, an additive home-advantage adjustment delta_b is fitted
  on TRAINING cup matches only:
      delta_b = shrink * ln( sum(w * observed_home_goals) / sum(w * expected_home_mean) )
  i.e. the log-ratio of observed vs model-expected home goals, shrunk toward
  0 by bucket size (shrink_matches pseudo-matches).
- Prediction wraps a fitted DCModel: for cup matches the home goal mean is
  multiplied by exp(delta_b); the away mean is untouched. Non-cup matches
  pass through unchanged.

Walk-forward: the adjustment is fitted strictly on pre-validation matches
(single as-of fit — equivalent to a one-window walk-forward).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from models.dc_model import DCModel, decay_weight

ROUND_BUCKETS = ("early", "middle", "late", "final")


def round_bucket(round_name: Optional[str]) -> str:
    """Map a raw round name to {early, middle, late, final} (default middle)."""
    s = (round_name or "").strip().lower()
    if not s:
        return "middle"
    # order matters: "quarter-finals"/"semi-finals" contain "final" as a
    # substring — classify them before the final check
    if "semi" in s:
        return "late"
    if "quarter" in s or "round of 16" in s or "4th round" in s or "5th round" in s:
        return "late"
    if s == "final" or (s.endswith("final") and "qualif" not in s):
        return "final"
    if "1st" in s or "2nd" in s or "3rd" in s or "qualif" in s or "group" in s or "first" in s or "prelim" in s:
        return "early"
    return "middle"


def is_cup(league_name: Optional[str], cup_leagues: set) -> bool:
    return (league_name or "") in cup_leagues


@dataclass
class CupRoundModel:
    """Wrapper over a fitted DCModel applying cup-round HA adjustments."""

    base: DCModel
    deltas: Dict[str, float] = field(default_factory=dict)  # bucket -> delta (log multiplier)
    cup_leagues: set = field(default_factory=set)
    n_train_cup: int = 0

    def _params(self, home: str, away: str, league: Optional[str]) -> Tuple[float, float]:
        return self.base._params(home, away, league)

    def score_matrix(
        self,
        home: str,
        away: str,
        max_goals: int = 10,
        league: Optional[str] = None,
        round_name: Optional[str] = None,
    ) -> List[List[float]]:
        lam_h, lam_a = self._params(home, away, league)
        if league in self.cup_leagues and round_name is not None:
            b = round_bucket(round_name)
            delta = self.deltas.get(b, 0.0)
            lam_h = lam_h * math.exp(delta)
        from models.dc_model import tau_corrected_matrix

        return tau_corrected_matrix(lam_h, lam_a, self.base.rho, max_goals=max_goals)

    def probs_1x2(
        self,
        home: str,
        away: str,
        max_goals: int = 10,
        league: Optional[str] = None,
        round_name: Optional[str] = None,
    ) -> Dict[str, float]:
        mat = self.score_matrix(home, away, max_goals=max_goals, league=league, round_name=round_name)
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


def fit_cup_round_adjustment(
    base: DCModel,
    train_matches: Sequence[dict],
    cup_leagues: set,
    half_life_days: float = 365.0,
    shrink_matches: float = 300.0,
    asof: Optional[date] = None,
) -> Tuple[CupRoundModel, dict]:
    """Fit the per-bucket home-goal log-multiplier on training cup matches.

    delta_b = shrink * ln( sum(w * observed_home_goals) / sum(w * model_home_mean) )
    (shrunk toward 0; as-of boundary — training data only, zero leakage).
    """
    from datetime import date as _date

    num: Dict[str, float] = {}
    den: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    n_cup = 0
    for m in train_matches:
        lg = m.get("league") or ""
        if lg not in cup_leagues:
            continue
        if asof is not None and m["match_date"] >= asof:
            continue
        n_cup += 1
        bucket = round_bucket(m.get("round_name"))
        lam_h, _ = base._params(m["home"], m["away"], lg)
        age_days = 0
        # weight: recency decay from the latest training date
        w = 1.0
        if asof is not None:
            from models.dc_model import decay_weight as _dw

            w = _dw(max(0, (asof - m["match_date"]).days), half_life_days)
        num[bucket] = num.get(bucket, 0.0) + w * m["home_goals"]
        den[bucket] = den.get(bucket, 0.0) + w * lam_h
        counts[bucket] = counts.get(bucket, 0) + 1

    deltas: Dict[str, float] = {}
    detail: Dict[str, dict] = {}
    for b in ROUND_BUCKETS:
        n_b = counts.get(b, 0)
        if den.get(b, 0.0) > 0 and num.get(b, 0.0) > 0:
            raw = math.log(num[b] / den[b])
            shrink = n_b / (n_b + max(1.0, shrink_matches))
            deltas[b] = round(shrink * raw, 4)
        else:
            deltas[b] = 0.0
        detail[b] = {"n": n_b, "delta": deltas[b]}
    wrapped = CupRoundModel(base=base, deltas=deltas, cup_leagues=set(cup_leagues), n_train_cup=n_cup)
    return wrapped, {"n_train_cup": n_cup, "buckets": detail}


__all__ = [
    "CupRoundModel",
    "ROUND_BUCKETS",
    "fit_cup_round_adjustment",
    "is_cup",
    "round_bucket",
]
