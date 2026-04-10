#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from v2.paper.constants import FIXTURES_LEAGUE_UNIVERSE
from v2.paper.historical_provider import HistoricalBackfillProvider, HistoricalMySQLProvider
from v2.paper.report import summarize_window_metrics
from v2.paper.run_day import run_for_day
from v2.paper.settle import run_settlement


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _season_bounds(season: str) -> tuple[date, date]:
    s = str(season or "").strip()
    if not s or "-" not in s:
        raise ValueError("season must look like YYYY-YYYY, e.g. 2024-2025")
    a, b = s.split("-", 1)
    y1 = int(a)
    y2 = int(b)
    return date(y1, 7, 1), date(y2, 6, 30)


def _collect_selected_counts(days: list[dict]) -> dict:
    matches = sum(int((d.get("selection") or {}).get("matches", 0) or 0) for d in days)
    candidates = sum(int((d.get("selection") or {}).get("candidates", 0) or 0) for d in days)
    selected = sum(int((d.get("selection") or {}).get("selected", 0) or 0) for d in days)
    inserted = sum(int((d.get("selection") or {}).get("inserted", 0) or 0) for d in days)
    return {
        "matches": matches,
        "candidates": candidates,
        "selected": selected,
        "inserted": inserted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate paper model on a historical season using backfill dbs")
    parser.add_argument("--season", default="2024-2025")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--sqlite", default="data/v2/backtest_2024_2025.sqlite")
    parser.add_argument("--snapshot-db", default="data/v2/backtest_2024_2025_snap.sqlite")
    parser.add_argument("--out-dir", default="reports/v2/historical_validation")
    parser.add_argument("--bankroll", type=float, default=2000.0)
    parser.add_argument("--model", default="team_strength")
    parser.add_argument("--matches-sqlite", default="data/backfill_sofascore_10y/backfill_10y.sqlite")
    parser.add_argument("--odds-sqlite", default="data/backfill_sofascore_10y/event_odds_10y.sqlite")
    parser.add_argument("--use-open-odds", action="store_true", default=True)
    parser.add_argument("--use-close-odds", action="store_true")
    parser.add_argument("--allow-synthetic-odds", action="store_true")
    parser.add_argument("--max-days", type=int, default=0, help="optional limit for smoke runs")
    parser.add_argument("--resume", action="store_true", help="skip days that already have settled/open rows in sqlite")
    parser.add_argument("--stop-on-error", action="store_true", help="raise immediately on the first per-day exception")
    parser.add_argument("--competition-scope", choices=["league-only", "league-and-cups"], default="league-only")
    parser.add_argument("--league-keys", default="", help="optional comma-separated explicit league keys override")
    parser.add_argument("--historical-source", choices=["sqlite", "mysql"], default="sqlite")
    parser.add_argument("--mysql-host", default=os.getenv("SOFASCORE_MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--mysql-port", type=int, default=int(os.getenv("SOFASCORE_MYSQL_PORT", "3306")))
    parser.add_argument("--mysql-user", default=os.getenv("SOFASCORE_MYSQL_USER", "root"))
    parser.add_argument("--mysql-password", default=os.getenv("SOFASCORE_MYSQL_PASSWORD", ""))
    parser.add_argument("--mysql-database", default=os.getenv("SOFASCORE_MYSQL_DATABASE", "appdb"))
    args = parser.parse_args()

    season_start, season_end = _season_bounds(args.season)
    start = datetime.strptime(args.start_date, "%Y-%m-%d").date() if str(args.start_date).strip() else season_start
    end = datetime.strptime(args.end_date, "%Y-%m-%d").date() if str(args.end_date).strip() else season_end
    use_open_odds = not bool(args.use_close_odds)

    os.environ["PAPER_MODEL_NAME"] = str(args.model)
    if str(args.league_keys).strip():
        active_league_keys = [x.strip() for x in str(args.league_keys).split(",") if x.strip()]
    elif args.competition_scope == "league-and-cups":
        active_league_keys = list(FIXTURES_LEAGUE_UNIVERSE)
    else:
        active_league_keys = None

    if args.historical_source == "mysql":
        provider = HistoricalMySQLProvider(
            host=str(args.mysql_host),
            port=int(args.mysql_port),
            user=str(args.mysql_user),
            password=str(args.mysql_password),
            database=str(args.mysql_database),
            use_open_odds=use_open_odds,
        )
    else:
        provider = HistoricalBackfillProvider(
            matches_sqlite=Path(args.matches_sqlite),
            odds_sqlite=Path(args.odds_sqlite),
            use_open_odds=use_open_odds,
        )

    db_path = Path(args.sqlite)
    snapshot_db = Path(args.snapshot_db)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "decisions").mkdir(parents=True, exist_ok=True)
    error_log_path = out_dir / "errors.jsonl"

    import sqlite3

    def _has_any_rows_for_day(day: date) -> bool:
        if not db_path.exists():
            return False
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM bet_log WHERE substr(kickoff_time_hkt, 1, 10) = ?",
                (day.isoformat(),),
            ).fetchone()
            return bool((row or [0])[0])
        finally:
            conn.close()

    days: list[dict] = []
    processed = 0
    last_attempted_day: date | None = None
    for day in _daterange(start, end):
        if args.max_days and processed >= int(args.max_days):
            break
        if args.resume and _has_any_rows_for_day(day):
            print(f"[HIST {day.isoformat()}] skip=resume_existing_rows")
            days.append({"day": day.isoformat(), "selection": {}, "settled": 0, "skipped": "resume_existing_rows"})
            processed += 1
            last_attempted_day = day
            continue
        try:
            sel = run_for_day(
                day=day,
                db_path=db_path,
                snapshot_db=snapshot_db,
                initial_bankroll=float(args.bankroll),
                run_id=f"hist_{args.model}_{day.isoformat()}",
                provider=provider,
                allow_synthetic_odds=bool(args.allow_synthetic_odds),
                decision_log_path=out_dir / "decisions" / f"decisions_{day.isoformat()}.jsonl",
                league_keys=active_league_keys,
            )
            settled = run_settlement(
                db_path=db_path,
                day=day,
                provider=provider,
                closing_odds_tracker_sqlite=None,
                league_keys=active_league_keys,
            )
            if sel.get("matches") or sel.get("inserted") or settled:
                print(f"[HIST {day.isoformat()}] select={sel.get('inserted', 0)} settle={settled} matches={sel.get('matches', 0)}")
            days.append({"day": day.isoformat(), "selection": sel, "settled": settled})
            processed += 1
            last_attempted_day = day
        except Exception as e:
            err = {"day": day.isoformat(), "error": repr(e), "model": args.model}
            with error_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(err, ensure_ascii=False) + "\n")
            print(f"[HIST ERROR {day.isoformat()}] {e!r}")
            last_attempted_day = day
            if args.stop_on_error:
                raise
            continue

    effective_end = last_attempted_day or start
    summary = summarize_window_metrics(
        db_path=db_path,
        start=start,
        end=effective_end,
        initial_bankroll=float(args.bankroll),
    )

    payload = {
        "season": args.season,
        "start_date": start.isoformat(),
        "end_date": effective_end.isoformat(),
        "model": args.model,
        "use_open_odds": use_open_odds,
        "historical_source": args.historical_source,
        "mysql_database": args.mysql_database if args.historical_source == "mysql" else "",
        "competition_scope": args.competition_scope,
        "league_keys": active_league_keys or [],
        "bankroll": float(args.bankroll),
        "selection_totals": _collect_selected_counts(days),
        "summary": summary,
    }

    tag = f"{args.model}_{start.isoformat()}_{effective_end.isoformat()}"
    json_path = out_dir / f"historical_validation_{tag}.json"
    md_path = out_dir / f"historical_validation_{tag}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        f"# Historical Validation ({start.isoformat()} -> {effective_end.isoformat()})",
        "",
        f"- Season: {args.season}",
        f"- Model: `{args.model}`",
        f"- Odds basis: {'open' if use_open_odds else 'close'}",
        f"- Matches seen: {payload['selection_totals']['matches']}",
        f"- Candidates: {payload['selection_totals']['candidates']}",
        f"- Bets selected: {payload['selection_totals']['selected']}",
        f"- Bets inserted: {payload['selection_totals']['inserted']}",
        "",
        "## Summary",
        f"- PnL: {summary['pnl']:.2f}",
        f"- ROI: {summary['roi_pct']:.2f}%",
        f"- Max drawdown: {summary['max_drawdown_pct']:.2f}%",
        f"- Winrate: {summary['winrate_pct']:.2f}%",
        f"- Avg edge: {summary['avg_edge_pct']:.2f}%",
        f"- Avg CLV: {summary['avg_clv_pct']:.2f}%",
        f"- Bets: {summary['bets']}",
        f"- Ending bankroll: {summary['ending_bankroll']:.2f}",
        "",
        "## By market",
    ]
    for row in summary.get("by_market", []):
        md.append(
            f"- {row['market_type']}: bets={row['bets']}, pnl={row['pnl']:.2f}, roi={row['roi_pct']:.2f}%, winrate={row['winrate_pct']:.2f}%"
        )
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"[HIST SUMMARY] json={json_path} md={md_path}")
    print(
        f"[HIST SUMMARY] model={args.model} bets={summary['bets']} pnl={summary['pnl']:.2f} roi={summary['roi_pct']:.2f}% max_dd={summary['max_drawdown_pct']:.2f}%"
    )


if __name__ == "__main__":
    main()
