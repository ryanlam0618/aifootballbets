from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import poisson



@dataclass
class ModelPick:
    match_id: str
    league: str
    home_team: str
    away_team: str
    market: str
    line: str
    selection: str
    odds: float
    model_probability: float
    implied_probability: float
    edge: float
    ev: float
    confidence: str
    rationale: str


def _score_matrix(mu_h: float, mu_a: float, max_goals: int = 10) -> np.ndarray:
    mat = np.zeros((max_goals + 1, max_goals + 1))
    for h in range(max_goals + 1):
        ph = poisson.pmf(h, mu_h)
        for a in range(max_goals + 1):
            pa = poisson.pmf(a, mu_a)
            mat[h, a] = ph * pa
    s = mat.sum()
    return mat / s if s > 0 else mat


def _prob_over(mat: np.ndarray, line: float) -> float:
    prob = 0.0
    for h in range(mat.shape[0]):
        for a in range(mat.shape[1]):
            if (h + a) > line:
                prob += mat[h, a]
    return float(prob)


def _prob_home_ah(mat: np.ndarray, line: float) -> float:
    # Approximation for AH line: win if (home_goals + line) > away_goals
    prob = 0.0
    for h in range(mat.shape[0]):
        for a in range(mat.shape[1]):
            if (h + line) > a:
                prob += mat[h, a]
    return float(prob)


def _to_conf(edge: float) -> str:
    if edge >= 0.08:
        return "High"
    if edge >= 0.04:
        return "Medium"
    return "Low"


def _safe_float(x, d=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def _implied(odds: float) -> float:
    if odds <= 1:
        return np.nan
    return 1.0 / odds


def _ev(prob: float, odds: float) -> float:
    if odds <= 1:
        return -1.0
    b = odds - 1.0
    return (prob * b) - (1 - prob)


def _build_probabilities(mu_h: float, mu_a: float) -> Dict[str, float]:
    # v2 standalone: use Poisson score matrix directly (no v1 src dependencies)
    mat = _score_matrix(mu_h, mu_a, max_goals=10)
    home_win = 0.0
    draw = 0.0
    away_win = 0.0
    for h in range(mat.shape[0]):
        for a in range(mat.shape[1]):
            p = float(mat[h, a])
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p

    out = {"home_win": home_win, "draw": draw, "away_win": away_win}
    s = out["home_win"] + out["draw"] + out["away_win"]
    if s > 0:
        for k in list(out.keys()):
            out[k] = out[k] / s
    return out


def predict_markets(
    features_df: pd.DataFrame,
    market_odds_map: Dict[Tuple[str, str, str], float],
) -> pd.DataFrame:
    picks: List[ModelPick] = []

    for _, row in features_df.iterrows():
        match_id = row["match_id"]
        league = row.get("league", "")
        home = row.get("home_team", "")
        away = row.get("away_team", "")

        mu_h = _safe_float(row.get("home_xg_avg_5"), 1.25)
        mu_a = _safe_float(row.get("away_xg_avg_5"), 1.10)
        mu_h = max(0.2, min(4.5, mu_h))
        mu_a = max(0.2, min(4.5, mu_a))

        probs_1x2 = _build_probabilities(mu_h, mu_a)
        score_mat = _score_matrix(mu_h, mu_a, max_goals=10)

        # 1x2
        for sel, key in [("Home", "home_win"), ("Draw", "draw"), ("Away", "away_win")]:
            odd = market_odds_map.get((match_id, "1X2", sel))
            if not odd:
                continue
            mp = probs_1x2[key]
            ip = _implied(odd)
            edge = mp - ip
            ev = _ev(mp, odd)
            picks.append(
                ModelPick(
                    match_id=match_id,
                    league=league,
                    home_team=home,
                    away_team=away,
                    market="1X2",
                    line="",
                    selection=sel,
                    odds=float(odd),
                    model_probability=mp,
                    implied_probability=ip,
                    edge=edge,
                    ev=ev,
                    confidence=_to_conf(edge),
                    rationale=f"1X2 綜合機率 (Poisson/DC/NB), μ={mu_h:.2f}-{mu_a:.2f}",
                )
            )

        # OU + AH from available odds map
        for (mid, market_key, sel), odd in market_odds_map.items():
            if mid != match_id:
                continue
            if market_key.startswith("Over/Under"):
                try:
                    line = float(market_key.split(" ")[-1])
                except Exception:
                    line = 2.5
                p_over = _prob_over(score_mat, line)
                mp = p_over if sel == "Over" else (1 - p_over)
                ip = _implied(odd)
                edge = mp - ip
                ev = _ev(mp, odd)
                picks.append(
                    ModelPick(
                        match_id=match_id,
                        league=league,
                        home_team=home,
                        away_team=away,
                        market="Over/Under",
                        line=str(line),
                        selection=sel,
                        odds=float(odd),
                        model_probability=mp,
                        implied_probability=ip,
                        edge=edge,
                        ev=ev,
                        confidence=_to_conf(edge),
                        rationale=f"總入球分佈推導 O/U {line}",
                    )
                )
            elif market_key.startswith("Asian Handicap"):
                try:
                    line = float(market_key.split(" ")[-1])
                except Exception:
                    line = 0.0
                # line here from bookmaker on named side, assume line belongs to Home side
                p_home = _prob_home_ah(score_mat, line)
                mp = p_home if sel == "Home" else (1 - p_home)
                ip = _implied(odd)
                edge = mp - ip
                ev = _ev(mp, odd)
                picks.append(
                    ModelPick(
                        match_id=match_id,
                        league=league,
                        home_team=home,
                        away_team=away,
                        market="Asian Handicap",
                        line=str(line),
                        selection=sel,
                        odds=float(odd),
                        model_probability=mp,
                        implied_probability=ip,
                        edge=edge,
                        ev=ev,
                        confidence=_to_conf(edge),
                        rationale=f"比分矩陣推導 AH {line}",
                    )
                )

    out = pd.DataFrame([p.__dict__ for p in picks])
    if out.empty:
        return out

    out["expected_value_assessment"] = np.where(out["ev"] > 0, "Positive", "Negative")
    return out.sort_values(["match_id", "edge"], ascending=[True, False]).reset_index(drop=True)
