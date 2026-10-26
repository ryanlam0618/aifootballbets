#!/usr/bin/env python3
"""Layer-1 migration: legacy file/SQLite bet data -> MySQL afb_bets.

Sources handled (idempotent, PK = bet_id, INSERT ... ON DUPLICATE KEY no-op):
- data/v2/tracking/bets_normalized.csv  (legacy normalized export)
- data/v2/tracking/bets.sqlite bet_log  (legacy paper ledger, if present)

Never touches sofascore-backfill tables (matches/match_odds/... are read-only
for this project). Credentials come from .env (AFB_MYSQL_*).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import settings_v2  # noqa: E402  (loads .env)

CSV_PATH = REPO_ROOT / "data" / "v2" / "tracking" / "bets_normalized.csv"
SQLITE_PATH = Path(settings_v2.tracking_sqlite_path)

BET_COLS = [
    "bet_id", "bet_time_hkt", "kickoff_time_hkt", "closing_time_hkt",
    "league", "home", "away", "market", "market_type", "line", "selection",
    "odds_bet", "model_prob", "ev", "kelly_pct", "stake",
    "result", "profit", "bankroll", "notes", "source_book", "source_file", "run_id",
    "source_quality", "odds_source", "odds_close", "clv_abs", "clv_pct", "close_odds_source",
]

NUMERIC_COLS = {"odds_bet", "model_prob", "ev", "kelly_pct", "stake", "profit", "bankroll", "odds_close", "clv_abs", "clv_pct"}


def _clean(row: dict, default_source_quality: str) -> dict:
    out = {}
    for c in BET_COLS:
        v = row.get(c)
        if v is None or (isinstance(v, str) and v.strip() == ""):
            v = None
        if c in NUMERIC_COLS and v is not None:
            v = float(v)
        out[c] = v
    if not out.get("source_book"):
        out["source_book"] = "paper_sim"
    if not out.get("source_quality"):
        # legacy CSV rows with source_book=sportsbook are real bets
        out["source_quality"] = default_source_quality
    return out


def upsert_rows(rows: list[dict]) -> int:
    from afbdb.connection import afb_mysql_connect

    conn = afb_mysql_connect()
    inserted = 0
    try:
        with conn.cursor() as cur:
            for r in rows:
                cols = ",".join(BET_COLS)
                ph = ",".join(["%s"] * len(BET_COLS))
                cur.execute(
                    f"INSERT INTO afb_bets ({cols}) VALUES ({ph}) "
                    "ON DUPLICATE KEY UPDATE updated_at_utc = afb_bets.updated_at_utc",
                    tuple(r[c] for c in BET_COLS),
                )
                inserted += 1 if cur.rowcount == 1 else 0
        conn.commit()
    finally:
        conn.close()
    return inserted


def migrate_csv(path: Path) -> tuple[int, int]:
    if not path.exists():
        print(f"[skip] CSV not found: {path}")
        return 0, 0
    import csv

    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for raw in csv.DictReader(f):
            rows.append(_clean(raw, default_source_quality="real_odds"))
    ok = upsert_rows(rows)
    print(f"[csv] {path.name}: read {len(rows)}, upserted {ok}")
    return len(rows), ok


def migrate_sqlite(path: Path) -> tuple[int, int]:
    if not path.exists():
        print(f"[skip] sqlite not found: {path}")
        return 0, 0
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute("SELECT * FROM bet_log")
        rows = [_clean(dict(r), default_source_quality="synthetic_odds") for r in cur.fetchall()]
    finally:
        conn.close()
    ok = upsert_rows(rows)
    print(f"[sqlite] {path.name}: read {len(rows)}, upserted {ok}")
    return len(rows), ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy bet data to MySQL afb_bets")
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--sqlite", type=Path, default=SQLITE_PATH)
    args = parser.parse_args()

    total_read = 0
    total_up = 0
    for fn, arg in ((migrate_csv, args.csv), (migrate_sqlite, args.sqlite)):
        r, u = fn(arg)
        total_read += r
        total_up += u

    print(f"[done] total read {total_read}, upserted {total_up} -> afb_bets")


if __name__ == "__main__":
    main()
