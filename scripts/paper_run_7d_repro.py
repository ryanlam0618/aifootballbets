#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from paper.run_7d import run_7d


DEFAULT_PROVIDER_JSON = REPO_ROOT / "tests" / "fixtures" / "paper7d_provider.json"


def _reset_file(path: Path, *, label: str) -> None:
    if not path.exists():
        return
    if path.is_dir():
        raise SystemExit(f"Refusing to reset {label}: expected file but got directory: {path}")
    path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "One-command deterministic 7-day paper trading run "
            "(bankroll=2000, select->settle->report->final PnL/ROI/DD)"
        )
    )
    parser.add_argument("--start-date", default="2026-03-10", help="YYYY-MM-DD (default: 2026-03-10)")
    parser.add_argument("--bankroll", type=float, default=2000.0, help="initial bankroll (default: 2000)")
    parser.add_argument("--provider-json", default=str(DEFAULT_PROVIDER_JSON), help="deterministic fixture JSON path")
    parser.add_argument("--sqlite", default="data/v2/tracking/bets_repro.sqlite", help="tracking sqlite path")
    parser.add_argument("--snapshot-db", default="data/v2/odds_snapshots_repro.sqlite", help="snapshot sqlite path")
    parser.add_argument("--out-dir", default="reports/v2/repro", help="output directory")
    parser.add_argument("--decision-log-dir", default="reports/v2/repro/decisions", help="decision JSONL directory")
    parser.add_argument("--run-prefix", default="paper7d_repro", help="run id prefix")
    parser.add_argument(
        "--reset",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="reset sqlite/snapshot files before running (default: true)",
    )
    args = parser.parse_args()

    start = datetime.strptime(str(args.start_date), "%Y-%m-%d").date()
    provider_json = str(args.provider_json).strip()
    if not provider_json:
        raise SystemExit("--provider-json is required")

    sqlite_path = Path(args.sqlite)
    snapshot_db_path = Path(args.snapshot_db)
    if args.reset:
        _reset_file(sqlite_path, label="--sqlite")
        _reset_file(snapshot_db_path, label="--snapshot-db")

    result = run_7d(
        start_date=start,
        db_path=Path(args.sqlite),
        snapshot_db=Path(args.snapshot_db),
        run_prefix=str(args.run_prefix),
        odds_provider_name="sofascore",
        results_provider_name="sofascore",
        provider_json=provider_json,
        allow_synthetic_odds=False,
        decision_log_dir=Path(args.decision_log_dir),
        initial_bankroll=float(args.bankroll),
        out_dir=Path(args.out_dir),
    )

    summary = result["summary"]
    end_date = result["end_date"]
    summary_json = Path(args.out_dir) / f"paper_7d_summary_{end_date}.json"
    print(
        "[ONE-COMMAND] "
        f"final_pnl={summary['pnl']:.2f} "
        f"roi={summary['roi_pct']:.2f}% "
        f"max_dd={summary['max_drawdown_pct']:.2f}% "
        f"summary_json={summary_json}"
    )


if __name__ == "__main__":
    main()
