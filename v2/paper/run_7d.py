from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from statistics import mean
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
    closing_odds_tracker_sqlite: Path | None = None,
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
            closing_odds_tracker_sqlite=closing_odds_tracker_sqlite,
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
        f"- CLV sample size: {summary['clv_sample_size']}\n"
        f"- CLV coverage: {summary.get('clv_coverage_pct', 0.0):.2f}%\n"
        f"- Avg CLV (abs): {summary['avg_clv_abs']:.4f}\n"
        f"- Avg CLV (%): {summary['avg_clv_pct']:.2f}%\n"
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

    md += "\n## CLV by source_quality\n"
    clv_by_source = summary.get("clv_by_source_quality", [])
    if clv_by_source:
        for row in clv_by_source:
            md += (
                f"- {row['source_quality']} (close_odds={row.get('close_odds_source', 'none')}): clv_n={row['clv_sample_size']}, "
                f"avg_clv_abs={row['avg_clv_abs']:.4f}, avg_clv_pct={row['avg_clv_pct']:.2f}%\n"
            )
    else:
        md += "- (no CLV samples)\n"

    md += "\n## Closing odds coverage by source\n"
    close_cov = summary.get("close_odds_coverage", [])
    if close_cov:
        for row in close_cov:
            md += (
                f"- close_odds={row.get('close_odds_source', 'none')}: bets={int(row.get('bets', 0) or 0)}, "
                f"clv_n={int(row.get('clv_sample_size', 0) or 0)}, coverage={float(row.get('coverage_pct', 0.0)):.2f}%\n"
            )
    else:
        md += "- (no bets)\n"

    fallback_diag = summary.get("close_odds_fallback", {})
    md += "\n## Closing odds fallback diagnostics\n"
    md += f"- tracker_clv_sample_size: {int(fallback_diag.get('tracker_clv_sample_size', 0) or 0)}\n"
    md += f"- provider_fallback_clv_sample_size: {int(fallback_diag.get('provider_fallback_clv_sample_size', 0) or 0)}\n"
    md += f"- provider_fallback_share_pct_of_bets: {float(fallback_diag.get('provider_fallback_share_pct_of_bets', 0.0) or 0.0):.2f}%\n"
    md += f"- provider_fallback_share_pct_of_clv_samples: {float(fallback_diag.get('provider_fallback_share_pct_of_clv_samples', 0.0) or 0.0):.2f}%\n"
    md += f"- uncovered_bets: {int(fallback_diag.get('uncovered_bets', 0) or 0)}\n"
    md += f"- uncovered_pct: {float(fallback_diag.get('uncovered_pct', 0.0) or 0.0):.2f}%\n"

    out_md.write_text(md, encoding="utf-8")

    print(f"[7D SUMMARY] json={out_json} md={out_md}")
    print(
        "[7D SUMMARY] "
        f"final_pnl={summary['pnl']:.2f} roi={summary['roi_pct']:.2f}% "
        f"max_dd={summary['max_drawdown_pct']:.2f}% winrate={summary['winrate_pct']:.2f}%"
    )

    return final


