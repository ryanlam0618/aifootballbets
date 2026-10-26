"""MySQL mirrors for odds snapshots, predictions and the bet ledger.

Design (dual-write):
- The paper pipeline keeps SQLite as its internal working store (replay,
  tests, reports); every committed row is ALSO mirrored into MySQL afb_*
  tables. MySQL therefore holds the unified layer-1 view while the pipeline
  remains deterministic and offline-friendly.
- All writers are best-effort with explicit failure logging: a DB outage
  must never break a paper run.
"""

from __future__ import annotations

import sys
from typing import Iterable, Optional

from afbdb.connection import afb_mysql_connect


def _warn(where: str, exc: Exception) -> None:
    print(f"[afbdb][WARN] {where} failed: {exc}", file=sys.stderr)


# ---------------------------------------------------------------- snapshots

_SNAP_COLS = (
    "match_id, source, league_key, league_name, home_team, away_team, "
    "commence_time_utc, market_key, selection, odds, bookmaker, captured_at_utc, run_id"
)


def db_write_snapshots(snap_rows: list[dict]) -> int:
    """Insert odds snapshot rows into afb_odds_snapshots. Idempotent per second."""
    if not snap_rows:
        return 0
    inserted = 0
    try:
        conn = afb_mysql_connect()
    except Exception as exc:
        _warn("snapshots.connect", exc)
        return 0
    try:
        sql = (
            f"INSERT IGNORE INTO afb_odds_snapshots ({_SNAP_COLS}) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        )
        with conn.cursor() as cur:
            for r in snap_rows:
                cur.execute(
                    sql,
                    (
                        str(r.get("match_id") or "")[:64],
                        str(r.get("source") or "unknown")[:32],
                        r.get("league_key"),
                        r.get("league_name"),
                        str(r.get("home_team") or "")[:100],
                        str(r.get("away_team") or "")[:100],
                        r.get("commence_time_utc"),
                        str(r.get("market_key") or "")[:100],
                        str(r.get("selection") or "")[:32],
                        float(r["odds"]),
                        r.get("bookmaker"),
                        r.get("captured_at_utc"),
                        r.get("run_id"),
                    ),
                )
                inserted += cur.rowcount
        conn.commit()
        return inserted
    except Exception as exc:
        _warn("snapshots.write", exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def db_latest_odds_asof(match_id: str, asof_utc=None) -> dict:
    """Latest known odds per (market_key, selection) for one match, as-of a time.

    Returns {(market_key, selection): odds}.
    """
    out: dict = {}
    try:
        conn = afb_mysql_connect()
    except Exception as exc:
        _warn("snapshots.read", exc)
        return out
    try:
        with conn.cursor() as cur:
            if asof_utc is None:
                cur.execute(
                    """
                    SELECT market_key, selection, odds
                    FROM afb_odds_snapshots
                    WHERE match_id = %s
                      AND captured_at_utc = (
                          SELECT MAX(captured_at_utc) FROM afb_odds_snapshots WHERE match_id = %s
                      )
                    """,
                    (str(match_id), str(match_id)),
                )
            else:
                cur.execute(
                    """
                    SELECT s.market_key, s.selection, s.odds
                    FROM afb_odds_snapshots s
                    JOIN (
                        SELECT market_key, selection, MAX(captured_at_utc) AS mx
                        FROM afb_odds_snapshots
                        WHERE match_id = %s AND captured_at_utc <= %s
                        GROUP BY market_key, selection
                    ) t ON t.market_key = s.market_key AND t.selection = s.selection
                       AND t.mx = s.captured_at_utc
                    WHERE s.match_id = %s
                    """,
                    (str(match_id), asof_utc, str(match_id)),
                )
            for mk, sel, odds in cur.fetchall():
                if mk is not None and sel is not None and odds is not None:
                    out[(str(mk), str(sel))] = float(odds)
        return out
    except Exception as exc:
        _warn("snapshots.read", exc)
        return out
    finally:
        try:
            conn.close()
        except Exception:
            pass


# --------------------------------------------------------------- predictions

_PRED_COLS = (
    "run_id, run_date, match_id, league, home_team, away_team, market, line, selection, "
    "odds, model_probability, implied_probability, edge, ev, kelly_fraction, "
    "suggested_stake, bet_flag, confidence, rationale, model_name"
)


def db_write_predictions(pred_rows: list[dict]) -> int:
    """Insert prediction rows into afb_predictions (one run = one run_id)."""
    if not pred_rows:
        return 0
    try:
        conn = afb_mysql_connect()
    except Exception as exc:
        _warn("predictions.connect", exc)
        return 0
    try:
        sql = (
            f"INSERT IGNORE INTO afb_predictions ({_PRED_COLS}) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        )
        with conn.cursor() as cur:
            for r in pred_rows:
                cur.execute(
                    sql,
                    (
                        str(r.get("run_id") or "")[:64],
                        r.get("run_date"),
                        str(r.get("match_id") or "")[:64],
                        r.get("league"),
                        str(r.get("home_team") or "")[:100],
                        str(r.get("away_team") or "")[:100],
                        str(r.get("market") or "")[:50],
                        (None if r.get("line") in (None, "") else str(r.get("line"))[:20]),
                        str(r.get("selection") or "")[:32],
                        r.get("odds"),
                        float(r["model_probability"]),
                        r.get("implied_probability"),
                        r.get("edge"),
                        r.get("ev"),
                        r.get("kelly_fraction"),
                        r.get("suggested_stake"),
                        1 if r.get("bet_flag") else 0,
                        r.get("confidence"),
                        r.get("rationale"),
                        str(r.get("model_name") or "team_strength_poisson")[:50],
                    ),
                )
        conn.commit()
        return len(pred_rows)
    except Exception as exc:
        _warn("predictions.write", exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------- bet ledger

_BET_COLS = (
    "bet_id, bet_time_hkt, kickoff_time_hkt, closing_time_hkt, league, home, away, "
    "market, market_type, line, selection, odds_bet, model_prob, ev, kelly_pct, stake, "
    "result, profit, bankroll, notes, source_book, source_file, run_id, "
    "source_quality, odds_source, odds_close, clv_abs, clv_pct, close_odds_source"
)


def db_append_bets(payloads: list[dict]) -> int:
    """Mirror bet rows into afb_bets (INSERT IGNORE on PK bet_id)."""
    if not payloads:
        return 0
    try:
        conn = afb_mysql_connect()
    except Exception as exc:
        _warn("bets.connect", exc)
        return 0
    try:
        sql = (
            f"INSERT IGNORE INTO afb_bets ({_BET_COLS}) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        )
        keys = [
            "bet_id", "bet_time_hkt", "kickoff_time_hkt", "closing_time_hkt",
            "league", "home", "away", "market", "market_type", "line", "selection",
            "odds_bet", "model_prob", "ev", "kelly_pct", "stake",
            "result", "profit", "bankroll", "notes", "source_book", "source_file", "run_id",
            "source_quality", "odds_source", "odds_close", "clv_abs", "clv_pct",
        ]
        with conn.cursor() as cur:
            for p in payloads:
                vals = [p.get(k) for k in keys]
                cur.execute(sql, tuple(vals))
        conn.commit()
        return len(payloads)
    except Exception as exc:
        _warn("bets.write", exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def db_settle_bet(
    bet_id: str,
    result: str,
    profit: float,
    bankroll_after: float,
    odds_close: Optional[float] = None,
    clv_abs: Optional[float] = None,
    clv_pct: Optional[float] = None,
    close_odds_source: Optional[str] = None,
) -> bool:
    """Mirror a settlement update onto afb_bets."""
    try:
        conn = afb_mysql_connect()
    except Exception as exc:
        _warn("bets.settle.connect", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE afb_bets
                SET result=%s, profit=%s, bankroll=%s,
                    odds_close=%s, clv_abs=%s, clv_pct=%s, close_odds_source=%s
                WHERE bet_id=%s
                """,
                (
                    result,
                    float(profit),
                    float(bankroll_after),
                    odds_close,
                    clv_abs,
                    clv_pct,
                    close_odds_source,
                    str(bet_id),
                ),
            )
        conn.commit()
        return True
    except Exception as exc:
        _warn("bets.settle", exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def db_get_state(key: str, default: str) -> str:
    try:
        conn = afb_mysql_connect()
    except Exception:
        return default
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT state_value FROM afb_state WHERE state_key=%s", (str(key),))
            row = cur.fetchone()
            return str(row[0]) if row else default
    except Exception:
        return default
    finally:
        try:
            conn.close()
        except Exception:
            pass


def db_set_state(key: str, value: str) -> bool:
    try:
        conn = afb_mysql_connect()
    except Exception as exc:
        _warn("state.write", exc)
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO afb_state (state_key, state_value)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE state_value=VALUES(state_value)
                """,
                (str(key)[:64], str(value)[:255]),
            )
        conn.commit()
        return True
    except Exception as exc:
        _warn("state.write", exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


__all__ = [
    "Optional",
    "db_append_bets",
    "db_get_state",
    "db_latest_odds_asof",
    "db_set_state",
    "db_settle_bet",
    "db_write_predictions",
    "db_write_snapshots",
]
