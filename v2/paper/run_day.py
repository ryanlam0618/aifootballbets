from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

from v2.config import settings_v2
from v2.paper.constants import LEAGUE_UNIVERSE
from v2.paper.ledger import append_selected_bets, bankroll_before_day
from v2.paper.models import CandidateBet, MatchInfo
from v2.paper.providers import OddsApiEspnPlaceholderProvider
from v2.paper.staking import DailyRiskManager, make_selected_bet
from v2.paper.strategy import generate_candidates_for_match, select_best_per_match


def _league_name_rank(matches: List[MatchInfo]) -> Dict[str, int]:
    # combined rank universe by league, but one global strategy pool
    order = {lk: i for i, lk in enumerate(LEAGUE_UNIVERSE)}
    return {m.match_id: order.get(m.league_key, 999) for m in matches}


def run_for_day(
    day: date,
    db_path: Path,
    snapshot_db: Path,
    initial_bankroll: float,
    run_id: str,
) -> dict:
    provider = OddsApiEspnPlaceholderProvider(snapshot_db=snapshot_db)

    matches = provider.fetch_matches(day=day, league_keys=LEAGUE_UNIVERSE)
    if not matches:
        return {"matches": 0, "candidates": 0, "selected": 0, "inserted": 0, "risk_stop": False}

    odds_map = provider.fetch_market_odds(day=day, league_keys=LEAGUE_UNIVERSE, matches=matches)

    all_candidates: List[CandidateBet] = []
    for m in matches:
        all_candidates.extend(generate_candidates_for_match(m, odds_map=odds_map))

    best_by_match = select_best_per_match(all_candidates)

    # combined ranking across all leagues by expected_log_growth then edge
    ranked = sorted(
        best_by_match.values(),
        key=lambda x: (x.expected_log_growth, x.edge),
        reverse=True,
    )

    day_start = bankroll_before_day(db_path, day, initial_bankroll)
    risk = DailyRiskManager(day_start_bankroll=day_start, stop_loss_pct=0.20)

    # guard using already-settled same-day pnl if rerun mid-day
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        r = conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN profit IS NULL THEN 0 ELSE profit END), 0)
            FROM bet_log
            WHERE substr(kickoff_time_hkt, 1, 10) = ?
            """,
            (day.isoformat(),),
        ).fetchone()
        day_pnl_now = float(r[0] or 0.0)
    finally:
        conn.close()

    if day_pnl_now <= (-0.20 * day_start):
        risk.state.stop_triggered = True

    selected = []
    bankroll_cursor = day_start
    for c in ranked:
        if not risk.can_place():
            break
        bet = make_selected_bet(c, sim_date=day, bankroll_before=bankroll_cursor, run_id=run_id)
        if bet.stake <= 0:
            continue
        selected.append(bet)
        bankroll_cursor -= bet.stake

    inserted = append_selected_bets(db_path=db_path, bets=selected, source_book="paper_sim")

    return {
        "matches": len(matches),
        "candidates": len(all_candidates),
        "selected": len(selected),
        "inserted": inserted,
        "risk_stop": risk.state.stop_triggered,
        "day_start_bankroll": day_start,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one-day paper bet selection and append to tracking sqlite")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--sqlite",
        default=str(Path(settings_v2.tracking_sqlite_path)),
        help="tracking sqlite path",
    )
    parser.add_argument(
        "--snapshot-db",
        default="data/v2/odds_snapshots.sqlite",
        help="odds snapshot sqlite path",
    )
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()

    day = datetime.strptime(args.date, "%Y-%m-%d").date()
    run_id = args.run_id or f"paper_day_{day.isoformat()}"

    res = run_for_day(
        day=day,
        db_path=Path(args.sqlite),
        snapshot_db=Path(args.snapshot_db),
        initial_bankroll=settings_v2.initial_bankroll,
        run_id=run_id,
    )
    print(f"[OK] day={day.isoformat()} -> {res}")


if __name__ == "__main__":
    main()
