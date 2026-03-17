#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from v2.paper.run_7d import run_7d, run_walkforward, _default_start_date_today_shanghai


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
    parser.add_argument(
        "--decision-log-dir",
        default="",
        help="directory for per-day decision JSONL logs (default: <out-dir>/decisions)",
    )
    parser.add_argument(
        "--out-dir",
        default="reports/v2",
        help="output directory for reports and final 7D summary",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=2000.0,
        help="initial bankroll for this run (default: 2000)",
    )
    parser.add_argument(
        "--walkforward-end-date",
        default="",
        help="optional YYYY-MM-DD; run multiple 7-day windows from --start-date to this end date",
    )
    parser.add_argument(
        "--closing-odds-tracker-sqlite",
        default="",
        help="optional OddsPortal tracker sqlite for closing-odds hook",
    )
    args = parser.parse_args()

    start = _default_start_date_today_shanghai() if not str(args.start_date).strip() else datetime.strptime(args.start_date, "%Y-%m-%d").date()
    closing_tracker = Path(args.closing_odds_tracker_sqlite) if str(args.closing_odds_tracker_sqlite).strip() else None

    if str(args.walkforward_end_date).strip():
        wf_end = datetime.strptime(args.walkforward_end_date, "%Y-%m-%d").date()
        run_walkforward(
            start_date=start,
            end_date=wf_end,
            db_path=Path(args.sqlite),
            snapshot_db=Path(args.snapshot_db),
            run_prefix=args.run_prefix,
            odds_provider_name=args.odds_provider,
            results_provider_name=args.results_provider,
            provider_json=str(args.provider_json or "").strip(),
            allow_synthetic_odds=bool(args.allow_synthetic_odds),
            decision_log_dir=Path(args.decision_log_dir) if str(args.decision_log_dir).strip() else None,
            initial_bankroll=float(args.bankroll),
            out_dir=Path(args.out_dir),
            closing_odds_tracker_sqlite=closing_tracker,
        )
        return

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
        initial_bankroll=float(args.bankroll),
        out_dir=Path(args.out_dir),
        closing_odds_tracker_sqlite=closing_tracker,
    )


if __name__ == "__main__":
    main()
