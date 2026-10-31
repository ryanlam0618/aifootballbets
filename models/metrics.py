"""Shared evaluation metrics for the Layer-2 models (1X2).

- rps_1x2: Ranked Probability Score for the ordered outcome Home < Draw < Away
  (the metric required by the afb-T2 acceptance criteria).
- brier_1x2: multi-class Brier score (mean over the three selections).
- ece_1x2: Expected Calibration Error from equal-width probability buckets
  (pairs of (predicted probability, realised indicator)).

Pure stdlib.
"""

from __future__ import annotations

import math
from typing import Dict, Sequence

OUTCOMES = ("Home", "Draw", "Away")


def rps_1x2(probs: Dict[str, float], outcome: str) -> float:
    """Ranked Probability Score; lower is better.

    rps = (1/2) * sum_{i=1..2} (CDF_model(i) - CDF_obs(i))^2
    with the ordered classes Home < Draw < Away.
    """
    p_home = float(probs.get("Home", 0.0))
    p_draw = float(probs.get("Draw", 0.0))
    cdf_m = (p_home, p_home + p_draw)
    cdf_o = (
        1.0 if outcome == "Home" else 0.0,
        1.0 if outcome in ("Home", "Draw") else 0.0,
    )
    return 0.5 * ((cdf_m[0] - cdf_o[0]) ** 2 + (cdf_m[1] - cdf_o[1]) ** 2)


def mean_rps_1x2(prob_rows: Sequence[Dict[str, float]], outcomes: Sequence[str]) -> float:
    if not outcomes:
        return float("nan")
    return sum(rps_1x2(p, o) for p, o in zip(prob_rows, outcomes)) / len(outcomes)


def brier_1x2(probs: Dict[str, float], outcome: str) -> float:
    """Multi-class Brier score: mean squared error over the three selections."""
    total = 0.0
    for sel in OUTCOMES:
        target = 1.0 if outcome == sel else 0.0
        total += (float(probs.get(sel, 0.0)) - target) ** 2
    return total / len(OUTCOMES)


def mean_brier_1x2(prob_rows: Sequence[Dict[str, float]], outcomes: Sequence[str]) -> float:
    if not outcomes:
        return float("nan")
    return sum(brier_1x2(p, o) for p, o in zip(prob_rows, outcomes)) / len(outcomes)


def ece_1x2(pairs: Sequence[Tuple], n_buckets: int = 10) -> float:
    """Expected Calibration Error: sum over buckets of (n/N)*|mean_pred - realised|.

    `pairs` are (predicted_probability, realised_indicator) as produced by the
    backtest scoring helpers.
    """
    if not pairs:
        return float("nan")
    width = 1.0 / n_buckets
    n_total = len(pairs)
    ece = 0.0
    for b in range(n_buckets):
        lo, hi = b * width, (b + 1) * width
        members = [(p, r) for p, r in pairs if (lo <= p < hi) or (b == n_buckets - 1 and p == 1.0)]
        if not members:
            continue
        mean_pred = sum(p for p, _ in members) / len(members)
        realised = sum(r for _, r in members) / len(members)
        ece += (len(members) / n_total) * abs(mean_pred - realised)
    return ece


__all__ = ["brier_1x2", "ece_1x2", "mean_brier_1x2", "mean_rps_1x2", "rps_1x2"]
