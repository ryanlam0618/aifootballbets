# v2/paper - one-day + 7-day paper trading pipeline

Lightweight stdlib-first paper trading flow for football value betting.

## What it supports

- Real fixtures from ESPN Scoreboard for league universe.
- Real odds fallback chain (default `--odds-provider espn`):
  1. **ESPN odds** (preferred)
  2. **SofaScore odds** (event odds endpoint)
  3. **The Odds API** (only if `ODDS_API_KEY` is configured)
- Strict odds provenance written per bet:
  - `source_quality`: `real_odds` or `synthetic_odds`
  - `odds_source`: `espn` / `sofascore` / `odds_api` / `synthetic` / ...
- Results-only synthetic fallback when no real market odds are available for a match.
- Selection constraints:
  - one best bet per match (strategy-level)
  - max bets per day (`PAPER_MAX_BETS_PER_DAY`)
  - max bets per league per day (`PAPER_MAX_BETS_PER_LEAGUE_PER_DAY`)
- Settlement from ESPN/SofaScore results.
- CLV placeholder at settlement:
  - if closing odds can be fetched, store `odds_close`, `clv_abs`, `clv_pct`.
- Daily + weekly markdown reports with **source_quality split**.

## League universe

- EPL, La Liga, Serie A, Bundesliga, Ligue 1
- J1, K League 1, A-League Men, CSL

## Environment knobs

```bash
INITIAL_BANKROLL=2000
KELLY_FRACTION=0.75
MIN_EDGE=0.05
PAPER_MAX_BETS_PER_DAY=8
PAPER_MAX_BETS_PER_LEAGUE_PER_DAY=2
# Optional: ODDS_API_KEY=...
```

## Commands

Run one day selection+append:

```bash
python3 -m v2.paper.run_day --date 2026-03-15 --odds-provider espn
```

Settle one day:

```bash
python3 -m v2.paper.settle --date 2026-03-15 --results-provider espn
```

Generate daily+weekly reports:

```bash
python3 -m v2.paper.report --date 2026-03-15 --sqlite data/v2/tracking/bets.sqlite
```

Run full 7-day loop:

```bash
python3 -m v2.paper.run_7d \
  --start-date 2026-03-09 \
  --sqlite data/v2/tracking/bets.sqlite \
  --odds-provider espn \
  --results-provider espn \
  --run-prefix paper7d
```

## READY checklist (7-day simulation)

- [ ] `.env` configured (at least bankroll/edge/kelly; optional `ODDS_API_KEY`).
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` passes.
- [ ] Tracking DB path writable (`data/v2/tracking/bets.sqlite` or custom `--sqlite`).
- [ ] Run 7-day sim command above.
- [ ] Inspect generated reports in `reports/v2/`:
  - total PnL/ROI
  - `By source_quality` section (real vs synthetic separated)
- [ ] Optional: inspect CLV columns in sqlite (`odds_close`, `clv_abs`, `clv_pct`).

## One-command end-to-end (recommended)

From repo root:

```bash
python3 scripts/paper_one_day.py --date 2026-03-15 --sqlite data/v2/tracking/bets.sqlite
```

This runs: `run_day -> settle -> report`.
