from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from v2.paper.db import ensure_tracking_schema
from v2.paper.models import SelectedBet
from v2.paper.staking import market_type, utc_to_hkt_iso

HKT = timezone(timedelta(hours=8))


def append_selected_bets(db_path: Path, bets: Iterable[SelectedBet], source_book: str = "paper_sim") -> int:
    ensure_tracking_schema(db_path)
    rows = list(bets)
    if not rows:
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        sql = """
        INSERT OR IGNORE INTO bet_log (
            bet_id, bet_time_hkt, kickoff_time_hkt, closing_time_hkt,
            league, home, away,
            market, market_type, line, selection,
            odds_bet, model_prob, ev, kelly_pct, stake,
            result, profit, bankroll,
            notes, source_book, source_file, run_id,
            odds_close, clv_abs, clv_pct
        ) VALUES (
            :bet_id, :bet_time_hkt, :kickoff_time_hkt, :closing_time_hkt,
            :league, :home, :away,
            :market, :market_type, :line, :selection,
            :odds_bet, :model_prob, :ev, :kelly_pct, :stake,
            :result, :profit, :bankroll,
            :notes, :source_book, :source_file, :run_id,
            :odds_close, :clv_abs, :clv_pct
        )
        """

        payloads = []
        now_hkt = datetime.now(HKT).replace(microsecond=0).isoformat(timespec="seconds")
        for b in rows:
            kickoff_hkt = utc_to_hkt_iso(b.kickoff_utc)
            kickoff_dt = datetime.fromisoformat(kickoff_hkt)
            close_hkt = (kickoff_dt - timedelta(minutes=5)).replace(microsecond=0).isoformat(timespec="seconds")
            payloads.append(
                {
                    "bet_id": b.bet_id,
                    "bet_time_hkt": now_hkt,
                    "kickoff_time_hkt": kickoff_hkt,
                    "closing_time_hkt": close_hkt,
                    "league": b.league_name,
                    "home": b.home_team,
                    "away": b.away_team,
                    "market": b.market,
                    "market_type": market_type(b.market),
                    "line": b.line,
                    "selection": b.selection,
                    "odds_bet": b.odds,
                    "model_prob": b.model_probability,
                    "ev": b.ev,
                    "kelly_pct": b.kelly_used,
                    "stake": b.stake,
                    "result": None,
                    "profit": None,
                    "bankroll": b.bankroll_before,
                    "notes": f"paper:{b.sim_date.isoformat()} edge={b.edge:.4f}",
                    "source_book": source_book,
                    "source_file": "v2/paper/ledger.py",
                    "run_id": b.run_id,
                    "odds_close": None,
                    "clv_abs": None,
                    "clv_pct": None,
                }
            )

        before = conn.total_changes
        conn.executemany(sql, payloads)
        conn.commit()
        return int(conn.total_changes - before)
    finally:
        conn.close()


def open_unsettled_bets_for_day(db_path: Path, day: date) -> List[sqlite3.Row]:
    ensure_tracking_schema(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        day_s = day.isoformat()
        rows = conn.execute(
            """
            SELECT *
            FROM bet_log
            WHERE result IS NULL
              AND substr(kickoff_time_hkt, 1, 10) = ?
            ORDER BY kickoff_time_hkt ASC, id ASC
            """,
            (day_s,),
        ).fetchall()
        return rows
    finally:
        conn.close()


def settle_bet(db_path: Path, bet_id: str, result: str, profit: float, bankroll_after: float) -> None:
    ensure_tracking_schema(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            UPDATE bet_log
            SET result = ?, profit = ?, bankroll = ?
            WHERE bet_id = ?
            """,
            (result, float(profit), float(bankroll_after), bet_id),
        )
        conn.commit()
    finally:
        conn.close()


def bankroll_before_day(db_path: Path, day: date, initial_bankroll: float) -> float:
    ensure_tracking_schema(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        day_s = day.isoformat()
        row = conn.execute(
            """
            SELECT bankroll
            FROM bet_log
            WHERE result IS NOT NULL
              AND substr(kickoff_time_hkt, 1, 10) < ?
            ORDER BY kickoff_time_hkt DESC, id DESC
            LIMIT 1
            """,
            (day_s,),
        ).fetchone()
        if not row or row[0] is None:
            return float(initial_bankroll)
        return float(row[0])
    finally:
        conn.close()
