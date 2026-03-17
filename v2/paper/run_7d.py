from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from v2.config import settings_v2
from v2.paper.report import generate_reports, summarize_window_metrics
from v2.paper.run_day import _build_odds_provider, run_for_day
from v2.paper.settle import _build_results_provider, run_settlement


def _default_start_date_today_shanghai() -> date:
    tz = ZoneInfo("Asia/Shanghai")
    today_local = datetime.now(tz).date()
    # last 7 fully settled days ending yesterday -> start = yesterday - 6
    return today_local - timedelta(days=7)


def run_7d(
    start_date: date,
    db_path: Path,
    snapshot_db: Path,
    run_prefix: str,
    odds_provider_name: str = "espn",
    results_provider_name: str = "espn",
    provider_json: str = "",
    allow_synthetic_odds: bool = False,
    decision_log_dir: Path | None = None,
    initial_bankroll: float | None = None,
    out_dir: Path | None = None,
) -> dict:
    day_results: list[dict] = []
    bankroll0 = float(settings_v2.initial_bankroll if initial_bankroll is None else initial_bankroll)
    output_dir = Path("reports/v2") if out_dir is None else Path(out_dir)
    decision_output_dir = output_dir / "decisions" if decision_log_dir is None else Path(decision_log_dir)

    for i in range(7):
        day = start_date + timedelta(days=i)
        run_id = f"{run_prefix}_{day.isoformat()}"
        decision_log_path = None
        if decision_output_dir:
            decision_output_dir.mkdir(parents=True, exist_ok=True)
            decision_log_path = decision_output_dir / f"decisions_{day.isoformat()}.jsonl"

        selected = run_for_day(
            day=day,
            db_path=db_path,
            snapshot_db=snapshot_db,
            initial_bankroll=bankroll0,
            run_id=run_id,
            provider=_build_odds_provider(odds_provider_name, provider_json=provider_json),
            allow_synthetic_odds=allow_synthetic_odds,
            decision_log_path=decision_log_path,
        )
        print(f"[DAY {day.isoformat()}] select({odds_provider_name}) -> {selected}")

        settled = run_settlement(
            db_path=db_path,
            day=day,
            provider=_build_results_provider(results_provider_name, provider_json=provider_json),
        )
        print(f"[DAY {day.isoformat()}] settled({results_provider_name}) -> {settled}")

        daily, weekly = generate_reports(db_path=db_path, day=day, out_dir=output_dir)
        print(f"[DAY {day.isoformat()}] reports -> {daily.name}, {weekly.name}")

        day_results.append(
            {
                "day": day.isoformat(),
                "selection": selected,
                "settled_rows": settled,
                "daily_report": str(daily),
                "weekly_report": str(weekly),
            }
        )

    end_date = start_date + timedelta(days=6)
    summary = summarize_window_metrics(
        db_path=db_path,
        start=start_date,
        end=end_date,
        initial_bankroll=bankroll0,
    )

    final = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "run_prefix": run_prefix,
        "odds_provider": odds_provider_name,
        "results_provider": results_provider_name,
        "provider_json": provider_json,
        "allow_synthetic_odds": allow_synthetic_odds,
        "initial_bankroll": bankroll0,
        "days": day_results,
        "summary": summary,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_json = output_dir / f"paper_7d_summary_{end_date.isoformat()}.json"
    out_md = output_dir / f"paper_7d_summary_{end_date.isoformat()}.md"

    out_json.write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")

    md = (
        f"# Paper 7D Summary ({start_date.isoformat()} -> {end_date.isoformat()})\n\n"
        f"- Final PnL: {summary['pnl']:.2f}\n"
        f"- ROI: {summary['roi_pct']:.2f}%\n"
        f"- Max drawdown: {summary['max_drawdown_pct']:.2f}%\n"
        f"- Winrate: {summary['winrate_pct']:.2f}%\n"
        f"- Avg edge: {summary['avg_edge_pct']:.2f}%\n"
        f"- Bets: {summary['bets']}\n"
        f"- Starting bankroll: {summary['starting_bankroll']:.2f}\n"
        f"- Ending bankroll: {summary['ending_bankroll']:.2f}\n"
        f"\n## Baseline comparison\n"
        f"- Kelly-fraction PnL: {summary['pnl']:.2f}\n"
        f"- Flat-stake PnL: {summary['baseline_flat']['pnl']:.2f}\n"
        f"- Flat-stake ROI: {summary['baseline_flat']['roi_pct']:.2f}%\n"
        f"\n## By market type\n"
    )
    for row in summary["by_market"]:
        md += (
            f"- {row['market_type']}: bets={row['bets']}, pnl={row['pnl']:.2f}, "
            f"roi={row['roi_pct']:.2f}%, winrate={row['winrate_pct']:.2f}%, avg_edge={row['avg_edge_pct']:.2f}%\n"
        )
    out_md.write_text(md, encoding="utf-8")

    print(f"[7D SUMMARY] json={out_json} md={out_md}")
    print(
        "[7D SUMMARY] "
        f"final_pnl={summary['pnl']:.2f} roi={summary['roi_pct']:.2f}% "
        f"max_dd={summary['max_drawdown_pct']:.2f}% winrate={summary['winrate_pct']:.2f}%"
    )

    return final


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 7-day paper trading simulation")
    parser.add_argument("--start-date", default="", help="YYYY-MM-DD (default: last 7 settled days ending yesterday Asia/Shanghai)")
    parser.add_argument(
        "--sqlite",
        default=str(Path(settings_v2.tracking_sqlite_path)),
        help="tracking sqlite path",
    )
    parser.add_argument("--snapshot-db", default="data/v2/odds_snapshots.sqlite")
    parser.add_argument("--run-prefix", default="paper7d")
    parser.add_argument(
        "--provider-json",
        default="",
        help="optional deterministic provider fixture JSON for fixtures/odds/results replay",
    )
    parser.add_argument(
        "--allow-synthetic-odds",
        action="store_true",
        help="allow synthetic odds fallback when real odds are missing",
    )
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
    parser.add_argument(
        "--bankroll",
        type=float,
        default=float(settings_v2.initial_bankroll),
        help="initial bankroll for this run (default: INITIAL_BANKROLL env or 2000)",
    )
    args = parser.parse_args()

    if str(args.start_date).strip():
        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    else:
        start = _default_start_date_today_shanghai()

    run_7d(
        start,
        Path(args.sqlite),
        Path(args.snapshot_db),
        args.run_prefix,
        odds_provider_name=args.odds_provider,
        results_provider_name=args.results_provider,
        provider_json=str(args.provider_json or "").strip(),
        allow_synthetic_odds=bool(args.allow_synthetic_odds),
        decision_log_dir=Path(args.decision_log_dir) if str(args.decision_log_dir).strip() else None,
        initial_bankroll=args.bankroll,
        out_dir=Path(args.out_dir),
    )


if __name__ == "__main__":
    main()
