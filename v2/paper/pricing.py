from __future__ import annotations

from typing import Dict, Tuple


OddsKey = Tuple[str, str, str]


def implied_probability_raw(odds: float) -> float:
    try:
        o = float(odds)
    except Exception:
        return float("nan")
    return (1.0 / o) if o > 1.0 else float("nan")


def devig_two_way(odds_a: float, odds_b: float) -> tuple[float, float]:
    pa = implied_probability_raw(odds_a)
    pb = implied_probability_raw(odds_b)
    s = pa + pb
    if s <= 0:
        return pa, pb
    return pa / s, pb / s


def devig_1x2(odds_home: float, odds_draw: float, odds_away: float) -> tuple[float, float, float]:
    ph = implied_probability_raw(odds_home)
    pd = implied_probability_raw(odds_draw)
    pa = implied_probability_raw(odds_away)
    s = ph + pd + pa
    if s <= 0:
        return ph, pd, pa
    return ph / s, pd / s, pa / s


def build_devig_implied_map(odds_map: Dict[OddsKey, float]) -> Dict[OddsKey, float]:
    """
    Build implied-probability map with overround removed for:
    - 1X2 trios (Home/Draw/Away)
    - 2-way pairs in OU and AH (Over/Under, Home/Away)

    For incomplete groups, fallback to raw implied probability.
    """
    implied: Dict[OddsKey, float] = {k: implied_probability_raw(v) for k, v in odds_map.items()}

    grouped: Dict[tuple[str, str], Dict[str, float]] = {}
    for (match_id, market_key, selection), odd in odds_map.items():
        grouped.setdefault((match_id, market_key), {})[selection] = float(odd)

    for (match_id, market_key), sel_map in grouped.items():
        m = str(market_key)
        if m == "1X2":
            if {"Home", "Draw", "Away"}.issubset(sel_map.keys()):
                ph, pd, pa = devig_1x2(sel_map["Home"], sel_map["Draw"], sel_map["Away"])
                implied[(match_id, market_key, "Home")] = ph
                implied[(match_id, market_key, "Draw")] = pd
                implied[(match_id, market_key, "Away")] = pa
            continue

        if m.startswith("Over/Under") and {"Over", "Under"}.issubset(sel_map.keys()):
            po, pu = devig_two_way(sel_map["Over"], sel_map["Under"])
            implied[(match_id, market_key, "Over")] = po
            implied[(match_id, market_key, "Under")] = pu
            continue

        if m.startswith("Asian Handicap") and {"Home", "Away"}.issubset(sel_map.keys()):
            ph, pa = devig_two_way(sel_map["Home"], sel_map["Away"])
            implied[(match_id, market_key, "Home")] = ph
            implied[(match_id, market_key, "Away")] = pa
            continue

    return implied
