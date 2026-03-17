# v2/paper - reproducible 7-day paper trading pipeline

Lightweight stdlib-first paper trading flow for football value betting.

## What it supports

- Real fixtures from ESPN Scoreboard for league universe.
- Real odds fallback chain (default `--odds-provider espn`):
  1. **ESPN odds** (preferred)
  2. **SofaScore odds** (event odds endpoint)
  3. **The Odds API** (only if `ODDS_API_KEY` is configured)
- Deterministic replay via one JSON file (`--provider-json`) containing:
  - `matches` (fixtures)
  - `odds` (selection odds + source metadata)
  - `results` (final scores)
- Strict odds provenance written per bet:
  - `source_quality`: `real_odds` or `synthetic_odds`
  - `odds_source`: `espn` / `sofascore` / `odds_api` / `synthetic` / ...
- Synthetic odds are **disabled by default** and only used when explicitly enabled (`--allow-synthetic-odds` or `PAPER_ALLOW_SYNTHETIC_ODDS=1`).
- Selection constraints:
  - one best bet per match (strategy-level)
  - max bets per day (`PAPER_MAX_BETS_PER_DAY`)
  - max bets per league per day (`PAPER_MAX_BETS_PER_LEAGUE_PER_DAY`)
  - max stake fraction per bet (`PAPER_MAX_STAKE_FRACTION_PER_BET`)
  - max league exposure fraction per day (`PAPER_MAX_LEAGUE_EXPOSURE_FRACTION_PER_DAY`)
  - daily drawdown stop (-20%)
- Settlement correctness for OU/AH quarter lines (`0.25/0.75` split into half-lines).
- Decision logging JSONL per day with fields:
  - `match`, `market`, `line`, `odds_source`, `source_quality`, `model_prob`, `edge`, `kelly_stake`, `constraints_triggered`
- De-vig implied probabilities for 1X2 / OU / AH (toggle: `PAPER_DEVIG_ENABLED=1`).
- Daily + weekly markdown reports.
- 7-day final summary with:
  - final PnL / ROI / max drawdown / winrate / average edge
  - CLV summary (`avg_clv_abs`, `avg_clv_pct`, `clv_sample_size`) when closing odds exist
  - by market type
  - baseline comparison (flat stake vs kelly-fraction)

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
PAPER_MAX_STAKE_FRACTION_PER_BET=0.05
PAPER_MAX_LEAGUE_EXPOSURE_FRACTION_PER_DAY=0.20
PAPER_ALLOW_SYNTHETIC_ODDS=0
PAPER_FLAT_STAKE_FRACTION=0.02
PAPER_DEVIG_ENABLED=1
PAPER_CLOSING_ODDS_TRACKER_SQLITE=
# Optional: ODDS_API_KEY=...
```

## One-command 7-day simulation (primary deliverable)

### Recommended command

```bash
python3 scripts/paper_run_7d.py \
  --sqlite data/v2/tracking/bets.sqlite
```

Default behavior:
- runs 7 days ending yesterday in `Asia/Shanghai`
- starts from bankroll `2000` by default (override with `--bankroll`)
- uses real odds only

### Deterministic replay command

```bash
python3 scripts/paper_run_7d.py \
  --start-date 2026-03-10 \
  --bankroll 2000 \
  --provider-json tests/fixtures/paper7d_provider.json \
  --sqlite data/v2/tracking/bets.sqlite
```

### Expected outputs

- Per-day logs in stdout:
  - `[DAY YYYY-MM-DD] select(...) -> {...}`
  - `[DAY YYYY-MM-DD] settled(...) -> N`
  - `[DAY YYYY-MM-DD] reports -> ...`
- Final summary line in stdout:
  - `[7D SUMMARY] final_pnl=... roi=... max_dd=... winrate=...`
- Files generated:
  - `reports/v2/paper_7d_summary_YYYY-MM-DD.json`
  - `reports/v2/paper_7d_summary_YYYY-MM-DD.md`
  - `reports/v2/decisions/decisions_YYYY-MM-DD.jsonl`
  - `reports/v2/paper_daily_YYYY-MM-DD.md`
  - `reports/v2/paper_weekly_YYYY-MM-DD.md`

## One-day flow (debugging / smoke)

```bash
python3 scripts/paper_one_day.py --date 2026-03-15 --sqlite data/v2/tracking/bets.sqlite
```

With deterministic replay fixture:

```bash
python3 scripts/paper_one_day.py \
  --date 2026-03-15 \
  --provider-json tests/fixtures/mock_provider_day.json \
  --sqlite data/v2/tracking/bets.sqlite
```

## READY checklist (before starting live 7-day timer)

- [ ] `.env` configured.
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py'` passes.
- [ ] Tracking DB path writable.
- [ ] `scripts/paper_run_7d.py` runs end-to-end.
- [ ] Final summary markdown/json present with PnL/ROI/drawdown/winrate.
- [ ] Decision JSONL contains required fields.
- [ ] Synthetic odds are disabled unless explicitly requested.
ed.
