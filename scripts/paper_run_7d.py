#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from v2.paper.run_7d import run_7d, _default_start_date_today_shanghai


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run 7-day paper trading end-to-end (select -> settle -> report -> final summary)"
    )
    parser.add_argument(
        "--start-date",
        default="",
        help="YYYY-MM-DD (default: last 7 fully settled days ending yesterday Asia/Shanghai)",
    )
    parser.add_argument("--sqlite", default="data/v2/tracking/bets.sqlite")
    parser.add_argument("--snapshot-db", default="data/v2/odds_snapshots.sqlite")
    parser.add_argument("--run-prefix", default="paper7d")
    parser.add_argument("--odds-provider", choices=["espn", "sofascore"], default="espn")
    parser.add_argument("--results-provider", choices=["espn", "sofascore"], default="espn")
    parser.add_argument("--provider-json", default="", help="deterministic fixtures+odds+results JSON")
    parser.add_argument("--allow-synthetic-odds", action="store_true")
    parser.add_argument("--decision-log-dir", default="reports/v2/decisions")
    args = parser.parse_args()

    start = _default_start_date_today_shanghai() if not str(args.start_date).strip() else datetime.strptime(args.start_date, "%Y-%m-%d").date()

    run_7d(
        start_date=start,
        db_path=Path(args.sqlite),
        snapshot_db=Path(args.snapshot_db),
        run_prefix=args.run_prefix,
        odds_provider_name=args.odds_provider,
        results_provider_name=args.results_provider,
        provider_json=str(args.provider_json or "").strip(),
        allow_synthetic_odds=bool(args.allow_synthetic_odds),
        decision_log_dir=Path(args.decision_log_dir) if str(args.decision_log_dir).strip() else None,
    )


if __name__ == "__main__":
    main()
