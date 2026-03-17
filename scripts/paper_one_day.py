#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from v2.config import settings_v2
from v2.paper.report import generate_reports
from v2.paper.run_day import run_for_day
from v2.paper.settle import _build_results_provider, run_settlement


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one-day paper trading end-to-end (select -> settle -> report)"
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--sqlite",
        default=str(Path(settings_v2.tracking_sqlite_path)),
        help="tracking sqlite path",
    )
    parser.add_argument("--snapshot-db", default="data/v2/odds_snapshots.sqlite")
    parser.add_argument("--out-dir", default="reports/v2")
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--provider-json",
        default="",
        help="optional deterministic fixture for local testing (fixtures+odds+results)",
    )
    parser.add_argument("--odds-provider", choices=["espn", "sofascore"], default="espn")
    parser.add_argument("--results-provider", choices=["espn", "sofascore"], default="espn")
    parser.add_argument("--allow-synthetic-odds", action="store_true")
    parser.add_argument("--decision-log", default="")
    parser.add_argument(
        "--closing-odds-tracker-sqlite",
        default="",
        help="optional OddsPortal tracker sqlite for closing-odds hook",
    )
    args = parser.parse_args()

    day = datetime.strptime(args.date, "%Y-%m-%d").date()
    run_id = args.run_id or f"paper_e2e_{day.isoformat()}"

    from v2.paper.run_day import _build_odds_provider

    provider = _build_odds_provider(args.odds_provider, args.provider_json)
    results_provider = _build_results_provider(args.results_provider, provider_json=args.provider_json)

    decision_log_path = Path(args.decision_log) if str(args.decision_log).strip() else None

    selected = run_for_day(
        day=day,
        db_path=Path(args.sqlite),
        snapshot_db=Path(args.snapshot_db),
        initial_bankroll=settings_v2.initial_bankroll,
        run_id=run_id,
        provider=provider,
        allow_synthetic_odds=bool(args.allow_synthetic_odds),
        decision_log_path=decision_log_path,
    )

    settled = run_settlement(
        db_path=Path(args.sqlite),
        day=day,
        provider=results_provider,
        closing_odds_tracker_sqlite=(Path(args.closing_odds_tracker_sqlite) if str(args.closing_odds_tracker_sqlite).strip() else None),
    )
    daily, weekly = generate_reports(db_path=Path(args.sqlite), day=day, out_dir=Path(args.out_dir))

    print(f"[OK] date={day.isoformat()}")
    print(f"  select: {selected}")
    print(f"  settled: {settled}")
    print(f"  daily_report: {daily}")
    print(f"  weekly_report: {weekly}")


if __name__ == "__main__":
    main()
