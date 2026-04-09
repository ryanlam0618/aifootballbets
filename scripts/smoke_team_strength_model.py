from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from v2.paper.strategy import generate_candidates_for_match
from v2.paper.models import MatchInfo


def main() -> None:
    match = MatchInfo(
        match_id="demo-1",
        league_key="soccer_epl",
        league_name="Premier League",
        kickoff_utc="2026-04-09T19:00:00Z",
        home_team="Arsenal",
        away_team="Chelsea",
    )
    odds_map = {
        ("demo-1", "1X2", "Home"): 2.10,
        ("demo-1", "1X2", "Draw"): 3.50,
        ("demo-1", "1X2", "Away"): 3.40,
        ("demo-1", "Over/Under 2.5", "Over"): 1.95,
        ("demo-1", "Over/Under 2.5", "Under"): 1.95,
    }
    rows = generate_candidates_for_match(match, odds_map=odds_map)
    payload = [
        {
            "market": r.market,
            "line": r.line,
            "selection": r.selection,
            "model_probability": round(r.model_probability, 4),
            "edge": round(r.edge, 4),
            "ev": round(r.ev, 4),
        }
        for r in rows
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
