# v2/tracking (Phase A)

Value betting tracking tools for `aifootballbets`.

- Default sportsbook: **sport pp88**
- Timezone assumption for imports: **Hong Kong time (HKT, UTC+8)**
- Closing definition: **5 minutes before kickoff** (`closing_time_hkt = kickoff_time_hkt - 5m`)

## Files

- `schema.sql`
  - SQLite schema for `bet_log` including:
    - `bet_id, bet_time_hkt, league, home, away, market, market_type, line, selection`
    - `odds_bet, model_prob, ev, kelly_pct, stake`
    - `result, profit, bankroll, notes, source_book`
    - `kickoff_time_hkt, closing_time_hkt, odds_close, clv_abs, clv_pct`
- `xlsx_reader.py`
  - XLSX reader using only stdlib (`zipfile` + `xml.etree.ElementTree`)
- `import_bets.py`
  - Import historical XLSX to normalized CSV and/or SQLite
- `report_bets.py`
  - Reporting from SQLite (totals, ROI, market/league breakdown, calibration bins)

## Import historical betting records (XLSX)

Historical file example:

`/home/openclaw/.openclaw/media/inbound/Betting_Records---906cf633-1598-412c-92d9-25e9cc57815e.xlsx`

### Features of importer

- Single-sheet XLSX parse with stdlib only
- Handles mixed datetime formats in one column:
  - ISO-like strings (e.g. `2026-01-07 03:03`)
  - Excel serial numbers (e.g. `46024.054861111108`)
- Header detection in first 20 rows (supports possible index/meta rows above the real header)
- Market parsing into `market_type` + `line` when embedded, e.g.:
  - `Asian Handicap +0.5`
  - `Over/Under 2.5`

### Example commands

From project root:

```bash
python3 -m v2.tracking.import_bets \
  --xlsx /home/openclaw/.openclaw/media/inbound/Betting_Records---906cf633-1598-412c-92d9-25e9cc57815e.xlsx \
  --out-csv data/v2/tracking/bets_normalized.csv \
  --sqlite data/v2/tracking/bets.sqlite \
  --schema v2/tracking/schema.sql \
  --source-book "sport pp88"
```

## Run reports

```bash
python3 -m v2.tracking.report_bets --sqlite data/v2/tracking/bets.sqlite
```

Outputs in terminal:
- totals (bets, stake, profit, ROI, W/L/P)
- breakdown by `market_type`
- breakdown by `league`
- calibration table by `model_prob` bins

## Optional runtime hook from pipeline (off by default)

`v2/reports/exporters.py` includes:

- `append_recommendations_to_tracking_sqlite(...)`

`v2.main` will only call this when enabled via env:

```env
TRACKING_EXPORT_ENABLED=1
TRACKING_SQLITE_PATH=data/v2/tracking/bets.sqlite
TRACKING_SOURCE_BOOK=sport pp88
```

Behavior:
- append-only
- writes only `bet_flag=True` rows from recommendations
- does not overwrite historical records

## Adding closing odds / CLV later

Phase A stores placeholders (`odds_close`, `clv_abs`, `clv_pct`).

Suggested Phase B process:
1. Populate `kickoff_time_hkt` for each bet (if missing).
2. Compute `closing_time_hkt = kickoff_time_hkt - 5 minutes`.
3. Fetch market odds snapshot at `closing_time_hkt` and set `odds_close`.
4. Compute CLV, e.g. decimal-odds basis:
   - `clv_abs = odds_close - odds_bet`
   - `clv_pct = (odds_close - odds_bet) / odds_bet`
5. Re-run reports including CLV diagnostics.

---

## OddsPortal 24h Odds Movement Tracker (new)

Added tools:

- `scripts/oddsportal_one_match.py`
  - now parameterized (`--match-url`, `--market`, `--output`, `--storage-state`, `--headless`)
- `v2/tracking/schema_odds_tracker.sql`
  - sqlite schema for tracked matches, snapshots, and bookmaker quotes
- `v2/tracking/odds_tracker.py`
  - runner that samples odds every N minutes over a duration (default 24h)
  - writes to sqlite, optional JSONL append
  - robust to partial/missing rows and snapshot failures
- `v2/tracking/report_odds_movement.py`
  - reports bookmaker movement (first→last + delta) and best available odds over time
- `v2/tracking/odds_targets.example.json`
  - sample targets file

### Example: one snapshot

```bash
xvfb-run -a ./.venv312/bin/python scripts/oddsportal_one_match.py \
  --match-url "https://www.oddsportal.com/football/england/premier-league/brentford-wolves-0jR7cwU6/#1X2;2" \
  --market 1X2 \
  --output /tmp/oddsportal_match.json \
  --storage-state /tmp/oddsportal_storage.json
```

### Example: 24h tracking every 10 minutes

```bash
xvfb-run -a ./.venv312/bin/python -m v2.tracking.odds_tracker \
  --targets-json v2/tracking/odds_targets.example.json \
  --sample-every-min 10 \
  --duration-hours 24 \
  --between-match-delay-sec 8 \
  --sqlite data/v2/tracking/odds_tracker.sqlite \
  --schema v2/tracking/schema_odds_tracker.sql \
  --jsonl data/v2/tracking/odds_tracker.jsonl \
  --storage-state /tmp/oddsportal_storage.json
```

### Report movement

```bash
./.venv312/bin/python -m v2.tracking.report_odds_movement \
  --sqlite data/v2/tracking/odds_tracker.sqlite
```
