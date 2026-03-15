from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from v2.config import settings_v2
from v2.paper.report import generate_reports
from v2.paper.run_day import run_for_day
from v2.paper.settle import run_settlement


def run_7d(start_date, db_path: Path, snapshot_db: Path, run_prefix: str) -> None:
    for i in range(7):
        day = start_date + timedelta(days=i)
        run_id = f"{run_prefix}_{day.isoformat()}"

        selected = run_for_day(
            day=day,
            db_path=db_path,
            snapshot_db=snapshot_db,
            initial_bankroll=settings_v2.initial_bankroll,
            run_id=run_id,
        )
        print(f"[DAY {day.isoformat()}] select -> {selected}")

        settled = run_settlement(db_path=db_path, day=day)
        print(f"[DAY {day.isoformat()}] settled -> {settled}")

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
    args = parser.parse_args()

    start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    run_7d(start, Path(args.sqlite), Path(args.snapshot_db), args.run_prefix)


if __name__ == "__main__":
    main()
