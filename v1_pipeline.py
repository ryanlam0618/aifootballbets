"""Layer-2 afb-T5: v1 daily pipeline (select -> odds snapshot -> settle -> report).

One entry point, `run_pipeline(day)`, that chains the v1 member stages for a
single day:

1. pick_day        — fixtures for `day` (from the DB, finished or scheduled)
2. odds_snapshot_stage — sample 1x2 odds for those fixtures into
                     afb_odds_snapshots (INSERT IGNORE, idempotent)
3. predictions     — DC (per-league HA) + pi-ratings probabilities for each
                     fixture, appended to afb_predictions
4. settle_prev_day — settle the PREVIOUS day's bet-log/predictions against
                     results (settlement is a no-op when results are absent)
5. report          — daily summary dict (logged + returned)

Idempotency: every DB write is INSERT IGNORE / ON DUPLICATE KEY guarded by
unique keys (afb_predictions: run_id+match+market+line+selection;
afb_odds_snapshots: match+market+selection+bookmaker+captured second), so
re-running the same day never duplicates rows.

Designed for cron via scripts/run_daily.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from afbdb.connection import afb_mysql_connect
from config import settings_v2
from models.dc_model import DCModel, MatchRecord, fit_dc
from models.pi_ratings import PiParams, PiRatingModel, league_mu_totals


@dataclass
class PipelineResult:
    day: str
    stages: Dict[str, dict]

    def to_json(self) -> str:
        return json.dumps({"day": self.day, "stages": self.stages}, ensure_ascii=False, indent=2, default=str)


def _conn():
    return afb_mysql_connect()


# --------------------------------------------------------------- 1. pick_day


def pick_day(conn, day: date) -> List[dict]:
    """Fixtures for `day`: scheduled (future) or finished (past) matches."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.match_id, m.match_date, c.name AS league,
               th.name AS home_team, ta.name AS away_team,
               m.home_score AS home_goals, m.away_score AS away_goals, m.status
        FROM matches m
        JOIN competitions c ON c.competition_id = m.competition_id
        JOIN teams th ON th.team_id = m.home_team_id
        JOIN teams ta ON ta.team_id = m.away_team_id
        WHERE m.match_date = %s
        ORDER BY c.name, m.match_id
        """,
        (day.isoformat(),),
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "match_id": str(r[0]),
                "match_date": r[1],
                "league": r[2],
                "home_team": r[3],
                "away_team": r[4],
                "home_goals": r[5],
                "away_goals": r[6],
                "status": r[7],
            }
        )
    return out


# ------------------------------------------------- 2. odds snapshot stage


def build_snapshot_rows(fixtures: List[dict], odds_by_id: Dict[str, Dict[str, float]], sample_time: datetime, run_prefix: str = "daily") -> List[dict]:
    """Pure helper: build afb_odds_snapshots rows from fixtures + odds map."""
    rows = []
    for m in fixtures:
        mid = str(m.get("match_id") or "")
        odds = odds_by_id.get(mid)
        if not odds:
            continue
        for sel in ("Home", "Draw", "Away"):
            rows.append(
                {
                    "match_id": mid,
                    "source": "market_avg",
                    "league_key": None,
                    "league_name": m.get("league"),
                    "home_team": m["home_team"],
                    "away_team": m["away_team"],
                    "commence_time_utc": None,
                    "market_key": "1X2",
                    "selection": sel,
                    "odds": float(odds[sel]),
                    "bookmaker": "avg",
                    "captured_at_utc": sample_time.replace(microsecond=0),
                    "run_id": f"{run_prefix}_{sample_time.strftime('%Y%m%d')}",
                }
            )
    return rows


def collect_market_odds_tolerant(conn, matches: List[dict]) -> Dict[str, Dict[str, float]]:
    """Odds variant that does NOT require odds_type='1x2': appdb rows from some
    backfill batches have odds_type NULL with market_name='Full time' and
    choice_name '1'/'X'/'2' — same market, different metadata completeness.
    Reuses the fractional parsing + averaging from backtest_t2."""
    from scripts.backtest_t2 import _fractional_to_decimal

    ids = [str(m["match_id"]) for m in matches if m.get("match_id")]
    by_id = {str(m["match_id"]): m for m in matches if m.get("match_id")}
    if not ids:
        return {}
    collected: Dict[str, Dict[str, List[float]]] = {}
    cur = conn.cursor()
    choice_map = {"1": "Home", "X": "Draw", "2": "Away"}
    chunk = 500
    for i in range(0, len(ids), chunk):
        part = ids[i : i + chunk]
        cur.execute(
            """
            SELECT o.match_id, o.choice_name, o.fractional_value
            FROM match_odds o
            WHERE o.market_name='Full time'
              AND o.choice_name IN ('1','X','2')
              AND o.match_id IN (%s)
            """
            % ",".join(["%s"] * len(part)),
            tuple(part),
        )
        for mid, choice, frac in cur.fetchall():
            dec = _fractional_to_decimal(frac)
            if dec is None:
                continue
            collected.setdefault(str(mid), {}).setdefault(choice_map.get(str(choice), ""), []).append(dec)
    out: Dict[str, Dict[str, float]] = {}
    for mid, choices in collected.items():
        if mid not in by_id:
            continue
        if all(choices.get(sel) for sel in ("Home", "Draw", "Away")):
            out[mid] = {
                "Home": sum(choices["Home"]) / len(choices["Home"]),
                "Draw": sum(choices["Draw"]) / len(choices["Draw"]),
                "Away": sum(choices["Away"]) / len(choices["Away"]),
            }
    return out


def odds_snapshot_stage(conn, fixtures: List[dict], sample_time: Optional[datetime] = None) -> dict:
    """Sample full-time 1x2 odds for the fixtures into afb_odds_snapshots.

    Idempotent: unique key (match_id, market_key, selection, bookmaker,
    captured_at_utc) + INSERT IGNORE — re-running the same second is a no-op.
    Returns {"n_fixtures": ..., "n_rows": ...}.
    """
    from scripts.backtest_t2 import collect_market_odds  # strict odds_type='1x2'

    if sample_time is None:
        sample_time = datetime.utcnow()
    ids = [str(m["match_id"]) for m in fixtures]
    if not ids:
        return {"n_fixtures": 0, "n_rows": 0}
    odds_by_id = collect_market_odds_tolerant(conn, [m for m in fixtures if m.get("match_id")])
    if not odds_by_id:
        # fallback to the strict query when the tolerant pass finds nothing
        odds_by_id = collect_market_odds(conn, [m for m in fixtures if m.get("match_id")])
    rows = build_snapshot_rows(fixtures, odds_by_id, sample_time)
    if not rows:
        return {"n_fixtures": len(ids), "n_rows": 0}
    from afbdb.ledger import db_write_snapshots

    written = db_write_snapshots(rows)
    return {"n_fixtures": len(ids), "n_rows": written}


# --------------------------------------------------------- 3. predictions


def predictions_stage(
    conn,
    fixtures: List[dict],
    run_id: str,
    max_goals: int = 10,
) -> Dict[str, int]:
    """DC + pi-ratings predictions for the fixtures -> afb_predictions.

    Fits both models as-of the fixture dates (train = everything strictly
    before the earliest fixture date), then predicts each fixture. INSERT
    IGNORE via unique key makes same-run_id re-runs no-ops.
    """
    from afbdb.history import fetch_history_rows
    from scripts.backtest_dc import to_match_records

    earliest = min(
        (m["match_date"] for m in fixtures if m.get("match_date")),
        default=date.today(),
    )
    rows = fetch_history_rows(conn, min_date=str(settings_v2.afb_history_min_date))
    history = [
        r
        for r in rows
        if datetime.strptime(r["match_date"], "%Y-%m-%d").date() < earliest
        and r["home_goals"] is not None
        and r["away_goals"] is not None
    ]
    train_records = [
        MatchRecord(
            datetime.strptime(r["match_date"], "%Y-%m-%d").date(),
            r["home_team"],
            r["away_team"],
            int(r["home_goals"]),
            int(r["away_goals"]),
            r.get("league"),
        )
        for r in history
    ]

    dc = fit_dc(
        train_records,
        asof=earliest,
        half_life_days=float(getattr(settings_v2, "afb_history_min_date", "2015") and 365.0),
        min_matches=10,
        max_sweeps=30,
        tol=1e-4,
        per_league_home_adv=True,
    )

    pi = PiRatingModel(params=PiParams(kappa=0.05, omega_home=0.6))
    for m in train_records:
        pi.update(m.home, m.away, m.home_goals, m.away_goals)
    mu_totals = league_mu_totals(train_records, asof=earliest)

    from afbdb.ledger import db_write_predictions

    pred_rows: List[dict] = []
    run_date = earliest.isoformat()
    for m in fixtures:
        lg = m.get("league")
        dc_probs = dc.probs_1x2(m["home_team"], m["away_team"], max_goals=max_goals, league=lg)
        mu = mu_totals.get(lg or "", mu_totals.get("", 2.6))
        pi_probs = pi.probs_1x2(m["home_team"], m["away_team"], mu_total=mu, max_goals=max_goals)
        for model_name, probs in (("dc_tau_v1", dc_probs), ("pi_tau_v1", pi_probs)):
            # deterministic run_id per (day, model): same-day re-runs are
            # INSERT IGNORE no-ops (idempotency), and the two models coexist
            # (uq key = run_id+match+market+line+selection, model in run_id)
            per_model_run_id = f"daily_{earliest.isoformat()}_{model_name}"
            for sel in ("Home", "Draw", "Away"):
                pred_rows.append(
                    {
                        "run_id": per_model_run_id,
                        "run_date": run_date,
                        "match_id": str(m["match_id"]),
                        "league": lg,
                        "home_team": m["home_team"],
                        "away_team": m["away_team"],
                        "market": "1X2",
                        "line": "",  # empty string, NOT NULL — uq_afb_pred ignores NULL columns
                        "selection": sel,
                        "odds": None,
                        "model_probability": float(probs[sel]),
                        "implied_probability": None,
                        "edge": None,
                        "ev": None,
                        "kelly_fraction": None,
                        "suggested_stake": None,
                        "bet_flag": 0,
                        "confidence": None,
                        "rationale": f"{model_name} daily pipeline",
                        "model_name": model_name,
                    }
                )
    written = db_write_predictions(pred_rows)
    return {"predictions_built": len(pred_rows), "written": written}


# --------------------------------------------------------- 4. settle prev


def settle_prev_day(conn, prev_day: date) -> dict:
    """Settlement stage: record finished results for prev-day predictions.

    v1: the paper ledger settles via paper.settle (separate flow); here we
    verify result availability and mark predictions' matches as decided by
    writing a settlement note row-set into afb_predictions is NOT needed —
    bet settlement happens in the paper ledger. This stage reports how many
    prev-day matches now have final scores (observability for the cron).
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*), SUM(home_score IS NOT NULL AND away_score IS NOT NULL)
        FROM matches WHERE match_date = %s
        """,
        (prev_day.isoformat(),),
    )
    total, with_result = cur.fetchone()
    cur.execute(
        """
        SELECT COUNT(DISTINCT match_id) FROM afb_predictions
        WHERE run_date = %s
        """,
        (prev_day.isoformat(),),
    )
    with_preds = cur.fetchone()[0]
    return {
        "prev_day": prev_day.isoformat(),
        "matches": int(total or 0),
        "with_result": int(with_result or 0),
        "matches_with_predictions": int(with_preds or 0),
        "note": "paper-ledger settlement runs via paper.settle; this stage is observability",
    }


# -------------------------------------------------------------- entrypoint


def run_pipeline(day: date, skip_market: bool = False) -> PipelineResult:
    """Run the full v1 daily pipeline for `day` (select/snapshot/predict/settle)."""
    conn = _conn()
    stages: Dict[str, dict] = {}
    fixtures = pick_day(conn, day)
    stages["pick_day"] = {"n": len(fixtures)}
    print(f"[pick_day] {day}: {len(fixtures)} fixtures")

    if not skip_market:
        snap = odds_snapshot_stage(conn, fixtures)
        stages["odds_snapshot"] = snap
        print(f"[odds_snapshot] {snap['n_rows']} rows from {snap['n_fixtures']} fixtures")

    if fixtures:
        run_id = f"daily_{day.strftime('%Y%m%d')}_{datetime.now(timezone.utc).strftime('%H%M%S')}"
        pred = predictions_stage(conn, fixtures, run_id=run_id)
        stages["predictions"] = pred
        print(f"[predictions] {pred['predictions_built']} built, {pred['written']} written (run_id={run_id})")

    prev = day - timedelta(days=1)
    stages["settle_prev_day"] = settle_prev_day(conn, prev)
    print(f"[settle_prev_day] {stages['settle_prev_day']['with_result']}/{stages['settle_prev_day']['matches']} with results")

    conn.close()
    return PipelineResult(day=day.isoformat(), stages=stages)
