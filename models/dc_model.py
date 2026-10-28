"""Dixon-Coles (1997) model with tau low-score correction, exponential time
decay, and Asian Handicap quarter-line pricing.

Model (log-linear parameterisation):
    lambda_home = exp(attack_home + defense_away + home_adv)
    lambda_away = exp(attack_away + defense_home)

tau correction (Dixon & Coles 1997, JRSS-C):
    tau(0,0) = 1 - lambda*mu*rho
    tau(0,1) = 1 + lambda*rho
    tau(1,0) = 1 + mu*rho
    tau(1,1) = 1 - rho
    tau(x,y) = 1 otherwise

Time decay (the 1997 paper uses (1-xi)^t; the standard practical equivalent
used here is exponential with a half-life, xi = ln(2)/half_life_days):
    weight(match) = exp(-ln(2) * age_days / half_life_days)

AH settlement semantics used throughout:
- a line L on the HOME side means home receives L goals: home wins when
  x + L > y, pushes when x + L == y (integer lines only);
- the away side of the SAME market wins exactly when the home side loses,
  pushes when the home side pushes -> eff_away = 1 - eff_home;
- quarter lines (0.25/0.75) are settled as equal splits of the two adjacent
  lines: eff = 0.5*(w1 + p1/2) + 0.5*(w2 + p2/2);
- fair odds: half line f = 1/win; quarter line f = (1 - push)/win with the
  split-aggregated (win, push).

Fitting: coordinate-ascent MLE with closed-form per-team updates (Poisson
parts) + in-sweep 1-D grid search for rho (tau part). Gauge is fixed each
sweep (mean(attack) = 0). Teams below `min_matches` in the window are pinned
at the neutral prior (attack = defense = 0) but their matches still
contribute to opponents' estimates.

Pure-Python + stdlib only (no numpy), so it runs anywhere the paper pipeline
runs. DB I/O lives in scripts/run_dc_predictions.py, not here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

LN2 = math.log(2.0)

SUPPORTED_AH_LINES = (0.0, 0.25, 0.5, 0.75, 1.0)


# ---------------------------------------------------------------- decay


def decay_weight(age_days: float, half_life_days: float) -> float:
    """Exponential time-decay weight; equals 0.5 at age == half_life."""
    if half_life_days <= 0:
        return 1.0
    return math.exp(-LN2 * float(age_days) / float(half_life_days))


# ------------------------------------------------------------------- tau


def tau_factor(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Dixon-Coles low-score correction factor for score cell (x, y)."""
    if rho == 0.0:
        return 1.0
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _pois_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


def tau_corrected_matrix(
    lam: float,
    mu: float,
    rho: float,
    max_goals: int = 10,
) -> List[List[float]]:
    """Tau-corrected, renormalised score matrix P(x=home goals, y=away goals)."""
    mat = [[0.0] * (max_goals + 1) for _ in range(max_goals + 1)]
    total = 0.0
    for x in range(max_goals + 1):
        px = _pois_pmf(x, lam)
        if px == 0.0:
            continue
        row = mat[x]
        for y in range(max_goals + 1):
            v = px * _pois_pmf(y, mu) * tau_factor(x, y, lam, mu, rho)
            if v < 0.0:
                v = 0.0
            row[y] = v
            total += v
    if total > 0:
        inv = 1.0 / total
        for x in range(max_goals + 1):
            row = mat[x]
            for y in range(max_goals + 1):
                row[y] *= inv
    return mat


# --------------------------------------------------------------- AH pricing


def _single_line_outcome(mat: Sequence[Sequence[float]], line: float) -> Tuple[float, float, float]:
    """(win, push, lose) for `home + line` from the home perspective."""
    if line == int(line):
        li = int(line)
        win = push = lose = 0.0
        for x in range(len(mat)):
            row = mat[x]
            for y in range(len(row)):
                d = x + li - y
                p = row[y]
                if d > 0:
                    win += p
                elif d == 0:
                    push += p
                else:
                    lose += p
        return win, push, lose
    # half line: no push possible
    base = int(math.floor(line))
    frac = line - base  # 0.5
    win = lose = 0.0
    for x in range(len(mat)):
        row = mat[x]
        for y in range(len(row)):
            if x + base + frac > y:
                win += row[y]
            else:
                lose += row[y]
    return win, 0.0, lose


