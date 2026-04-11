from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List

from paper.constants import FIXTURES_LEAGUE_UNIVERSE, LEAGUE_UNIVERSE, SOFASCORE_LEAGUE_MAP
from paper.providers import SofaScoreFixturesResultsProvider


def list_fixtures_for_day(day: date, league_keys: List[str] | None = None) -> Dict[str, Any]:
    provider = SofaScoreFixturesResultsProvider()
    leagues = list(league_keys or FIXTURES_LEAGUE_UNIVERSE)
    matches = provider.fetch_matches(day=day, league_keys=leagues)

    by_league: Dict[str, List[dict]] = defaultdict(list)
    for m in sorted(matches, key=lambda x: (x.league_key, x.kickoff_utc, x.home_team, x.away_team)):
        by_league[m.league_key].append(
            {
                "match_id": m.match_id,
                "league_key": m.league_key,
                "league_name": m.league_name or (SOFASCORE_LEAGUE_MAP.get(m.league_key) or {}).get("league_name", m.league_key),
                "kickoff_utc": m.kickoff_utc,
                "home_team": m.home_team,
                "away_team": m.away_team,
            }
        )

    leagues_out = []
    for lk in leagues:
        cfg = SOFASCORE_LEAGUE_MAP.get(lk) or {}
        league_name = cfg.get("league_name") or lk
        league_matches = by_league.get(lk, [])
        leagues_out.append(
            {
                "league_key": lk,
                "league_name": league_name,
                "match_count": len(league_matches),
                "matches": league_matches,
            }
        )

    return {
        "date": day.isoformat(),
        "total_matches": sum(x["match_count"] for x in leagues_out),
        "league_count": len(leagues_out),
        "leagues": leagues_out,
    }


def render_text_summary(payload: Dict[str, Any], only_with_matches: bool = False) -> str:
    lines: List[str] = [f"Date: {payload['date']}", ""]
    for league in payload.get("leagues", []):
        matches = league.get("matches", [])
        if only_with_matches and not matches:
            continue
        lines.append(f"{league['league_name']}: {league['match_count']} matches")
        for m in matches:
            lines.append(f"- {m['home_team']} vs {m['away_team']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="List today's SofaScore fixtures for tracked leagues and cups")
    parser.add_argument("--date", default="", help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--json", action="store_true", help="output JSON instead of text")
    parser.add_argument("--only-with-matches", action="store_true", help="hide leagues with 0 matches")
    parser.add_argument("--paper-only", action="store_true", help="use paper-trading league universe only")
    args = parser.parse_args()

    day = datetime.strptime(args.date, "%Y-%m-%d").date() if str(args.date).strip() else datetime.utcnow().date()
    league_keys = LEAGUE_UNIVERSE if args.paper_only else FIXTURES_LEAGUE_UNIVERSE
    payload = list_fixtures_for_day(day, league_keys=league_keys)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text_summary(payload, only_with_matches=args.only_with_matches), end="")


if __name__ == "__main__":
    main()
