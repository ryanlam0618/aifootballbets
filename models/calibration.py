"""Probability calibration for the DC model (Layer-2 T2 ①).

Pure-stdlib implementations:

- isotonic regression (PAVA — pool adjacent violators) per class, with
  renormalisation across the 1X2 trio;
- temperature scaling on the 3-class probability vector (logit/T then
  softmax), fitted by minimising multi-class log-loss on a calibration
  window;
- grouped variants (e.g. cup vs league vs continental) fitted separately.

All fitters are as-of friendly: they are fitted on a calibration window that
strictly precedes the evaluation window (zero leakage is the caller's
responsibility, enforced in scripts/backtest_t2.py).
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple


# ------------------------------------------------------------- isotonic/PAVA


def isotonic_pava(pairs: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Fit a monotone non-decreasing step function to (x, y) pairs (unit weights).

    Returns breakpoints [(x, y_fitted)] sorted by x; prediction looks up the
    last breakpoint with x_query >= x.
    """
    if not pairs:
        return []
    pts = sorted((float(x), float(y)) for x, y in pairs)
    # stack of (x, y, weight)
    blocks: List[List[float]] = []
    for x, y in pts:
        blocks.append([x, y, 1.0])
        while len(blocks) >= 2 and blocks[-2][1] > blocks[-1][1] + 1e-15:
            x2, y2, w2 = blocks.pop()
            x1, y1, w1 = blocks.pop()
            w = w1 + w2
            blocks.append([x2, (y1 * w1 + y2 * w2) / w, w])
    return [(x, y) for x, y, _ in blocks]


def isotonic_predict(breakpoints: Sequence[Tuple[float, float]], x: float) -> float:
    """Evaluate the PAVA step function at x (clamps outside the range)."""
    if not breakpoints:
        return x
    lo, hi = breakpoints[0][0], breakpoints[-1][0]
    if x <= lo:
        return breakpoints[0][1]
    if x >= hi:
        return breakpoints[-1][1]
    y = breakpoints[0][1]
    for bx, by in breakpoints:
        if x >= bx:
            y = by
        else:
            break
    return y


def fit_isotonic_1x2(
    prob_rows: Sequence[Dict[str, float]],
    outcomes: Sequence[str],
) -> Dict[str, List[Tuple[float, float]]]:
    """Per-class isotonic maps for 1X2 (selection -> PAVA breakpoints)."""
    if len(prob_rows) != len(outcomes):
        raise ValueError("prob_rows/outcomes length mismatch")
    maps: Dict[str, List[Tuple[float, float]]] = {}
    for sel in ("Home", "Draw", "Away"):
        pairs = [(row[sel], 1.0 if out == sel else 0.0) for row, out in zip(prob_rows, outcomes)]
        maps[sel] = isotonic_pava(pairs)
    return maps


def apply_isotonic_1x2(
    maps: Dict[str, List[Tuple[float, float]]],
    row: Dict[str, float],
) -> Dict[str, float]:
    """Apply per-class isotonic maps then renormalise the trio to sum 1."""
    raw = {sel: isotonic_predict(maps.get(sel, []), row[sel]) for sel in ("Home", "Draw", "Away")}
    total = sum(raw.values())
    if total <= 0:
        # degenerate maps: fall back to uniform
        return {"Home": 1 / 3, "Draw": 1 / 3, "Away": 1 / 3}
    return {sel: v / total for sel, v in raw.items()}


# ---------------------------------------------------------------- temperature


def apply_temperature(probs: Dict[str, float], temperature: float) -> Dict[str, float]:
    """Softmax(log(p)/T), renormalised. T > 1 flattens, T < 1 sharpens."""
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    logs = {sel: math.log(max(float(v), 1e-12)) / temperature for sel, v in probs.items()}
    peak = max(logs.values())
    exps = {sel: math.exp(z - peak) for sel, z in logs.items()}
    total = sum(exps.values())
    return {sel: v / total for sel, v in exps.items()}


def nll_1x2(prob_rows: Sequence[Dict[str, float]], outcomes: Sequence[str], eps: float = 1e-12) -> float:
    if not outcomes:
        return float("nan")
    total = 0.0
    for row, out in zip(prob_rows, outcomes):
        total -= math.log(max(float(row[out]), eps))
    return total / len(outcomes)


def fit_temperature_1x2(
    prob_rows: Sequence[Dict[str, float]],
    outcomes: Sequence[str],
    t_min: float = 0.25,
    t_max: float = 4.0,
    steps: int = 76,
) -> Tuple[float, float]:
    """Grid + refinement search for the temperature minimising log-loss.

    Returns (best_T, nll_at_best_T).
    """
    if not prob_rows:
        raise ValueError("no calibration rows")
    grid = [t_min + (t_max - t_min) * i / (steps - 1) for i in range(steps)]
    best_t, best_ll = 1.0, float("inf")
    for t in grid:
        ll = nll_1x2([apply_temperature(r, t) for r in prob_rows], outcomes)
        if ll < best_ll:
            best_t, best_ll = t, ll
    # local refinement around the best grid point
    step = grid[1] - grid[0]
    for t in (best_t - step, best_t + step, best_t - step / 2, best_t + step / 2):
        if t_min <= t <= t_max:
            ll = nll_1x2([apply_temperature(r, t) for r in prob_rows], outcomes)
            if ll < best_ll:
                best_t, best_ll = t, ll
    return best_t, best_ll


def fit_grouped_temperature_1x2(
    prob_rows: Sequence[Dict[str, float]],
    outcomes: Sequence[str],
    groups: Sequence[str],
) -> Dict[str, Tuple[float, float]]:
    """Fit one temperature per group (e.g. cup / league / continental)."""
    out: Dict[str, Tuple[float, float]] = {}
    for g in sorted(set(groups)):
        rows = [r for r, gg in zip(prob_rows, groups) if gg == g]
        outs = [o for o, gg in zip(outcomes, groups) if gg == g]
        if rows:
            out[g] = fit_temperature_1x2(rows, outs)
    return out


def apply_grouped_temperature(
    prob_rows: Sequence[Dict[str, float]],
    groups: Sequence[str],
    fitted: Dict[str, Tuple[float, float]],
    default_t: float = 1.0,
) -> List[Dict[str, float]]:
    """Apply group-specific temperatures; unknown groups use default_t."""
    out: List[Dict[str, float]] = []
    for row, g in zip(prob_rows, groups):
        t = fitted.get(g, (default_t, float("nan")))[0]
        out.append(apply_temperature(row, t))
    return out


def cup_vs_league_group(league_name: str) -> str:
    """Classify a competition name into cup / league / continental."""
    name = (league_name or "").strip()
    cups = {
        "FA Cup", "Copa del Rey", "Coppa Italia", "Coupe de France", "DFB Pokal",
        "EFL Cup", "Emperor's Cup", "J.League Cup", "Australia Cup", "Chinese FA Cup",
    }
    if name in cups:
        return "cup"
    if name in {"UCL", "UEL", "UECL", "AFC Champions League", "AFC Champions League Two"}:
        return "continental"
    return "league"


__all__ = [
    "apply_grouped_temperature",
    "apply_isotonic_1x2",
    "apply_temperature",
    "cup_vs_league_group",
    "fit_grouped_temperature_1x2",
    "fit_isotonic_1x2",
    "fit_temperature_1x2",
    "isotonic_pava",
    "isotonic_predict",
    "nll_1x2",
]
