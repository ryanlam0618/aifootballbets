#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from paper.models import MatchInfo
from paper.pricing import build_devig_implied_map
from paper.providers import JsonFileOddsProvider
from paper.strategy import generate_candidates_for_match, select_best_per_match


def _load_provider(path: str):
    provider = JsonFileOddsProvider(Path(path))
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    matches = [
        MatchInfo(
            match_id=str(m.get("match_id", "")),
            league_key=str(m.get("league_key", "")),
            league_name=str(m.get("league_name", m.get("league_key", ""))),
            kickoff_utc=str(m.get("kickoff_utc", "")),
            home_team=str(m.get("home_team", "")),
            away_team=str(m.get("away_team", "")),
        )
        for m in (payload.get("matches") or [])
    ]
    odds_map, _meta = provider.fetch_market_odds_with_meta(day=datetime.utcnow().date(), league_keys=[], matches=matches)
    return matches, odds_map


def _summarize(label: str, rows):
    best = select_best_per_match(rows, min_edge=0.0, min_ev=-999.0)
    return {
        "model": label,
        "candidates": len(rows),
        "selected": len(best),
        "top": [
            {
                "match_id": c.match_id,
                "selection": c.selection,
                "market": c.market,
                "line": c.line,
                "edge": round(c.edge, 4),
                "ev": round(c.ev, 4),
                "model_probability": round(c.model_probability, 4),
            }
            for c in sorted(best.values(), key=lambda x: (x.expected_log_growth, x.ev, x.edge), reverse=True)[:10]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare paper model outputs on a deterministic provider fixture")
    parser.add_argument("--provider-json", required=True)
    parser.add_argument("--baseline-home", type=float, default=1.25)
    parser.add_argument("--baseline-away", type=float, default=1.10)
    args = parser.parse_args()

    matches, odds_map = _load_provider(args.provider_json)
    implied_map = build_devig_implied_map(odds_map)

    baseline_rows = []
    team_rows = []
    for match in matches:
        baseline_rows.extend(
            generate_candidates_for_match(
                match,
                odds_map=odds_map,
                implied_map=implied_map,
                mu_home=args.baseline_home,
                mu_away=args.baseline_away,
                model_name="baseline",
            )
        )
        team_rows.extend(
            generate_candidates_for_match(
                match,
                odds_map=odds_map,
                implied_map=implied_map,
                mu_home=None,
                mu_away=None,
                model_name="team_strength",
            )
        )

    out = {
        "provider_json": args.provider_json,
        "baseline": _summarize("baseline", baseline_rows),
        "team_strength": _summarize("team_strength", team_rows),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
