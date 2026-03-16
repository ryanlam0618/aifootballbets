from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from v2.config import settings_v2
from v2.paper.report import generate_reports
from v2.paper.run_day import _build_odds_provider, run_for_day
from v2.paper.settle import _build_results_provider, run_settlement


def run_7d(
    start_date,
    db_path: Path,
    snapshot_db: Path,
    run_prefix: str,
    odds_provider_name: str = "espn",
    results_provider_name: str = "espn",
) -> None:
    for i in range(7):
        day = start_date + timedelta(days=i)
        run_id = f"{run_prefix}_{day.isoformat()}"

        selected = run_for_day(
            day=day,
            db_path=db_path,
            snapshot_db=snapshot_db,
            initial_bankroll=settings_v2.initial_bankroll,
            run_id=run_id,
            provider=_build_odds_provider(odds_provider_name, provider_json=""),
        )
        print(f"[DAY {day.isoformat()}] select({odds_provider_name}) -> {selected}")

        settled = run_settlement(db_path=db_path, day=day, provider=_build_results_provider(results_provider_name))
        print(f"[DAY {day.isoformat()}] settled({results_provider_name}) -> {settled}")

        daily, weekly = generate_reports(db_path=db_path, day=day, out_dir=Path("reports/v2"))
        print(f"[DAY {day.isoformat()}] reports -> {daily.name}, {weekly.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 7-day paper trading simulation")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--sqlite",
        default=str(Path(settings_v2.tracking_sqlite_path)),
        help="tracking sqlite path",
    )
    parser.add_argument("--snapshot-db", default="data/v2/odds_snapshots.sqlite")
    parser.add_argument("--run-prefix", default="paper7d")
    parser.add_argument(
        "--odds-provider",
        choices=["espn", "sofascore"],
        default="espn",
        help="fixtures/odds provider used in run_day",
    )
    parser.add_argument(
        "--results-provider",
        choices=["espn", "sofascore"],
        default="espn",
        help="results provider used in settle",
    )
    args = parser.parse_args()

    start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    run_7d(
        start,
        Path(args.sqlite),
        Path(args.snapshot_db),
        args.run_prefix,
        odds_provider_name=args.odds_provider,
        results_provider_name=args.results_provider,
    )


if __name__ == "__main__":
    main()
