from __future__ import annotations

import math
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from v2.config import settings_v2
from v2.paper.models import CandidateBet, MatchInfo
from v2.paper.pricing import implied_probability_raw
from v2.paper.team_strength import estimate_match_goal_model


Matrix = List[List[float]]


def _score_matrix(mu_h: float, mu_a: float, max_goals: int = 10) -> Matrix:
    def pmf(k: int, mu: float) -> float:
        if mu <= 0:
            return 1.0 if k == 0 else 0.0
        return math.exp(-mu) * (mu ** k) / math.factorial(k)

    mat: Matrix = [[0.0 for _ in range(max_goals + 1)] for _ in range(max_goals + 1)]
    total = 0.0
    for h in range(max_goals + 1):
        ph = pmf(h, mu_h)
        for a in range(max_goals + 1):
            v = ph * pmf(a, mu_a)
            mat[h][a] = v
            total += v

    if total > 0:
        inv = 1.0 / total
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                mat[h][a] *= inv
    return mat


def _prob_1x2(mat: Matrix) -> Dict[str, float]:
    home = draw = away = 0.0
    n = len(mat)
    for h in range(n):
        for a in range(n):
            p = float(mat[h][a])
            if h > a:
                home += p
            elif h == a:
                draw += p
            else:
                away += p
    return {"Home": home, "Draw": draw, "Away": away}


def _prob_over(mat: Matrix, line: float) -> float:
    p = 0.0
    n = len(mat)
    for h in range(n):
        for a in range(n):
            if (h + a) > line:
                p += float(mat[h][a])
    return p


def _prob_home_ah(mat: Matrix, line: float) -> float:
    p = 0.0
    n = len(mat)
    for h in range(n):
        for a in range(n):
            if (h + line) > a:
                p += float(mat[h][a])
    return p


def _ev(prob: float, odds: float) -> float:
    if odds <= 1:
        return -1.0
    return (prob * (odds - 1.0)) - (1.0 - prob)


def kelly_full(prob: float, odds: float) -> float:
    if odds <= 1:
        return 0.0
    b = odds - 1.0
    q = 1.0 - prob
    k = (b * prob - q) / b
    return max(0.0, k)


def expected_log_growth(prob: float, odds: float, f: float) -> float:
    if f <= 0 or odds <= 1:
        return 0.0
    b = odds - 1.0
    if (1.0 + f * b) <= 0 or (1.0 - f) <= 0:
        return -1e9
    return (prob * math.log(1.0 + f * b)) + ((1.0 - prob) * math.log(1.0 - f))


def _parse_market_key(market_key: str) -> Tuple[str, str]:
    s = (market_key or "").strip()
    if s.startswith("Over/Under"):
        tail = s.replace("Over/Under", "", 1).strip()
        return "Over/Under", tail
    if s.startswith("Asian Handicap"):
        tail = s.replace("Asian Handicap", "", 1).strip()
        return "Asian Handicap", tail
    return s, ""


def _match_day(match: MatchInfo) -> date:
    raw = str(match.kickoff_utc or "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except Exception:
            pass
    return date.today()


def _estimate_mu(match: MatchInfo) -> tuple[float, float]:
    try:
        goal_model = estimate_match_goal_model(
            league_key=match.league_key,
            league_name=match.league_name,
            home_team=match.home_team,
            away_team=match.away_team,
            day=_match_day(match),
        )
        return goal_model.mu_home, goal_model.mu_away
    except Exception:
        return 1.25, 1.10


def generate_candidates_for_match(
    match: MatchInfo,
    odds_map: Dict[Tuple[str, str, str], float],
    implied_map: Dict[Tuple[str, str, str], float] | None = None,
    mu_home: float | None = None,
    mu_away: float | None = None,
    kelly_fraction: Optional[float] = None,
    model_name: str | None = None,
) -> List[CandidateBet]:
    _ = model_name
    k_frac = settings_v2.kelly_fraction if kelly_fraction is None else kelly_fraction

    if mu_home is None or mu_away is None:
        mu_home, mu_away = _estimate_mu(match)

    mat = _score_matrix(mu_home, mu_away)
    probs_1x2 = _prob_1x2(mat)

    out: List[CandidateBet] = []

    for sel in ("Home", "Draw", "Away"):
        odd = odds_map.get((match.match_id, "1X2", sel))
        if not odd:
            continue
        p = probs_1x2[sel]
        key = (match.match_id, "1X2", sel)
        ip = (implied_map or {}).get(key, implied_probability_raw(float(odd)))
        ev = _ev(p, float(odd))
        edge = p - ip
        k = kelly_full(p, float(odd)) * k_frac
        g = expected_log_growth(p, float(odd), k)
        out.append(
            CandidateBet(
                match_id=match.match_id,
                league_key=match.league_key,
                league_name=match.league_name,
                kickoff_utc=match.kickoff_utc,
                home_team=match.home_team,
                away_team=match.away_team,
                market="1X2",
                line="",
                selection=sel,
                odds=float(odd),
                model_probability=p,
                implied_probability=ip,
                edge=edge,
                ev=ev,
                expected_log_growth=g,
            )
        )

    for (mid, market_key, sel), odd in odds_map.items():
        if mid != match.match_id:
            continue
        market, line = _parse_market_key(market_key)
        if market == "Over/Under":
            try:
                line_f = float(line)
            except Exception:
                line_f = 2.5
            p_over = _prob_over(mat, line_f)
            p = p_over if sel == "Over" else (1.0 - p_over)
        elif market == "Asian Handicap":
            try:
                line_f = float(line)
            except Exception:
                line_f = 0.0
            p_home = _prob_home_ah(mat, line_f)
            p = p_home if sel == "Home" else (1.0 - p_home)
        else:
            continue

        key = (match.match_id, market_key, sel)
        ip = (implied_map or {}).get(key, implied_probability_raw(float(odd)))
        ev = _ev(p, float(odd))
        edge = p - ip
        k = kelly_full(p, float(odd)) * k_frac
        g = expected_log_growth(p, float(odd), k)

        out.append(
            CandidateBet(
                match_id=match.match_id,
                league_key=match.league_key,
                league_name=match.league_name,
                kickoff_utc=match.kickoff_utc,
                home_team=match.home_team,
                away_team=match.away_team,
                market=market,
                line=str(line),
                selection=sel,
                odds=float(odd),
                model_probability=p,
                implied_probability=ip,
                edge=edge,
                ev=ev,
                expected_log_growth=g,
            )
        )

    return out


def select_best_per_match(
    candidates: List[CandidateBet],
    min_edge: float | None = None,
    min_ev: float = 0.0,
) -> Dict[str, CandidateBet]:
    edge_cut = settings_v2.min_edge if min_edge is None else min_edge
    filtered = [c for c in candidates if c.edge >= edge_cut and c.ev > min_ev and c.expected_log_growth > 0]

    best: Dict[str, CandidateBet] = {}
    for c in filtered:
        old = best.get(c.match_id)
        if old is None or c.expected_log_growth > old.expected_log_growth:
            best[c.match_id] = c
    return best
