-- v2/tracking/schema_odds_tracker.sql
-- OddsPortal odds movement tracker schema (24h snapshots)

CREATE TABLE IF NOT EXISTS odds_match (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_url TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT '1X2',
    label TEXT,
    created_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(match_url, market)
);

CREATE TABLE IF NOT EXISTS odds_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    snapshot_ts_utc TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 1,
    row_count_seen INTEGER,
    quote_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at_utc TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (match_id) REFERENCES odds_match(id)
);

CREATE TABLE IF NOT EXISTS odds_quote (
    snapshot_id INTEGER NOT NULL,
    bookmaker TEXT NOT NULL,
    home REAL,
    draw REAL,
    away REAL,
    raw TEXT,
    PRIMARY KEY (snapshot_id, bookmaker),
    FOREIGN KEY (snapshot_id) REFERENCES odds_snapshot(id)
);

CREATE INDEX IF NOT EXISTS idx_odds_match_url_market ON odds_match(match_url, market);
CREATE INDEX IF NOT EXISTS idx_odds_snapshot_match_time ON odds_snapshot(match_id, snapshot_ts_utc);
CREATE INDEX IF NOT EXISTS idx_odds_quote_bookmaker ON odds_quote(bookmaker);
