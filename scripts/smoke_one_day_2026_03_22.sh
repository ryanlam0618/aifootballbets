#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_BASE="${1:-/tmp/aifootballbets_smoke_20260322}"
RUN_DIR="${TMP_BASE}_$(date +%s)"
SOFA_DIR="$RUN_DIR/sofa"
ODDSPORTAL_DIR="$RUN_DIR/oddsportal"
mkdir -p "$SOFA_DIR" "$ODDSPORTAL_DIR"

DB="$SOFA_DIR/backfill_10y.sqlite"
STATE="$SOFA_DIR/state.json"
SHOTMAP_STATE="$SOFA_DIR/shotmap_state.json"
SHOTMAP_DETAIL_STATE="$SOFA_DIR/shotmap_detail_state.json"
EVENT_ODDS_DB="$SOFA_DIR/event_odds.sqlite"
EVENT_ODDS_STATE="$SOFA_DIR/event_odds_state.json"

echo "[SMOKE] run_dir=$RUN_DIR"

cd "$ROOT_DIR"

# 1) SofaScore scheduled + stats + lineups for one day
python3 TakeData/sofa_score/backfill_10y_leagues_cups.py \
  --start-date 2026-03-22 \
  --end-date 2026-03-22 \
  --out-dir "$SOFA_DIR" \
  --db "$DB" \
  --state "$STATE" \
  --commit-every 20 \
  --sleep 0.0

python3 - <<PY
import sqlite3, json
from pathlib import Path

db=sqlite3.connect(r"$DB")
inserted=db.execute("select count(*) from matches where match_date='2026-03-22'").fetchone()[0]
print(f"[CHECK] matches inserted on 2026-03-22: {inserted}")
assert inserted > 0, "No matches inserted for 2026-03-22"
raw_sched=Path(r"$SOFA_DIR/raw/scheduled-events/2026-03-22.json")
assert raw_sched.exists(), f"missing raw scheduled file: {raw_sched}"
lineup_files=list(Path(r"$SOFA_DIR/raw/lineups").glob("*.json"))
print(f"[CHECK] raw lineup files: {len(lineup_files)}")
assert len(lineup_files) > 0, "No raw lineup files dumped"
first_event=db.execute("select event_id from matches where match_date='2026-03-22' order by event_id limit 1").fetchone()[0]
print(f"[CHECK] first event_id: {first_event}")
Path(r"$SOFA_DIR/first_event_id.txt").write_text(str(first_event), encoding='utf-8')
PY

EVENT_ID="$(cat "$SOFA_DIR/first_event_id.txt")"

# 2) Shotmap/xG smoke using --limit 1
python3 TakeData/sofa_score/shotmap_xg_backfill.py \
  --db "$DB" \
  --state "$SHOTMAP_STATE" \
  --start-date 2026-03-22 \
  --end-date 2026-03-22 \
  --limit 1 \
  --checkpoint-every 1 \
  --sleep-min 0 \
  --sleep-max 0

python3 - <<PY
import sqlite3

db=sqlite3.connect(r"$DB")
cnt=db.execute("select count(*) from shotmap_xg_backfill").fetchone()[0]
print(f"[CHECK] shotmap_xg_backfill rows: {cnt}")
assert cnt >= 1, "shotmap_xg_backfill did not write rows"
PY

# (optional detailed shotmap; should complete quickly)
python3 TakeData/sofa_score/shotmap_detail_backfill.py \
  --db "$DB" \
  --state "$SHOTMAP_DETAIL_STATE" \
  --limit 1 \
  --checkpoint-every 1 \
  --sleep-min 0 \
  --sleep-max 0

# 3) Event odds smoke with --limit 1
python3 TakeData/sofa_score/backfill_event_odds_10y.py \
  --matches-db "$DB" \
  --out-db "$EVENT_ODDS_DB" \
  --state "$EVENT_ODDS_STATE" \
  --start-date 2026-03-22 \
  --end-date 2026-03-22 \
  --limit 1 \
  --checkpoint-every 1 \
  --sleep-min 0 \
  --sleep-max 0

python3 - <<PY
import sqlite3

db=sqlite3.connect(r"$EVENT_ODDS_DB")
cnt=db.execute("select count(*) from event_odds_10y_multi").fetchone()[0]
print(f"[CHECK] event_odds_10y_multi rows: {cnt}")
assert cnt >= 1, "event odds backfill produced no rows"
PY

# 4) OddsPortal smoke: one match x 1X2, OU, AH (strict timeouts)
MATCH_URL="https://www.oddsportal.com/football/england/premier-league/brentford-wolves-0jR7cwU6/"

for MARKET in 1X2 OU AH; do
  OUT_JSON="$ODDSPORTAL_DIR/${MARKET}.json"
  python3 scripts/oddsportal_one_match.py \
    --headless \
    --match-url "$MATCH_URL" \
    --market "$MARKET" \
    --output "$OUT_JSON" \
    --timeout-ms 60000 \
    --selector-timeout-ms 25000 \
    --settle-ms 1200 \
    --top-lines 2 \
    --adjacent-delta 0.25 \
    --max-lines-to-expand 6 \
    --max-retries 1

  python3 - <<PY
import json
from pathlib import Path
p=Path(r"$OUT_JSON")
obj=json.loads(p.read_text(encoding='utf-8'))
odds=obj.get('odds') or []
print(f"[CHECK] {p.name}: odds rows={len(odds)}")
assert len(odds) > 0, f"{p.name} odds empty"
PY
done

echo "[SMOKE DONE] All checks passed. Artifacts in: $RUN_DIR"
