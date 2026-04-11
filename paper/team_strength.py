from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Tuple

from config import BASE_DIR, settings_v2
from paper.constants import SOFASCORE_LEAGUE_MAP
from paper.providers import normalize_team


DEFAULT_HISTORY_CSV = BASE_DIR / "data" / "backfill_sofascore_10y" / "history_data_10y_leagues_cups.csv"
DEFAULT_BASELINE_MU_HOME = 1.25
DEFAULT_BASELINE_MU_AWAY = 1.10
DEFAULT_HOME_ADVANTAGE_GOALS = 0.18
DEFAULT_LOOKBACK_MATCHES = 10
DEFAULT_SHRINK_MATCHES = 12.0
DEFAULT_STRENGTH_CLAMP = (0.65, 1.35)
DEFAULT_MU_CLAMP = (0.2, 4.5)


@dataclass(frozen=True)
class TeamRecentStats:
    matches: int
    goals_for_avg: float
    goals_against_avg: float
    xg_for_avg: float | None
    xg_against_avg: float | None


@dataclass(frozen=True)
class TeamStrength:
    team: str
    matches: int
    attack: float
    defense: float


@dataclass(frozen=True)
class LeagueBaseline:
    league_name: str
    home_goals_avg: float
    away_goals_avg: float
    matches: int


@dataclass(frozen=True)
class MatchGoalModel:
    mu_home: float
    mu_away: float
    home_strength: TeamStrength
    away_strength: TeamStrength
    league_baseline: LeagueBaseline
    method: str


def _safe_float(v: object) -> float | None:
    try:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def _league_names_for_key(league_key: str, fallback_name: str = "") -> list[str]:
    cfg = SOFASCORE_LEAGUE_MAP.get(league_key) or {}
    names = []
    if cfg.get("league_name"):
        names.append(str(cfg.get("league_name")))
    for alias in cfg.get("tournament_aliases") or []:
        a = str(alias).strip()
        if a:
            names.append(a)
    if fallback_name:
        names.append(str(fallback_name))

    out = []
    seen = set()
    for n in names:
        k = normalize_team(n)
        if k and k not in seen:
            out.append(n)
            seen.add(k)
    return out


