#!/usr/bin/env bash
set -euo pipefail

PROJECT="/home/openclaw/.openclaw/workspace/projects/aifootballbets"
PY="$PROJECT/.venv312/bin/python"
OUT_DIR="$PROJECT/data/backfill_sofascore_10y"
LOG_DIR="$PROJECT/logs"
LOG_FILE="$LOG_DIR/sofascore_10y_to_mysql.log"
mkdir -p "$OUT_DIR" "$LOG_DIR"

SEASONS=(
  "2017-2018"
  "2018-2019"
  "2019-2020"
  "2020-2021"
  "2021-2022"
  "2022-2023"
  "2023-2024"
  "2024-2025"
  "2025-2026"
)

sync_season() {
  local season="$1"
  local start_date="$2"
  local end_date="$3"
  SEASON="$season" START_DATE="$start_date" END_DATE="$end_date" "$PY" - <<'PY'
import os, sqlite3, pymysql

project='/home/openclaw/.openclaw/workspace/projects/aifootballbets'
out_dir=f'{project}/data/backfill_sofascore_10y'
season=os.environ['SEASON']
start_date=os.environ['START_DATE']
end_date=os.environ['END_DATE']

sqlite_main=f'{out_dir}/backfill_10y.sqlite'
sqlite_odds=f'{out_dir}/event_odds_10y.sqlite'

conn_mysql = pymysql.connect(
    host='192.168.0.182', port=3306,
    user='A100', password='hksfl1512', database='appdb',
    charset='utf8mb4', autocommit=False,
)
curm = conn_mysql.cursor()

curm.execute("""
CREATE TABLE IF NOT EXISTS sofascore_matches_10y (
  event_id BIGINT PRIMARY KEY,
  league VARCHAR(128),
  match_date DATE,
  home_team VARCHAR(255),
  away_team VARCHAR(255),
  home_goals INT,
  away_goals INT,
  home_shots INT,
  away_shots INT,
  home_shots_on INT,
  away_shots_on INT,
  home_corners INT,
  away_corners INT,
  home_yellow INT,
  away_yellow INT,
  home_red INT,
  away_red INT,
  home_fouls INT,
  away_fouls INT,
  home_poss INT,
  away_poss INT,
  home_xg_total DOUBLE,
  away_xg_total DOUBLE,
  season VARCHAR(16),
  source_tournament VARCHAR(255),
  source_category VARCHAR(128),
  updated_at VARCHAR(64),
  KEY idx_match_date (match_date),
  KEY idx_league (league)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

curm.execute("""
CREATE TABLE IF NOT EXISTS sofascore_shotmap_xg_backfill (
  event_id BIGINT PRIMARY KEY,
  match_date DATE,
  league VARCHAR(128),
  home_team VARCHAR(255),
  away_team VARCHAR(255),
  status_code INT,
  has_shotmap TINYINT,
  has_xg TINYINT,
  shot_count INT,
  home_shotmap_xg DOUBLE,
  away_shotmap_xg DOUBLE,
  fetched_at VARCHAR(64),
  error TEXT,
  KEY idx_match_date (match_date),
  KEY idx_league (league)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

curm.execute("""
CREATE TABLE IF NOT EXISTS sofascore_shotmap_details (
  event_id BIGINT,
  shot_id BIGINT,
  match_date DATE,
  league VARCHAR(128),
  home_team VARCHAR(255),
  away_team VARCHAR(255),
  is_home_shot TINYINT,
  team_name VARCHAR(255),
  player_id BIGINT,
  player_name VARCHAR(255),
  player_position VARCHAR(32),
  minute INT,
  added_time INT,
  time_seconds INT,
  period_time_seconds INT,
  incident_type VARCHAR(64),
  shot_type VARCHAR(64),
  situation VARCHAR(64),
  body_part VARCHAR(64),
  goal_mouth_location VARCHAR(64),
  player_x DOUBLE,
  player_y DOUBLE,
  player_z DOUBLE,
  goal_mouth_x DOUBLE,
  goal_mouth_y DOUBLE,
  goal_mouth_z DOUBLE,
  block_x DOUBLE,
  block_y DOUBLE,
  block_z DOUBLE,
  xg DOUBLE,
  status_code INT,
  fetched_at VARCHAR(64),
  error TEXT,
  PRIMARY KEY (event_id, shot_id),
  KEY idx_match_date (match_date),
  KEY idx_league (league)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

curm.execute("""
CREATE TABLE IF NOT EXISTS sofascore_event_odds_10y_multi (
  event_id BIGINT,
  match_date DATE,
  league VARCHAR(128),
  home_team VARCHAR(255),
  away_team VARCHAR(255),
  market VARCHAR(64),
  line VARCHAR(64),
  selection VARCHAR(64),
  open_decimal DOUBLE,
  current_decimal DOUBLE,
  source_id BIGINT,
  fetched_at VARCHAR(64),
  status_code INT,
  error TEXT,
  PRIMARY KEY (event_id, source_id, market, line, selection),
  KEY idx_match_date (match_date),
  KEY idx_league (league)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

conn_sql = sqlite3.connect(sqlite_main)
conn_sql.row_factory = sqlite3.Row

rows = conn_sql.execute(
    """
    SELECT event_id, league, match_date, home_team, away_team,
           home_goals, away_goals, home_shots, away_shots, home_shots_on, away_shots_on,
           home_corners, away_corners, home_yellow, away_yellow, home_red, away_red,
           home_fouls, away_fouls, home_poss, away_poss, home_xg_total, away_xg_total,
           season, source_tournament, source_category, updated_at
    FROM matches
    WHERE match_date >= ? AND match_date <= ?
    """, (start_date, end_date)
).fetchall()
if rows:
    sql = """
    REPLACE INTO sofascore_matches_10y (
      event_id, league, match_date, home_team, away_team,
      home_goals, away_goals, home_shots, away_shots, home_shots_on, away_shots_on,
      home_corners, away_corners, home_yellow, away_yellow, home_red, away_red,
      home_fouls, away_fouls, home_poss, away_poss, home_xg_total, away_xg_total,
      season, source_tournament, source_category, updated_at
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    curm.executemany(sql, [tuple(r[k] for k in r.keys()) for r in rows])

rows = conn_sql.execute(
    """
    SELECT event_id, match_date, league, home_team, away_team,
           status_code, has_shotmap, has_xg, shot_count,
           home_shotmap_xg, away_shotmap_xg, fetched_at, error
    FROM shotmap_xg_backfill
    WHERE match_date >= ? AND match_date <= ?
    """, (start_date, end_date)
).fetchall()
if rows:
    sql = """
    REPLACE INTO sofascore_shotmap_xg_backfill (
      event_id, match_date, league, home_team, away_team,
      status_code, has_shotmap, has_xg, shot_count,
      home_shotmap_xg, away_shotmap_xg, fetched_at, error
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    curm.executemany(sql, [tuple(r[k] for k in r.keys()) for r in rows])

rows = conn_sql.execute(
    """
    SELECT event_id, shot_id, match_date, league, home_team, away_team,
           is_home_shot, team_name, player_id, player_name, player_position,
           minute, added_time, time_seconds, period_time_seconds,
           incident_type, shot_type, situation, body_part, goal_mouth_location,
           player_x, player_y, player_z, goal_mouth_x, goal_mouth_y, goal_mouth_z,
           block_x, block_y, block_z, xg, status_code, fetched_at, error
    FROM shotmap_details
    WHERE match_date >= ? AND match_date <= ?
    """, (start_date, end_date)
).fetchall()
if rows:
    sql = """
    REPLACE INTO sofascore_shotmap_details (
      event_id, shot_id, match_date, league, home_team, away_team,
      is_home_shot, team_name, player_id, player_name, player_position,
      minute, added_time, time_seconds, period_time_seconds,
      incident_type, shot_type, situation, body_part, goal_mouth_location,
      player_x, player_y, player_z, goal_mouth_x, goal_mouth_y, goal_mouth_z,
      block_x, block_y, block_z, xg, status_code, fetched_at, error
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    data = [tuple(r[k] for k in r.keys()) for r in rows]
    for i in range(0, len(data), 2000):
        curm.executemany(sql, data[i:i+2000])

conn_sql.close()

if os.path.exists(sqlite_odds):
    con2 = sqlite3.connect(sqlite_odds)
    con2.row_factory = sqlite3.Row
    rows = con2.execute(
        """
        SELECT event_id, match_date, league, home_team, away_team,
               market, line, selection, open_decimal, current_decimal,
               source_id, fetched_at, status_code, error
        FROM event_odds_10y_multi
        WHERE match_date >= ? AND match_date <= ?
        """, (start_date, end_date)
    ).fetchall()
    if rows:
        sql = """
        REPLACE INTO sofascore_event_odds_10y_multi (
          event_id, match_date, league, home_team, away_team,
          market, line, selection, open_decimal, current_decimal,
          source_id, fetched_at, status_code, error
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """
        data = [tuple(r[k] if k != 'source_id' else (r[k] if r[k] is not None else 0) for k in r.keys()) for r in rows]
        for i in range(0, len(data), 2000):
            curm.executemany(sql, data[i:i+2000])
    con2.close()

conn_mysql.commit()
for t in ['sofascore_matches_10y','sofascore_shotmap_xg_backfill','sofascore_shotmap_details','sofascore_event_odds_10y_multi']:
    curm.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"[{season}] {t} rows={curm.fetchone()[0]}")

curm.close(); conn_mysql.close()
print(f"[SYNC_OK] season={season} range={start_date}..{end_date}")
PY
}

{
  echo "===== START $(date -u '+%F %T UTC') ====="
  for season in "${SEASONS[@]}"; do
    echo "[SEASON_START] $season"
    start_date="${season%-*}-08-01"
    end_year="${season#*-}"
    end_date="$end_year-07-31"

    "$PY" "$PROJECT/TakeData/sofa_score/run_sofascore_season_backfill.py" \
      --season "$season" \
      --python "$PY" \
      --all-leagues-odds

    sync_season "$season" "$start_date" "$end_date"
    echo "[SEASON_DONE] $season"
  done
  echo "===== DONE $(date -u '+%F %T UTC') ====="
} >> "$LOG_FILE" 2>&1
