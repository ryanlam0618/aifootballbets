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
    m_raw = str(market_key or "").strip()
    m_lower = m_raw.lower()

    # 1X2 aliases from mixed providers
    if m_lower in {"1x2", "match odds", "moneyline", "h2h"}:
        return (str(match_id), "1X2", "")

    # Over/Under aliases (e.g. "OU 2.5", "O/U 2.5", "totals 2.5")
    if m_lower.startswith("over/under") or m_lower.startswith("ou") or m_lower.startswith("o/u") or m_lower.startswith("totals"):
        tail = m_raw
        for prefix in ("Over/Under", "over/under", "OU", "ou", "O/U", "o/u", "Totals", "totals"):
            if tail.startswith(prefix):
                tail = tail.replace(prefix, "", 1).strip()
                break
        line = _try_float(tail)
        line_norm = f"{line:g}" if line is not None else tail
        return (str(match_id), "Over/Under", line_norm)

    # Asian Handicap aliases ("AH -0.5", "Asian -0.5", "spreads -0.5")
    if m_lower.startswith("asian handicap") or m_lower.startswith("ah") or m_lower.startswith("asian") or m_lower.startswith("spreads"):
        tail = m_raw
        for prefix in ("Asian Handicap", "asian handicap", "AH", "ah", "Asian", "asian", "Spreads", "spreads"):
            if tail.startswith(prefix):
                tail = tail.replace(prefix, "", 1).strip()
                break
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


def _canonical_selection(market_family: str, selection: str) -> str | None:
    s = str(selection or "").strip().lower()

    if market_family == "1X2":
        if s in {"home", "h", "1"}:
            return "Home"
        if s in {"draw", "d", "x"}:
            return "Draw"
        if s in {"away", "a", "2"}:
            return "Away"
        return None

    if market_family == "Over/Under":
        if s in {"over", "o"}:
            return "Over"
        if s in {"under", "u"}:
            return "Under"
        return None

    if market_family == "Asian Handicap":
        if s in {"home", "h"}:
            return "Home"
        if s in {"away", "a"}:
            return "Away"
        return None

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
        _mid, family, _line = gk
        sel = _canonical_selection(family, selection)
        if sel is None:
            continue
        grouped.setdefault(gk, {}).setdefault(sel, []).append((k, float(odd)))

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