def _ah_side(mat: Sequence[Sequence[float]], home_line: float) -> dict:
    """Price the HOME side of `home + home_line`; quarter lines are splits."""
    q = round(home_line * 4)
    if abs(home_line * 4 - q) > 1e-9 or q % 2 != 0 and abs(q) > 4:
        raise ValueError(f"unsupported AH line: {home_line}")

    if q % 2 == 0:  # integer or half line: single line settlement
        win, push, lose = _single_line_outcome(mat, home_line)
        eff = win + 0.5 * push
    else:  # quarter line: equal split of the two adjacent lines
        if q > 0:
            l1, l2 = (q - 1) / 4.0, (q + 1) / 4.0
        else:
            l1, l2 = (q + 1) / 4.0, (q - 1) / 4.0
        w1, p1, _ = _single_line_outcome(mat, l1)
        w2, p2, _ = _single_line_outcome(mat, l2)
        win = 0.5 * (w1 + w2)
        push = 0.5 * (p1 + p2)
        lose = 1.0 - win - push
        eff = 0.5 * (w1 + 0.5 * p1) + 0.5 * (w2 + 0.5 * p2)

    fair = None
    if win > 1e-12:
        fair = (1.0 - push) / win
    return {"win": win, "push": push, "lose": lose, "eff": eff, "fair_odds": fair}


def ah_probs(mat: Sequence[Sequence[float]], home_line: float) -> dict:
    """Price both sides of the AH market whose HOME line is `home_line`.

    Returns {"home": {...}, "away": {...}}; the away side of the same market
    wins exactly when the home side loses (push in common), hence
    eff_away = 1 - eff_home.
    """
    home = _ah_side(mat, home_line)
    away = {
        "win": home["lose"],
        "push": home["push"],
        "lose": home["win"],
        "eff": 1.0 - home["eff"],
        "fair_odds": None,
    }
    if away["win"] > 1e-12:
        away["fair_odds"] = (1.0 - away["push"]) / away["win"]
    return {"home": home, "away": away}


# ------------------------------------------------------------------ fitting


@dataclass
class MatchRecord:
    match_date: date
    home: str
    away: str
    home_goals: int
    away_goals: int


@dataclass
class DCModel:
    attack: Dict[str, float] = field(default_factory=dict)
    defense: Dict[str, float] = field(default_factory=dict)
    home_adv: float = 0.0
    rho: float = 0.0
    half_life_days: float = 365.0
    asof: Optional[date] = None
    n_matches: int = 0
    n_teams: int = 0
    loglik_per_match: float = 0.0

    def _params(self, home: str, away: str) -> Tuple[float, float]:
        a_h = self.attack.get(home, 0.0)
        d_a = self.defense.get(away, 0.0)
        a_a = self.attack.get(away, 0.0)
        d_h = self.defense.get(home, 0.0)
        lam = math.exp(a_h + d_a + self.home_adv)
        mu = math.exp(a_a + d_h)
        return max(0.05, min(6.0, lam)), max(0.05, min(6.0, mu))

    def score_matrix(self, home: str, away: str, max_goals: int = 10) -> List[List[float]]:
        lam, mu = self._params(home, away)
        return tau_corrected_matrix(lam, mu, self.rho, max_goals=max_goals)

    def probs_1x2(self, home: str, away: str, max_goals: int = 10) -> Dict[str, float]:
        mat = self.score_matrix(home, away, max_goals=max_goals)
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

    def predict_markets(self, home: str, away: str, max_goals: int = 10) -> List[dict]:
        """1X2 + AH(SUPPORTED_AH_LINES, both sides) rows for afb_predictions.

        line semantics (documented in module docstring): the value is the HOME
        line; selection 'Home' = home +L, selection 'Away' = away +L (the
        complementary side of the same market).
        """
        rows: List[dict] = []
        tag = f"DC tau rho={self.rho:+.3f} hl={self.half_life_days:.0f}d"

        p1x2 = self.probs_1x2(home, away, max_goals=max_goals)
        for sel in ("Home", "Draw", "Away"):
            rows.append(
                {
                    "market": "1X2",
                    "line": None,
                    "selection": sel,
                    "model_probability": p1x2[sel],
                    "rationale": tag,
                }
            )

        mat = self.score_matrix(home, away, max_goals=max_goals)
        for line in SUPPORTED_AH_LINES:
            res = ah_probs(mat, line)
            for sel, side in (("Home", res["home"]), ("Away", res["away"])):
                fair = side["fair_odds"]
                rationale = tag + (f" fair={fair:.3f}" if fair is not None else "")
                rows.append(
                    {
                        "market": "Asian Handicap",
                        "line": f"{line:g}",
                        "selection": sel,
                        "model_probability": side["eff"],
                        "rationale": rationale,
                    }
                )
        return rows


