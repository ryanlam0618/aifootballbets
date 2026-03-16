-- v2/tracking/schema_odds_tracker_v2.sql
-- OddsPortal odds movement tracker schema (supports 1X2, OU, AH with main-line tracking)

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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    bookmaker TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT '1X2',
    line REAL,
    home REAL,
    draw REAL,
    away REAL,
    raw TEXT,
    FOREIGN KEY (snapshot_id) REFERENCES odds_snapshot(id)
);

CREATE INDEX IF NOT EXISTS idx_odds_match_url_market ON odds_match(match_url, market);
CREATE INDEX IF NOT EXISTS idx_odds_snapshot_match_time ON odds_snapshot(match_id, snapshot_ts_utc);
CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_quote_unique_snapshot_bookmaker_line
    ON odds_quote(snapshot_id, bookmaker, market_type, COALESCE(line, -9999.0));
CREATE INDEX IF NOT EXISTS idx_odds_quote_snapshot_bookmaker ON odds_quote(snapshot_id, bookmaker);
CREATE INDEX IF NOT EXISTS idx_odds_quote_market_line ON odds_quote(market_type, line);
CREATE INDEX IF NOT EXISTS idx_odds_quote_bookmaker ON odds_quote(bookmaker);
