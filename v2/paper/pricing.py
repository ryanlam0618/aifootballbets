from __future__ import annotations

import math
from typing import Dict, Tuple


OddsKey = Tuple[str, str, str]


def implied_probability_raw(odds: float) -> float:
    try:
        o = float(odds)
    except Exception:
        return float("nan")
    return (1.0 / o) if o > 1.0 else float("nan")


def _all_finite(values: tuple[float, ...]) -> bool:
    return all(math.isfinite(v) for v in values)


def _try_float(text: str) -> float | None:
    try:
        return float(str(text).strip())
    except Exception:
        return None


def _canonical_group_key(match_id: str, market_key: str, selection: str) -> tuple[str, str, str] | None:
    m = str(market_key or "").strip()

    if m == "1X2":
        return (str(match_id), "1X2", "")

    if m.startswith("Over/Under"):
        tail = m.replace("Over/Under", "", 1).strip()
        line = _try_float(tail)
        line_norm = f"{line:g}" if line is not None else tail
        return (str(match_id), "Over/Under", line_norm)

    if m.startswith("Asian Handicap"):
        tail = m.replace("Asian Handicap", "", 1).strip()
        line = _try_float(tail)
        if line is None:
            line_norm = tail
        else:
            # Canonicalize AH pairing by absolute line magnitude so both feed shapes pair:
            # - Home -0.5 / Away +0.5
            # - Home -0.5 / Away -0.5
            # (same for +0.5 / -0.5 etc.)
            line_norm = f"{abs(line):g}"
        return (str(match_id), "Asian Handicap", line_norm)

    return None


def devig_two_way(odds_a: float, odds_b: float) -> tuple[float, float]:
    pa = implied_probability_raw(odds_a)
    pb = implied_probability_raw(odds_b)
    if not _all_finite((pa, pb)):
        return pa, pb
    s = pa + pb
    if s <= 0:
        return pa, pb
    return pa / s, pb / s


def devig_1x2(odds_home: float, odds_draw: float, odds_away: float) -> tuple[float, float, float]:
    ph = implied_probability_raw(odds_home)
    pd = implied_probability_raw(odds_draw)
    pa = implied_probability_raw(odds_away)
    if not _all_finite((ph, pd, pa)):
        return ph, pd, pa
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

    Notes:
    - Over/Under lines are grouped by normalized numeric line.
    - Asian Handicap lines are grouped by canonical "home handicap line",
      so Home -0.5 pairs with Away +0.5 (and vice versa).
    """
    implied: Dict[OddsKey, float] = {k: implied_probability_raw(v) for k, v in odds_map.items()}

    grouped: Dict[tuple[str, str, str], Dict[str, list[tuple[OddsKey, float]]]] = {}
    for k, odd in odds_map.items():
        match_id, market_key, selection = k
        gk = _canonical_group_key(match_id, market_key, selection)
        if gk is None:
            continue
        grouped.setdefault(gk, {}).setdefault(selection, []).append((k, float(odd)))

    for (_match_id, market_family, _line_norm), sel_map in grouped.items():
        if market_family == "1X2":
            if not ({"Home", "Draw", "Away"}.issubset(sel_map.keys())):
                continue
            home_key, home_odd = sel_map["Home"][0]
            draw_key, draw_odd = sel_map["Draw"][0]
            away_key, away_odd = sel_map["Away"][0]
            ph, pd, pa = devig_1x2(home_odd, draw_odd, away_odd)
            for key, _ in sel_map["Home"]:
                implied[key] = ph
            for key, _ in sel_map["Draw"]:
                implied[key] = pd
            for key, _ in sel_map["Away"]:
                implied[key] = pa
            continue

        if market_family == "Over/Under":
            if not ({"Over", "Under"}.issubset(sel_map.keys())):
                continue
            over_key, over_odd = sel_map["Over"][0]
            under_key, under_odd = sel_map["Under"][0]
            po, pu = devig_two_way(over_odd, under_odd)
            for key, _ in sel_map["Over"]:
                implied[key] = po
            for key, _ in sel_map["Under"]:
                implied[key] = pu
            continue

        if market_family == "Asian Handicap":
            if not ({"Home", "Away"}.issubset(sel_map.keys())):
                continue
            home_key, home_odd = sel_map["Home"][0]
            away_key, away_odd = sel_map["Away"][0]
            ph, pa = devig_two_way(home_odd, away_odd)
            for key, _ in sel_map["Home"]:
                implied[key] = ph
            for key, _ in sel_map["Away"]:
                implied[key] = pa
            continue

    return implied
