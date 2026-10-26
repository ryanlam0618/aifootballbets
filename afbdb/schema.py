"""Schema for afb_* tables (owned by aifootballbets).

Idempotent CREATE TABLE IF NOT EXISTS. We intentionally avoid DROP (the
appdb_rw grant has no DROP privilege) — schema evolution is additive only.

Walk-forward friendliness:
- every row carries its own event/creation time;
- as-of reads filter on captured_at_utc / created_at_utc / run_date;
- history reads (matches/shotmap) are as-of filtered downstream by match_date.
"""

from __future__ import annotations

_DDL = """
CREATE TABLE IF NOT EXISTS afb_odds_snapshots (
  id BIGINT NOT NULL AUTO_INCREMENT,
  match_id VARCHAR(64) NOT NULL,
  source VARCHAR(32) NOT NULL DEFAULT 'unknown',
  league_key VARCHAR(64) DEFAULT NULL,
  league_name VARCHAR(100) DEFAULT NULL,
  home_team VARCHAR(100) NOT NULL,
  away_team VARCHAR(100) NOT NULL,
  commence_time_utc DATETIME DEFAULT NULL,
  market_key VARCHAR(100) NOT NULL,
  selection VARCHAR(32) NOT NULL,
  odds DECIMAL(10,3) NOT NULL,
  bookmaker VARCHAR(64) DEFAULT NULL,
  captured_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  run_id VARCHAR(64) DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_afb_odds_snap (match_id, market_key, selection, bookmaker, captured_at_utc),
  KEY idx_afb_odds_asof (match_id, captured_at_utc),
  KEY idx_afb_odds_commence (commence_time_utc)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS afb_predictions (
  id BIGINT NOT NULL AUTO_INCREMENT,
  run_id VARCHAR(64) NOT NULL,
  run_date DATE NOT NULL,
  match_id VARCHAR(64) NOT NULL,
  league VARCHAR(100) DEFAULT NULL,
  home_team VARCHAR(100) NOT NULL,
  away_team VARCHAR(100) NOT NULL,
  market VARCHAR(50) NOT NULL,
  line VARCHAR(20) DEFAULT NULL,
  selection VARCHAR(32) NOT NULL,
  odds DECIMAL(10,3) DEFAULT NULL,
  model_probability DECIMAL(9,6) NOT NULL,
  implied_probability DECIMAL(9,6) DEFAULT NULL,
  edge DECIMAL(9,6) DEFAULT NULL,
  ev DECIMAL(12,6) DEFAULT NULL,
  kelly_fraction DECIMAL(9,6) DEFAULT NULL,
  suggested_stake DECIMAL(12,2) DEFAULT NULL,
  bet_flag TINYINT(1) DEFAULT 0,
  confidence VARCHAR(10) DEFAULT NULL,
  rationale TEXT,
  model_name VARCHAR(50) DEFAULT 'team_strength_poisson',
  created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_afb_pred (run_id, match_id, market, line, selection),
  KEY idx_afb_pred_date (run_date),
  KEY idx_afb_pred_match (match_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS afb_bets (
  bet_id VARCHAR(32) NOT NULL,
  bet_time_hkt VARCHAR(32) DEFAULT NULL,
  kickoff_time_hkt VARCHAR(32) DEFAULT NULL,
  closing_time_hkt VARCHAR(32) DEFAULT NULL,
  league VARCHAR(100) DEFAULT NULL,
  home VARCHAR(100) DEFAULT NULL,
  away VARCHAR(100) DEFAULT NULL,
  market VARCHAR(50) DEFAULT NULL,
  market_type VARCHAR(50) DEFAULT NULL,
  line VARCHAR(20) DEFAULT NULL,
  selection VARCHAR(32) DEFAULT NULL,
  odds_bet DECIMAL(10,3) DEFAULT NULL,
  model_prob DECIMAL(9,6) DEFAULT NULL,
  ev DECIMAL(12,6) DEFAULT NULL,
  kelly_pct DECIMAL(9,6) DEFAULT NULL,
  stake DECIMAL(12,2) DEFAULT NULL,
  result VARCHAR(20) DEFAULT NULL,
  profit DECIMAL(12,2) DEFAULT NULL,
  bankroll DECIMAL(12,2) DEFAULT NULL,
  notes TEXT,
  source_book VARCHAR(32) NOT NULL DEFAULT 'paper_sim',
  source_file VARCHAR(255) DEFAULT NULL,
  run_id VARCHAR(64) DEFAULT NULL,
  source_quality VARCHAR(20) NOT NULL DEFAULT 'synthetic_odds',
  odds_source VARCHAR(32) DEFAULT NULL,
  odds_close DECIMAL(10,3) DEFAULT NULL,
  clv_abs DECIMAL(10,4) DEFAULT NULL,
  clv_pct DECIMAL(10,4) DEFAULT NULL,
  close_odds_source VARCHAR(32) DEFAULT NULL,
  created_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (bet_id),
  KEY idx_afb_bets_time (bet_time_hkt),
  KEY idx_afb_bets_kickoff (kickoff_time_hkt),
  KEY idx_afb_bets_league (league),
  KEY idx_afb_bets_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS afb_state (
  state_key VARCHAR(64) NOT NULL,
  state_value VARCHAR(255) NOT NULL,
  updated_at_utc DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (state_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def ensure_afb_schema(conn) -> None:
    """Create afb_* tables if missing. Idempotent; additive only (no DROP)."""
    with conn.cursor() as cur:
        for stmt in _DDL.split(";"):
            s = stmt.strip()
            if s:
                cur.execute(s)
    conn.commit()


__all__ = ["ensure_afb_schema"]
