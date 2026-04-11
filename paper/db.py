from __future__ import annotations

import sqlite3
from pathlib import Path


def ensure_tracking_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bet_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bet_id TEXT NOT NULL UNIQUE,
                bet_time_hkt TEXT,
                kickoff_time_hkt TEXT,
                closing_time_hkt TEXT,
                league TEXT,
                home TEXT,
                away TEXT,
                market TEXT,
                market_type TEXT,
                line TEXT,
                selection TEXT,
                odds_bet REAL,
                model_prob REAL,
                ev REAL,
                kelly_pct REAL,
                stake REAL,
                result TEXT,
                profit REAL,
                bankroll REAL,
                notes TEXT,
                source_book TEXT NOT NULL DEFAULT 'paper_sim',
                source_file TEXT,
                run_id TEXT,
                source_quality TEXT NOT NULL DEFAULT 'synthetic_odds',
                odds_source TEXT,
                odds_close REAL,
                clv_abs REAL,
                clv_pct REAL,
                close_odds_source TEXT,
                created_at_utc TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_bet_log_bet_time ON bet_log (bet_time_hkt);
            CREATE INDEX IF NOT EXISTS idx_bet_log_league ON bet_log (league);
            CREATE INDEX IF NOT EXISTS idx_bet_log_market_type ON bet_log (market_type);
            CREATE INDEX IF NOT EXISTS idx_bet_log_bet_id ON bet_log (bet_id);

            CREATE TABLE IF NOT EXISTS paper_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )

        # Lightweight schema migration for existing DBs.
        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(bet_log)").fetchall()}
        if "source_quality" not in cols:
            conn.execute("ALTER TABLE bet_log ADD COLUMN source_quality TEXT NOT NULL DEFAULT 'synthetic_odds'")
        if "odds_source" not in cols:
            conn.execute("ALTER TABLE bet_log ADD COLUMN odds_source TEXT")
        if "close_odds_source" not in cols:
            conn.execute("ALTER TABLE bet_log ADD COLUMN close_odds_source TEXT")

        conn.commit()
    finally:
        conn.close()


def get_state(db_path: Path, key: str, default: str) -> str:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT value FROM paper_state WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        return str(row[0])
    finally:
        conn.close()


def set_state(db_path: Path, key: str, value: str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO paper_state(key, value, updated_at_utc)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
              value=excluded.value,
              updated_at_utc=datetime('now')
            """,
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()
