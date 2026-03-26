-- OddsPortal time-series tracking (relative-to-kickoff) → MySQL 8
-- Source JSONL: v2/tracking/run_relative_schedule.py output envelope

-- Snapshots: one per (match_url, market_type, snapshot_ts_utc)
CREATE TABLE IF NOT EXISTS oddsportal_snapshot (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  match_url VARCHAR(512) NOT NULL,
  market_type VARCHAR(16) NOT NULL,
  snapshot_ts_utc DATETIME(6) NOT NULL,

  -- scheduling context
  scheduled_snapshot_ts_utc DATETIME(6) NULL,
  minutes_to_kickoff INT NULL,

  -- join keys / metadata
  sofascore_event_id BIGINT NULL,
  kickoff_utc DATETIME(6) NULL,
  home_team VARCHAR(128) NULL,
  away_team VARCHAR(128) NULL,
  tournament VARCHAR(128) NULL,
  tournament_slug VARCHAR(128) NULL,

  detected_market_tab VARCHAR(64) NULL,
  row_count_seen INT NULL,
  quote_count INT NULL,

  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  UNIQUE KEY uk_snapshot (match_url, market_type, snapshot_ts_utc),
  KEY idx_event (sofascore_event_id),
  KEY idx_kickoff (kickoff_utc),
  KEY idx_sched (scheduled_snapshot_ts_utc)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Quotes: one per bookmaker (+ line for OU/AH) within a snapshot
CREATE TABLE IF NOT EXISTS oddsportal_quote (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  snapshot_id BIGINT UNSIGNED NOT NULL,
  bookmaker VARCHAR(64) NOT NULL,
  line DOUBLE NULL,

  home_odds DOUBLE NULL,
  draw_odds DOUBLE NULL,
  away_odds DOUBLE NULL,
  raw VARCHAR(512) NULL,

  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  UNIQUE KEY uk_quote (snapshot_id, bookmaker, line),
  KEY idx_snapshot (snapshot_id),

  CONSTRAINT fk_oddsportal_quote_snapshot
    FOREIGN KEY (snapshot_id)
    REFERENCES oddsportal_snapshot(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
