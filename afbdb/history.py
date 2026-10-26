"""Read-only history provider: fixtures/results/xG from sofascore-backfill tables.

Produces the same in-memory index shape as paper/team_strength._load_history_index:

    {"team_rows": {team_key: [row, ...]}, "league_rows": {league_key: [row, ...]}}

row = {date, league, home_team, away_team, home_goals, away_goals, home_xg, away_xg}

Rows are as-of filtered downstream (rows sorted by date; consumers slice
``date < ref_day``), so one full load serves every walk-forward day.
"""

from __future__ import annotations

from typing import Dict

_HISTORY_QUERY = """
SELECT m.match_date        AS match_date,
       c.name              AS league,
       th.name             AS home_team,
       ta.name             AS away_team,
       m.home_score        AS home_goals,
       m.away_score        AS away_goals,
       hx.total_xg         AS home_xg,
       ax.total_xg         AS away_xg
FROM matches m
JOIN competitions c ON c.competition_id = m.competition_id
JOIN teams th ON th.team_id = m.home_team_id
JOIN teams ta ON ta.team_id = m.away_team_id
LEFT JOIN (
    SELECT match_id, is_home, SUM(xg) AS total_xg
    FROM match_shotmap
    WHERE xg IS NOT NULL
    GROUP BY match_id, is_home
) hx ON hx.match_id = m.match_id AND hx.is_home = 1
LEFT JOIN (
    SELECT match_id, is_home, SUM(xg) AS total_xg
    FROM match_shotmap
    WHERE xg IS NOT NULL
    GROUP BY match_id, is_home
) ax ON ax.match_id = m.match_id AND ax.is_home = 0
WHERE m.home_score IS NOT NULL
  AND m.away_score IS NOT NULL
"""

_MIN_DATE = "2015-01-01"


def fetch_history_rows(conn, min_date: str = _MIN_DATE) -> list[dict]:
    """Return flat history rows from MySQL (finished matches only)."""
    rows: list[dict] = []
    with conn.cursor() as cur:
        cur.execute(_HISTORY_QUERY + " AND m.match_date >= %s ORDER BY m.match_date ASC", (min_date,))
        for r in cur.fetchall():
            rows.append(
                {
                    "match_date": str(r[0]),
                    "league": str(r[1] or ""),
                    "home_team": str(r[2] or ""),
                    "away_team": str(r[3] or ""),
                    "home_goals": r[4],
                    "away_goals": r[5],
                    "home_xg_total": (float(r[6]) if r[6] is not None else None),
                    "away_xg_total": (float(r[7]) if r[7] is not None else None),
                }
            )
    return rows


def build_history_index(rows: list[dict], normalize_team) -> Dict[str, dict]:
    """Group flat rows into the team/league index used by team_strength."""
    team_rows: Dict[str, list[dict]] = {}
    league_rows: Dict[str, list[dict]] = {}

    for row in rows:
        home = str(row.get("home_team") or "").strip()
        away = str(row.get("away_team") or "").strip()
        league = str(row.get("league") or "").strip()
        d = str(row.get("match_date") or "").strip()
        hg = row.get("home_goals")
        ag = row.get("away_goals")
        if not home or not away or not league or not d or hg is None or ag is None:
            continue

        item = {
            "date": d,
            "league": league,
            "home_team": home,
            "away_team": away,
            "home_goals": float(hg),
            "away_goals": float(ag),
            "home_xg": row.get("home_xg_total"),
            "away_xg": row.get("away_xg_total"),
        }
        league_rows.setdefault(normalize_team(league), []).append(item)
        team_rows.setdefault(normalize_team(home), []).append(item)
        team_rows.setdefault(normalize_team(away), []).append(item)

    for lst in team_rows.values():
        lst.sort(key=lambda x: x["date"])
    for lst in league_rows.values():
        lst.sort(key=lambda x: x["date"])

    return {"team_rows": team_rows, "league_rows": league_rows}


__all__ = ["build_history_index", "fetch_history_rows"]