def _window_inserted_kpi_aggregate(db_path: Path, start_date: date, end_date: date) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT
              COALESCE(league, 'UNKNOWN') AS league,
              COALESCE(market_type, 'UNKNOWN') AS strategy,
              COUNT(*) AS inserted_count,
              COALESCE(SUM(stake), 0) AS stake,
              COALESCE(SUM(CASE WHEN profit IS NULL THEN 0 ELSE profit END), 0) AS pnl,
              SUM(CASE WHEN lower(COALESCE(result,''))='win' THEN 1 ELSE 0 END) AS wins,
              SUM(CASE WHEN lower(COALESCE(result,''))='loss' THEN 1 ELSE 0 END) AS losses,
              SUM(CASE WHEN lower(COALESCE(result,''))='push' THEN 1 ELSE 0 END) AS pushes
            FROM bet_log
            WHERE substr(kickoff_time_hkt, 1, 10) BETWEEN ? AND ?
            GROUP BY COALESCE(league, 'UNKNOWN'), COALESCE(market_type, 'UNKNOWN')
            ORDER BY inserted_count DESC, league ASC, strategy ASC
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()

        out = []
        for r in rows:
            inserted_count = int(r[2] or 0)
            stake = float(r[3] or 0.0)
            pnl = float(r[4] or 0.0)
            wins = int(r[5] or 0)
            losses = int(r[6] or 0)
            pushes = int(r[7] or 0)
            out.append(
                {
                    "league": str(r[0]),
                    "strategy": str(r[1]),
                    "inserted_count": inserted_count,
                    "stake": stake,
                    "pnl": pnl,
                    "roi_pct": (pnl / stake) * 100.0 if stake > 0 else 0.0,
                    "wins": wins,
                    "losses": losses,
                    "pushes": pushes,
                    "winrate_pct": (wins / inserted_count) * 100.0 if inserted_count > 0 else 0.0,
                }
            )

        return {
            "kpi_basis": "inserted",
            "rows": out,
            "note": "KPI metrics (stake/pnl/roi/winrate) are computed from inserted rows in bet_log.",
        }
    finally:
        conn.close()