def _build_index(
    matches: Sequence[MatchRecord],
    asof: date,
    half_life_days: float,
    min_matches: int,
) -> Tuple[Dict[str, List[int]], List[float], List[MatchRecord]]:
    """As-of filter, decay weights, and per-team match index (min_matches gate)."""
    team_counts: Dict[str, int] = {}
    weights: List[float] = []
    kept: List[MatchRecord] = []
    for m in matches:
        if m.match_date >= asof:
            continue
        if m.home_goals is None or m.away_goals is None:
            continue
        age = (asof - m.match_date).days
        if age < 0:
            continue
        weights.append(decay_weight(age, half_life_days))
        kept.append(m)
        team_counts[m.home] = team_counts.get(m.home, 0) + 1
        team_counts[m.away] = team_counts.get(m.away, 0) + 1

    team_idx: Dict[str, List[int]] = {}
    for i, m in enumerate(kept):
        if team_counts.get(m.home, 0) >= min_matches:
            team_idx.setdefault(m.home, []).append(i)
        if team_counts.get(m.away, 0) >= min_matches:
            team_idx.setdefault(m.away, []).append(i)
    return team_idx, weights, kept


def fit_dc(
    matches: Sequence[MatchRecord],
    asof: date,
    half_life_days: float = 365.0,
    min_matches: int = 10,
    max_sweeps: int = 40,
    tol: float = 1e-5,
    rho_grid: Optional[Sequence[float]] = None,
    fit_rho: bool = True,
) -> DCModel:
    """Fit the Dixon-Coles model by coordinate-ascent MLE.

    - attack/defense: closed-form Poisson updates per team per sweep
    - home_adv: closed-form update per sweep
    - rho: in-sweep 1-D grid search maximising the tau-corrected likelihood
    - gauge fixing: mean(attack) pinned to 0 after each sweep
    - teams with < min_matches matches in the window stay at neutral 0.0
    """
    if rho_grid is None:
        rho_grid = [round(-0.15 + 0.01 * i, 3) for i in range(26)]  # [-0.15, +0.10]

    team_idx, weights, kept = _build_index(matches, asof, half_life_days, min_matches)
    if not kept:
        raise ValueError("no usable matches in window")

    attack: Dict[str, float] = {t: 0.0 for t in team_idx}
    defense: Dict[str, float] = {t: 0.0 for t in team_idx}
    home_adv = 0.0
    rho = 0.0
    teams = sorted(team_idx.keys())

    for _sweep in range(max_sweeps):
        max_delta = 0.0

        # ---- attack: goals scored by team i ----
        for t in teams:
            num = den = 0.0
            for i in team_idx[t]:
                m = kept[i]
                w = weights[i]
                if m.home == t:
                    num += w * m.home_goals
                    den += w * math.exp(defense.get(m.away, 0.0) + home_adv)
                else:
                    num += w * m.away_goals
                    den += w * math.exp(defense.get(m.home, 0.0))
            new_a = math.log(num + 1e-9) - math.log(den + 1e-9) if den > 0 else 0.0
            max_delta = max(max_delta, abs(new_a - attack[t]))
            attack[t] = new_a

        # ---- defense: goals conceded by team j ----
        for t in teams:
            num = den = 0.0
            for i in team_idx[t]:
                m = kept[i]
                w = weights[i]
                if m.home == t:
                    num += w * m.away_goals
                    den += w * math.exp(attack.get(m.away, 0.0))
                else:
                    num += w * m.home_goals
                    den += w * math.exp(attack.get(m.home, 0.0) + home_adv)
            new_d = math.log(num + 1e-9) - math.log(den + 1e-9) if den > 0 else 0.0
            max_delta = max(max_delta, abs(new_d - defense[t]))
            defense[t] = new_d

        # ---- home advantage ----
        num = den = 0.0
        for i, m in enumerate(kept):
            w = weights[i]
            num += w * m.home_goals
            den += w * math.exp(attack.get(m.home, 0.0) + defense.get(m.away, 0.0))
        new_h = math.log(num + 1e-9) - math.log(den + 1e-9) if den > 0 else 0.0
        max_delta = max(max_delta, abs(new_h - home_adv))
        home_adv = new_h

        # ---- gauge fix: mean(attack) = 0 ----
        c = sum(attack[t] for t in teams) / len(teams)
        for t in teams:
            attack[t] -= c
            defense[t] += c

        # ---- rho grid search (tau part of the likelihood) ----
        if fit_rho:
            best_ll, best_rho = -math.inf, rho
            for r in rho_grid:
                ll = 0.0
                feasible = True
                for i, m in enumerate(kept):
                    x, y = m.home_goals, m.away_goals
                    if (x, y) not in ((0, 0), (0, 1), (1, 0), (1, 1)):
                        continue
                    lam = math.exp(attack.get(m.home, 0.0) + defense.get(m.away, 0.0) + home_adv)
                    mu = math.exp(attack.get(m.away, 0.0) + defense.get(m.home, 0.0))
                    tf = tau_factor(x, y, lam, mu, r)
                    if tf <= 0:
                        feasible = False
                        break
                    ll += weights[i] * math.log(tf)
                if feasible and ll > best_ll:
                    best_ll, best_rho = ll, r
            rho = best_rho

        if max_delta < tol:
            break

    # ---- report metric: weighted tau-corrected log-likelihood per match ----
    ll_total = w_total = 0.0
    for i, m in enumerate(kept):
        lam = math.exp(attack.get(m.home, 0.0) + defense.get(m.away, 0.0) + home_adv)
        mu = math.exp(attack.get(m.away, 0.0) + defense.get(m.home, 0.0))
        x, y = m.home_goals, m.away_goals
        w = weights[i]
        ll_total += w * (
            x * math.log(lam) - lam + y * math.log(mu) - mu
            + math.log(max(1e-12, tau_factor(x, y, lam, mu, rho)))
        )
        w_total += w

    return DCModel(
        attack=attack,
        defense=defense,
        home_adv=home_adv,
        rho=rho,
        half_life_days=half_life_days,
        asof=asof,
        n_matches=len(kept),
        n_teams=len(teams),
        loglik_per_match=(ll_total / w_total) if w_total else 0.0,
    )


