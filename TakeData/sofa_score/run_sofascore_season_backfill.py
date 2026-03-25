#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "backfill_sofascore_10y"


def parse_season_label(label: str) -> tuple[int, int]:
    parts = label.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid season label: {label} (expected YYYY-YYYY)")
    y1 = int(parts[0])
    y2 = int(parts[1])
    if y2 != y1 + 1:
        raise ValueError(f"Invalid season span: {label}")
    return y1, y2


def season_date_range(label: str, start_month: int = 8, start_day: int = 1) -> tuple[str, str]:
    y1, y2 = parse_season_label(label)
    start = dt.date(y1, start_month, start_day)
    end = start.replace(year=y2) - dt.timedelta(days=1)
    return start.isoformat(), end.isoformat()


def run_cmd(cmd: list[str]) -> None:
    print("[RUN]", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run SofaScore backfill for one season")
    ap.add_argument("--season", required=True, help="Season label, e.g. 2015-2016")
    ap.add_argument("--python", default=sys.executable, help="Python executable")
    ap.add_argument("--start-month", type=int, default=8, help="Season start month (default 8)")
    ap.add_argument("--start-day", type=int, default=1, help="Season start day (default 1)")
    ap.add_argument("--merge-history", action="store_true", help="Merge season export into data/history_data.csv")
    ap.add_argument("--fresh", action="store_true", help="Pass --fresh to primary backfill script")
    ap.add_argument("--no-raw-scheduled", action="store_true", help="Disable scheduled-events raw dumps")
    ap.add_argument("--no-raw-lineups", action="store_true", help="Disable lineups raw dumps")
    ap.add_argument("--all-leagues-odds", action="store_true", help="Pass --all-leagues to event odds backfill")
    args = ap.parse_args()

    start_date, end_date = season_date_range(args.season, args.start_month, args.start_day)
    print(f"[INFO] season={args.season} range={start_date}..{end_date}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db_path = OUT_DIR / "backfill_10y.sqlite"

    # 1) Core matches/statistics backfill
    core_cmd = [
        args.python,
        "TakeData/sofa_score/backfill_10y_leagues_cups.py",
        "--start-date", start_date,
        "--end-date", end_date,
        "--out-dir", str(OUT_DIR),
        "--db", str(db_path),
        "--state", str(OUT_DIR / f"state_sofascore_{args.season}.json"),
    ]
    if args.merge_history:
        core_cmd.append("--merge-history")
    if args.fresh:
        core_cmd.append("--fresh")
    if args.no_raw_scheduled:
        core_cmd.append("--no-dump-raw-scheduled")
    if args.no_raw_lineups:
        core_cmd.append("--no-dump-raw-lineups")
    run_cmd(core_cmd)

    # 2) Shotmap xG backfill (resume-safe table + state)
    run_cmd([
        args.python,
        "TakeData/sofa_score/shotmap_xg_backfill.py",
        "--db", str(db_path),
        "--state", str(OUT_DIR / f"shotmap_backfill_state_{args.season}.json"),
        "--start-date", start_date,
        "--end-date", end_date,
        "--only-missing-xg",
        "--update-matches",
    ])

    # 3) Detailed shotmap rows (resume-safe table + state)
    run_cmd([
        args.python,
        "TakeData/sofa_score/shotmap_detail_backfill.py",
        "--db", str(db_path),
        "--state", str(OUT_DIR / f"shotmap_detail_state_{args.season}.json"),
        "--start-date", start_date,
        "--end-date", end_date,
    ])

    # 4) Event odds backfill (resume-safe table + state)
    odds_cmd = [
        args.python,
        "TakeData/sofa_score/backfill_event_odds_10y.py",
        "--matches-db", str(db_path),
        "--out-db", str(OUT_DIR / "event_odds_10y.sqlite"),
        "--state", str(OUT_DIR / f"event_odds_backfill_state_{args.season}.json"),
        "--start-date", start_date,
        "--end-date", end_date,
    ]
    if args.all_leagues_odds:
        odds_cmd.append("--all-leagues")
    run_cmd(odds_cmd)

    print("[DONE] season pipeline finished")


if __name__ == "__main__":
    main()
