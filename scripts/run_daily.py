#!/usr/bin/env python3
"""Layer-2 afb-T5: cron orchestrator for the v1 daily pipeline.

Modes (via --mode):
- daily    : run_pipeline(day) once — select -> odds snapshot -> predictions
             -> settle observability (default cron entry, hourly/daily)
- sample   : odds-only multi-timepoint sampling for today's and upcoming
             fixtures (T-72/48/24/6/1h + closing proxy), per the T4 spec —
             writes afb_odds_snapshots rows (INSERT IGNORE, idempotent)
- coverage : regenerate reports/odds_coverage_inventory.{md,json}

Cron wiring (documented; install via crontab -e):
  # daily pipeline 03:30 HKT
  30 3 * * * cd /root/.openclaw/workspace-coding/aifootballbets && ./.venv/bin/python scripts/run_daily.py --mode daily >> logs/daily.log 2>&1
  # odds snapshots every 2h (idempotent per captured_at second)
  0 */2 * * * cd /root/.openclaw/workspace-coding/aifootballbets && ./.venv/bin/python scripts/run_daily.py --mode sample >> logs/sample.log 2>&1

Note: cron should run the repo's .venv python (has pandas/pymysql); see
scripts/setup_env.sh. logs/ is gitignored.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402
from v1_pipeline import odds_snapshot_stage, pick_day, run_pipeline  # noqa: E402


def mode_daily(day: date, skip_market: bool) -> int:
    result = run_pipeline(day, skip_market=skip_market)
    print(result.to_json())
    return 0


def mode_sample(days_ahead: int) -> int:
    """Odds-only sampling for today + upcoming fixtures (idempotent)."""
    conn = afb_mysql_connect()
    now = datetime.utcnow()
    total_fixtures = total_rows = 0
    # today and the next days_ahead days: sample every fixture in range
    for offset in range(0, days_ahead + 1):
        day = (now + timedelta(days=offset)).date()
        fixtures = pick_day(conn, day)
        if not fixtures:
            continue
        snap = odds_snapshot_stage(conn, fixtures, sample_time=now.replace(microsecond=0))
        total_fixtures += snap["n_fixtures"]
        total_rows += snap["n_rows"]
        print(f"[sample] {day}: {snap['n_fixtures']} fixtures, {snap['n_rows']} rows")
    print(f"[sample] total: {total_fixtures} fixtures, {total_rows} rows (INSERT IGNORE — idempotent)")
    conn.close()
    return 0


def mode_coverage() -> int:
    from scripts.odds_coverage_inventory import main as coverage_main

    sys.argv = ["odds_coverage_inventory"]
    return coverage_main()


def main() -> int:
    p = argparse.ArgumentParser(description="v1 daily pipeline cron orchestrator")
    p.add_argument("--mode", choices=["daily", "sample", "coverage"], default="daily")
    p.add_argument("--day", type=str, default=None, help="pipeline date YYYY-MM-DD (default: today UTC)")
    p.add_argument("--days-ahead", type=int, default=7, help="sample mode: upcoming days (default 7)")
    p.add_argument("--skip-market", action="store_true")
    args = p.parse_args()

    if args.mode == "daily":
        day = (
            datetime.strptime(args.day, "%Y-%m-%d").date()
            if args.day
            else datetime.utcnow().date()
        )
        return mode_daily(day, args.skip_market)
    if args.mode == "sample":
        return mode_sample(args.days_ahead)
    if args.mode == "coverage":
        return mode_coverage()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