def _iter_history_rows(history_csv: Path) -> Iterable[dict]:
    if not history_csv.exists():
        return []
    with history_csv.open("r", encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


@lru_cache(maxsize=4)
def _load_history_index(history_csv_str: str) -> dict:
    history_csv = Path(history_csv_str)
    team_rows: Dict[str, list[dict]] = {}
    league_rows: Dict[str, list[dict]] = {}

    for row in _iter_history_rows(history_csv):
        home = str(row.get("home_team") or "").strip()
        away = str(row.get("away_team") or "").strip()
        league = str(row.get("league") or "").strip()
        d = str(row.get("match_date") or "").strip()
        hg = _safe_float(row.get("home_goals"))
        ag = _safe_float(row.get("away_goals"))
        if not home or not away or not league or not d or hg is None or ag is None:
            continue

        item = {
            "date": d,
            "league": league,
            "home_team": home,
            "away_team": away,
            "home_goals": hg,
            "away_goals": ag,
            "home_xg": _safe_float(row.get("home_xg_total")),
            "away_xg": _safe_float(row.get("away_xg_total")),
        }

        league_rows.setdefault(normalize_team(league), []).append(item)
        team_rows.setdefault(normalize_team(home), []).append(item)
        team_rows.setdefault(normalize_team(away), []).append(item)

    for rows in team_rows.values():
        rows.sort(key=lambda x: x["date"])
    for rows in league_rows.values():
        rows.sort(key=lambda x: x["date"])

    return {"team_rows": team_rows, "league_rows": league_rows}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def _league_baseline(index: dict, league_names: list[str], ref_day: date) -> LeagueBaseline:
    rows: list[dict] = []
    seen = set()
    for name in league_names:
        key = normalize_team(name)
        for row in index["league_rows"].get(key, []):
            if row["date"] >= ref_day.isoformat():
                continue
            rid = (row["date"], row["home_team"], row["away_team"], row["league"])
            if rid in seen:
                continue
            seen.add(rid)
            rows.append(row)

    if not rows:
        return LeagueBaseline(" / ".join(league_names) or "unknown", DEFAULT_BASELINE_MU_HOME, DEFAULT_BASELINE_MU_AWAY, 0)

    home_avg = sum(r["home_goals"] for r in rows) / len(rows)
    away_avg = sum(r["away_goals"] for r in rows) / len(rows)
    return LeagueBaseline(league_names[0] if league_names else rows[0]["league"], home_avg, away_avg, len(rows))


def _team_recent_stats(index: dict, team_name: str, ref_day: date, lookback_matches: int) -> TeamRecentStats:
    team_key = normalize_team(team_name)
    rows = [r for r in index["team_rows"].get(team_key, []) if r["date"] < ref_day.isoformat()]
    rows = rows[-lookback_matches:]

    if not rows:
        return TeamRecentStats(matches=0, goals_for_avg=0.0, goals_against_avg=0.0, xg_for_avg=None, xg_against_avg=None)

    gf = ga = 0.0
    xgf_values = []
    xga_values = []
    for r in rows:
        is_home = normalize_team(r["home_team"]) == team_key
        gf += float(r["home_goals"] if is_home else r["away_goals"])
        ga += float(r["away_goals"] if is_home else r["home_goals"])

        xgf = r.get("home_xg") if is_home else r.get("away_xg")
        xga = r.get("away_xg") if is_home else r.get("home_xg")
        if xgf is not None:
            xgf_values.append(float(xgf))
        if xga is not None:
            xga_values.append(float(xga))

    n = len(rows)
    return TeamRecentStats(
        matches=n,
        goals_for_avg=gf / n,
        goals_against_avg=ga / n,
        xg_for_avg=(sum(xgf_values) / len(xgf_values)) if xgf_values else None,
        xg_against_avg=(sum(xga_values) / len(xga_values)) if xga_values else None,
    )


def _team_strength(
    index: dict,
    team_name: str,
    ref_day: date,
    baseline: LeagueBaseline,
    lookback_matches: int,
    shrink_matches: float,
    use_xg: bool,
) -> TeamStrength:
    recent = _team_recent_stats(index, team_name, ref_day, lookback_matches)

    if not recent.matches:
        return TeamStrength(team=team_name, matches=0, attack=1.0, defense=1.0)

    n = recent.matches
    gf_avg = recent.xg_for_avg if (use_xg and recent.xg_for_avg is not None) else recent.goals_for_avg
    ga_avg = recent.xg_against_avg if (use_xg and recent.xg_against_avg is not None) else recent.goals_against_avg
    shrink = n / (n + shrink_matches) if shrink_matches > 0 else 1.0

    base_scored = max(0.2, (baseline.home_goals_avg + baseline.away_goals_avg) / 2.0)
    attack_raw = gf_avg / base_scored if base_scored > 0 else 1.0
    defense_raw = ga_avg / base_scored if base_scored > 0 else 1.0

    attack = (shrink * attack_raw) + ((1.0 - shrink) * 1.0)
    defense = (shrink * defense_raw) + ((1.0 - shrink) * 1.0)
    lo, hi = DEFAULT_STRENGTH_CLAMP
    return TeamStrength(team=team_name, matches=n, attack=_clamp(attack, lo, hi), defense=_clamp(defense, lo, hi))


def estimate_match_goal_model(
    league_key: str,
    league_name: str,
    home_team: str,
    away_team: str,
    day: date,
    history_csv: Path | None = None,
    lookback_matches: int = DEFAULT_LOOKBACK_MATCHES,
    shrink_matches: float = DEFAULT_SHRINK_MATCHES,
    home_advantage_goals: float = DEFAULT_HOME_ADVANTAGE_GOALS,
) -> MatchGoalModel:
    csv_path = Path(history_csv or DEFAULT_HISTORY_CSV)
    index = _load_history_index(str(csv_path))
    league_names = _league_names_for_key(league_key, fallback_name=league_name)
    baseline = _league_baseline(index, league_names=league_names, ref_day=day)

    model_lookback_matches = int(lookback_matches or settings_v2.paper_model_lookback_matches)
    model_shrink_matches = float(shrink_matches or settings_v2.paper_model_shrink_matches)
    model_home_advantage_goals = float(home_advantage_goals if home_advantage_goals is not None else settings_v2.paper_model_home_advantage_goals)
    use_xg = bool(settings_v2.paper_model_use_xg)

    home_strength = _team_strength(index, home_team, day, baseline, model_lookback_matches, model_shrink_matches, use_xg)
    away_strength = _team_strength(index, away_team, day, baseline, model_lookback_matches, model_shrink_matches, use_xg)

    mu_home = baseline.home_goals_avg * home_strength.attack * away_strength.defense
    mu_away = baseline.away_goals_avg * away_strength.attack * home_strength.defense

    # Apply a small additive home edge after multiplicative strength terms.
    mu_home += model_home_advantage_goals

    mu_lo, mu_hi = DEFAULT_MU_CLAMP
    mu_home = _clamp(mu_home, mu_lo, mu_hi)
    mu_away = _clamp(mu_away, mu_lo, mu_hi)

    return MatchGoalModel(
        mu_home=mu_home,
        mu_away=mu_away,
        home_strength=home_strength,
        away_strength=away_strength,
        league_baseline=baseline,
        method="team_strength_goal_rates",
    )
