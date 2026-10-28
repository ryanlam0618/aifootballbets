#!/usr/bin/env python3
"""Layer-2 T1: Dixon-Coles day runner — fit as-of a date, predict upcoming
fixtures from appdb, write 1X2 + AH(0/0.25/0.5/0.75/1) to afb_predictions
(model_name='dc_tau_v1').

Usage:
    python scripts/run_dc_predictions.py --date 2026-10-31
    python scripts/run_dc_predictions.py --date 2026-10-31 --fit-xi
    python scripts/run_dc_predictions.py --date 2026-10-31 \
        --leagues "Premier League,La Liga"

Read-only on sofascore-backfill tables (matches / teams / competitions);
writes only afb_predictions. History is as-of the run date (strictly earlier
matches), so runs are walk-forward reproducible.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402
from afbdb.ledger import db_write_predictions  # noqa: E402
from afbdb.history import fetch_history_rows  # noqa: E402
from config import settings_v2  # noqa: E402
from models.dc_model import (  # noqa: E402
    DCModel,
    MatchRecord,
    fit_dc,
    fit_half_life_by_validation,
)

MODEL_NAME = "dc_tau_v1"

# paper pipeline league universe (paper/constants.LEAGUE_UNIVERSE names)
DEFAULT_LEAGUES = (
    "Premier League",
    "La Liga",
    "Serie A",
    "Bundesliga",
    "Ligue 1",
    "J1 League",
    "K League 1",
    "A-League Men",
    "Chinese Super League",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Dixon-Coles (dc_tau_v1) day runner")
    p.add_argument("--date", type=str, default=None, help="prediction date YYYY-MM-DD (default: tomorrow UTC)")
    p.add_argument("--leagues", type=str, default=None, help="comma-separated competition names (default: paper universe)")
    p.add_argument("--all-leagues", action="store_true", help="predict every competition scheduled that date")
    p.add_argument("--half-life", type=float, default=365.0, help="time-decay half-life in days (default 365)")
    p.add_argument("--fit-xi", action="store_true", help="choose half-life by hold-out validation")
    p.add_argument("--min-matches", type=int, default=10, help="min matches in window for team params (default 10)")
    p.add_argument("--max-goals", type=int, default=10)
    p.add_argument(
        "--status",
        type=str,
        default="scheduled",
        choices=["scheduled", "finished", "postponed", "all"],
        help="fixture status to predict (default scheduled; use finished for backtest runs)",
    )
    p.add_argument("--dry-run", action="store_true", help="fit + predict but skip DB write")
    return p.parse_args()


def load_history(asof: date) -> list[MatchRecord]:
    rows = fetch_history_rows(
        __import__("afbdb.connection", fromlist=["afb_mysql_connect"]) and _conn(),
        min_date=str(settings_v2.afb_history_min_date),
    )
    out: list[MatchRecord] = []
    for r in rows:
        try:
            out.append(
                MatchRecord(
                    match_date=datetime.strptime(r["match_date"], "%Y-%m-%d").date(),
                    home=r["home_team"],
                    away=r["away_team"],
                    home_goals=int(r["home_goals"]),
                    away_goals=int(r["away_goals"]),
                )
            )
        except (TypeError, ValueError):
            continue
    del asof
    return out


def _conn():
    return afb_mysql_connect()


def fetch_fixtures(conn, run_date: date, leagues: list[str] | None, status: str) -> list[dict]:
    sql = """
        SELECT m.match_id, m.match_date, c.name AS league,
               th.name AS home_team, ta.name AS away_team
        FROM matches m
        JOIN competitions c ON c.competition_id = m.competition_id
        JOIN teams th ON th.team_id = m.home_team_id
        JOIN teams ta ON ta.team_id = m.away_team_id
        WHERE m.match_date = %s
    """
    params: list = [run_date.isoformat()]
    if status != "all":
        sql += " AND m.status = %s"
        params.append(status)
    if leagues:
        sql += f" AND c.name IN ({','.join(['%s'] * len(leagues))})"
        params.extend(leagues)
    sql += " ORDER BY c.name, m.match_id"
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return [
            {
                "match_id": str(r[0]),
                "match_date": r[1],
                "league": r[2],
                "home_team": r[3],
                "away_team": r[4],
            }
            for r in cur.fetchall()
        ]


def build_prediction_rows(model: DCModel, fixtures: list[dict], run_id: str) -> list[dict]:
    run_date = datetime.utcnow().date().isoformat()
    rows: list[dict] = []
    for fx in fixtures:
        try:
            markets = model.predict_markets(fx["home_team"], fx["away_team"])
        except Exception as exc:
            print(f"[WARN] predict failed for {fx['home_team']} vs {fx['away_team']}: {exc}")
            continue
        for mk in markets:
            rows.append(
                {
                    "run_id": run_id,
                    "run_date": run_date,
                    "match_id": fx["match_id"],
                    "league": fx["league"],
                    "home_team": fx["home_team"],
                    "away_team": fx["away_team"],
                    "market": mk["market"],
                    "line": mk["line"],
                    "selection": mk["selection"],
                    "odds": None,
                    "model_probability": float(mk["model_probability"]),
                    "implied_probability": None,
                    "edge": None,
                    "ev": None,
                    "kelly_fraction": None,
                    "suggested_stake": None,
                    "bet_flag": 0,
                    "confidence": None,
                    "rationale": mk["rationale"],
                    "model_name": MODEL_NAME,
                }
            )
    return rows


def main() -> int:
    args = parse_args()
    run_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else (datetime.utcnow() + timedelta(days=1)).date()
    )

    leagues: list[str] | None = None
    if not args.all_leagues:
        leagues = (
            [s.strip() for s in args.leagues.split(",") if s.strip()]
            if args.leagues
            else list(DEFAULT_LEAGUES)
        )

    conn = _conn()
    print(f"[1] connected; run_date={run_date} leagues={'ALL' if leagues is None else len(leagues)}")

    history = load_history(run_date)
    print(f"[2] history: {len(history)} finished matches (as-of {run_date})")
    if len(history) < 200:
        print("[WARN] suspiciously little history; check DB")

    half_life = args.half_life
    if args.fit_xi:
        half_life, report = fit_half_life_by_validation(history, min_matches=args.min_matches)
        pretty = {f"{k:g}d": f"{v:.4f}" for k, v in report.items()}
        print(f"[2b] fit-xi validation loglik: {pretty} -> half_life={half_life:g}d")

    print(f"[3] fitting Dixon-Coles (half_life={half_life:g}d, min_matches={args.min_matches}) ...")
    model = fit_dc(
        history,
        asof=run_date,
        half_life_days=half_life,
        min_matches=args.min_matches,
    )
    print(
        f"[3] fit done: {model.n_matches} matches, {model.n_teams} teams, "
        f"rho={model.rho:+.3f}, home_adv={model.home_adv:+.3f}, "
        f"avg loglik={model.loglik_per_match:.4f}"
    )

    fixtures = fetch_fixtures(conn, run_date, leagues, args.status)
    print(f"[4] fixtures on {run_date} (status={args.status}): {len(fixtures)}")
    if not fixtures:
        print("[WARN] no scheduled fixtures found for this date/leagues; nothing written")
        return 0

    run_id = f"dc_{run_date.strftime('%Y%m%d')}_{datetime.utcnow().strftime('%H%M%S')}"
    rows = build_prediction_rows(model, fixtures, run_id)
    n_1x2 = sum(1 for r in rows if r["market"] == "1X2")
    n_ah = sum(1 for r in rows if r["market"] == "Asian Handicap")
    print(f"[5] predictions built: {len(rows)} rows ({n_1x2} 1X2 + {n_ah} AH), run_id={run_id}")

    sample = fixtures[0]
    probs = model.probs_1x2(sample["home_team"], sample["away_team"])
    print(
        f"[5] sample: {sample['home_team']} vs {sample['away_team']} -> "
        f"H={probs['Home']:.3f} D={probs['Draw']:.3f} A={probs['Away']:.3f}"
    )

    if args.dry_run:
        print("[6] dry-run: skip DB write")
        return 0

    written = db_write_predictions(rows)
    print(f"[6] afb_predictions written: {written} rows (model_name={MODEL_NAME})")

    # End this connection's open transaction so the readback below starts a
    # fresh snapshot (REPEATABLE READ would otherwise not see the rows
    # committed by db_write_predictions' own connection).
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM afb_predictions WHERE run_id=%s AND model_name=%s",
            (run_id, MODEL_NAME),
        )
        back = cur.fetchone()[0]
    print(f"[7] readback: {back} rows in afb_predictions for run_id={run_id}")
    conn.close()
    print("DC RUN OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