def fit_half_life_by_validation(
    matches: Sequence[MatchRecord],
    candidates: Sequence[float] = (180.0, 270.0, 365.0, 540.0, 730.0),
    min_matches: int = 10,
) -> Tuple[float, dict]:
    """Choose the half-life by hold-out log-likelihood on the newest 25%.

    Returns (best_half_life, report) with report mapping half_life -> mean
    tau-corrected per-match log-likelihood on the validation window.
    """
    if not matches:
        raise ValueError("no matches")
    dates = sorted(m.match_date for m in matches)
    cut_idx = int(len(dates) * 0.75)
    cut_date = dates[cut_idx]
    last_date = dates[-1]

    train = [m for m in matches if m.match_date < cut_date]
    valid = [m for m in matches if m.match_date >= cut_date]
    if not train or not valid:
        return float(candidates[len(candidates) // 2]), {}

    report: dict = {}
    best_hl, best_ll = float(candidates[len(candidates) // 2]), -math.inf
    for hl in candidates:
        model = fit_dc(train, asof=cut_date, half_life_days=hl, min_matches=min_matches)
        ll = 0.0
        for m in valid:
            lam, mu = model._params(m.home, m.away)
            x, y = m.home_goals, m.away_goals
            w = decay_weight((last_date - m.match_date).days, hl)
            ll += w * (
                x * math.log(lam) - lam + y * math.log(mu) - mu
                + math.log(max(1e-12, tau_factor(x, y, lam, mu, model.rho)))
            )
        report[hl] = ll / max(1, len(valid))
        if report[hl] > best_ll:
            best_ll, best_hl = report[hl], float(hl)
    return best_hl, report


__all__ = [
    "DCModel",
    "MatchRecord",
    "SUPPORTED_AH_LINES",
    "ah_probs",
    "decay_weight",
    "fit_dc",
    "fit_half_life_by_validation",
    "tau_corrected_matrix",
    "tau_factor",
]