def run_walkforward(
    start_date: date,
    end_date: date,
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
    closing_odds_tracker_sqlite: Path | None = None,
) -> dict:
    windows: list[dict] = []
    cur = start_date
    output_dir = Path("reports/v2") if out_dir is None else Path(out_dir)

    while cur <= end_date:
        window = run_7d(
            start_date=cur,
            db_path=db_path,
            snapshot_db=snapshot_db,
            run_prefix=f"{run_prefix}_{cur.isoformat()}",
            odds_provider_name=odds_provider_name,
            results_provider_name=results_provider_name,
            provider_json=provider_json,
            allow_synthetic_odds=allow_synthetic_odds,
            decision_log_dir=decision_log_dir,
            initial_bankroll=initial_bankroll,
            out_dir=output_dir,
            closing_odds_tracker_sqlite=closing_odds_tracker_sqlite,
        )
        windows.append(window)
        cur = cur + timedelta(days=7)

    pnl_list = [float(w.get("summary", {}).get("pnl", 0.0)) for w in windows]
    roi_list = [float(w.get("summary", {}).get("roi_pct", 0.0)) for w in windows]
    dd_list = [float(w.get("summary", {}).get("max_drawdown_pct", 0.0)) for w in windows]
    wr_list = [float(w.get("summary", {}).get("winrate_pct", 0.0)) for w in windows]
    clv_list = [float(w.get("summary", {}).get("avg_clv_pct", 0.0)) for w in windows if int(w.get("summary", {}).get("clv_sample_size", 0)) > 0]

    selected_per_window: list[int] = []
    inserted_per_window: list[int] = []
    inserted_new_per_window: list[int] = []
    by_window_tag_rows: list[dict] = []
    league_counter: Counter[str] = Counter()
    strategy_counter: Counter[str] = Counter()

    for w in windows:
        days = w.get("days", [])
        selected_count = 0
        inserted_count = 0

        for d in days:
            sel = int(d.get("selection", {}).get("selected", 0) or 0)
            ins = int(d.get("selection", {}).get("inserted", 0) or 0)
            selected_count += sel
            inserted_count += ins

        start_s = str(w.get("start_date"))
        end_s = str(w.get("end_date"))
        ws = datetime.strptime(start_s, "%Y-%m-%d").date()
        we = datetime.strptime(end_s, "%Y-%m-%d").date()
        tags = _window_inserted_kpi_aggregate(db_path=db_path, start_date=ws, end_date=we)

        for row in tags.get("rows", []):
            lg = str(row.get("league", "UNKNOWN"))
            st = str(row.get("strategy", "UNKNOWN"))
            ic = int(row.get("inserted_count", 0) or 0)
            league_counter[lg] += ic
            strategy_counter[st] += ic

        # attach selected_count at window level and annotate selected_count on tag rows as helper
        w["selected_count"] = selected_count
        w["inserted_new_count"] = inserted_count
        w["inserted_count"] = int(w.get("summary", {}).get("bets", 0) or 0)
        w["inserted_kpi_tags"] = tags
        window_inserted_total = int(w.get("summary", {}).get("bets", 0) or 0)
        by_window_tag_rows.append(
            {
                "window_start": start_s,
                "window_end": end_s,
                "selected_count": selected_count,
                "inserted_count": window_inserted_total,
                "inserted_new_count": inserted_count,
                "kpi_basis": "inserted",
                "rows": tags.get("rows", []),
            }
        )
        selected_per_window.append(selected_count)
        inserted_per_window.append(window_inserted_total)
        inserted_new_per_window.append(inserted_count)

    agg = {
        "windows": len(windows),
        "window_start": start_date.isoformat(),
        "window_end": end_date.isoformat(),
        "kpi_basis": "inserted",
        "total_pnl": sum(pnl_list) if pnl_list else 0.0,
        "avg_pnl": mean(pnl_list) if pnl_list else 0.0,
        "avg_roi_pct": mean(roi_list) if roi_list else 0.0,
        "avg_max_drawdown_pct": mean(dd_list) if dd_list else 0.0,
        "avg_winrate_pct": mean(wr_list) if wr_list else 0.0,
        "avg_clv_pct": mean(clv_list) if clv_list else 0.0,
        "positive_windows": sum(1 for x in pnl_list if x > 0),
        "total_selected_count": sum(selected_per_window),
        "total_inserted_count": sum(inserted_per_window),
        "total_inserted_new_count": sum(inserted_new_per_window),
        "selection_insertion_gap": sum(selected_per_window) - sum(inserted_per_window),
        "selection_new_insertion_gap": sum(selected_per_window) - sum(inserted_new_per_window),
        "dedupe_behavior": {
            "root_cause": "bet_log.bet_id is UNIQUE and ledger uses INSERT OR IGNORE on reruns",
            "effect": "rerun can produce selected_count > inserted_new_count because already-existing bet_id rows are ignored",
            "metric_definition": {
                "inserted_count": "total rows in bet_log within window (KPI basis)",
                "inserted_new_count": "rows newly inserted during this run",
                "selected_count": "strategy selected candidates before DB dedupe",
            },
        },
    }

    payload = {
        "aggregate": agg,
        "windows": windows,
        "by_window_league_strategy": by_window_tag_rows,
        "by_league_inserted": [{"league": k, "inserted_count": v} for k, v in league_counter.most_common()],
        "by_strategy_inserted": [{"strategy": k, "inserted_count": v} for k, v in strategy_counter.most_common()],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    out_json = output_dir / f"paper_walkforward_{start_date.isoformat()}_{end_date.isoformat()}.json"
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[WALKFORWARD] json={out_json} windows={agg['windows']} total_pnl={agg['total_pnl']:.2f} avg_roi={agg['avg_roi_pct']:.2f}%")
    return payload


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
    parser.add_argument(
        "--walkforward-end-date",
        default="",
        help="optional YYYY-MM-DD; when set, runs rolling 7-day windows from --start-date to this end date",
    )
    parser.add_argument(
        "--closing-odds-tracker-sqlite",
        default="",
        help="optional OddsPortal tracker sqlite for closing-odds hook",
    )
    args = parser.parse_args()

    if str(args.start_date).strip():
        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    else:
        start = _default_start_date_today_shanghai()

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
            initial_bankroll=args.bankroll,
            out_dir=Path(args.out_dir),
            closing_odds_tracker_sqlite=closing_tracker,
        )
        return

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
        closing_odds_tracker_sqlite=closing_tracker,
    )


if __name__ == "__main__":
    main()
