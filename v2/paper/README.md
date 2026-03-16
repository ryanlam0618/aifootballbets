# v2/paper - one-day + 7-day paper trading pipeline

Lightweight stdlib-first paper trading flow for football value betting.

## What it now supports

- Real fixtures from ESPN Scoreboard for league universe
- Odds from ESPN Scoreboard when available (1X2, spreads, totals)
- Optional fallback odds from The Odds API **only if** `ODDS_API_KEY` is configured
- Results-only mode when no external odds exist:
  - still uses real ESPN fixtures/results
  - injects synthetic odds so candidate generation + selection can run
- Settlement from ESPN final scores with robust mapping by:
  - stored `match_id` (preferred)
  - normalized home/away names (fallback)
- Daily + weekly markdown reports

## League universe

- EPL, La Liga, Serie A, Bundesliga, Ligue 1
- J1, K League 1, A-League Men, CSL

## Daily risk rule

If same-day settled PnL is `<= -20%` of day-start bankroll, stop placing new bets for that day.

## Commands

Run one day selection+append:

```bash
python3 -m v2.paper.run_day --date 2026-03-15
```

Settle one day using ESPN final scores:

```bash
python3 -m v2.paper.settle --date 2026-03-15
```

Generate daily+weekly reports:

```bash
python3 -m v2.paper.report --date 2026-03-15 --sqlite data/v2/tracking/bets.sqlite
```

Run full 7-day loop:

```bash
python3 -m v2.paper.run_7d --start-date 2026-03-09
```

## One-command end-to-end (recommended)

From repo root:

```bash
python3 scripts/paper_one_day.py --date 2026-03-15 --sqlite data/v2/tracking/bets.sqlite
```

This runs: `run_day -> settle -> report`.
