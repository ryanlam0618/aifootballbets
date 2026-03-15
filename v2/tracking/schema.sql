-- v2/tracking/schema.sql
-- Bet tracking schema (Phase A)

CREATE TABLE IF NOT EXISTS bet_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id TEXT NOT NULL,
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
    source_book TEXT NOT NULL DEFAULT 'sport pp88',
    source_file TEXT,
    run_id TEXT,

    odds_close REAL,
    clv_abs REAL,
    clv_pct REAL,

    created_at_utc TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bet_log_bet_time ON bet_log (bet_time_hkt);
CREATE INDEX IF NOT EXISTS idx_bet_log_league ON bet_log (league);
CREATE INDEX IF NOT EXISTS idx_bet_log_market_type ON bet_log (market_type);
CREATE INDEX IF NOT EXISTS idx_bet_log_bet_id ON bet_log (bet_id);
