# v2/paper - 7-day paper trading pipeline

Implements a lightweight paper-trading loop for value betting in one combined strategy pool.

## Scope implemented

- League universe (combined pool):
  - Big-5: EPL, La Liga, Serie A, Bundesliga, Ligue 1
  - J1, K League 1, A-League Men, CSL
- Candidate generation per match across markets:
  - 1X2, Over/Under, Asian Handicap
- Single best bet per match by consistent metric:
  - Rank by fractional Kelly expected log-growth (with EV/edge filters)
- Staking and append logging into `v2/tracking` sqlite (`bet_log`)
- Settlement via ESPN scoreboard results provider
- Daily + weekly markdown reports
- 7-day orchestrator

## Provider interfaces

- `OddsProvider` interface
  - concrete: `OddsApiEspnPlaceholderProvider`
  - stub: `Pp88OddsProviderStub` (for future browser automation)
- `ResultsProvider` interface
  - concrete: `EspnResultsProvider`

## Daily risk rule

Before placing new bets on a day, the runner checks cumulative same-day PnL in `bet_log`.
If `day_pnl <= -20% * day_start_bankroll`, no new bets are placed for that day.

## Commands

Run one day selection+append:

```bash
python -m v2.paper.run_day --date 2026-03-15
```

Settle one day using ESPN final scores:

```bash
python -m v2.paper.settle --date 2026-03-15
```

Generate daily+weekly reports:

```bash
python -m v2.paper.report --date 2026-03-15 --sqlite data/v2/tracking/bets.sqlite
```

Run full 7-day loop:

```bash
python -m v2.paper.run_7d --start-date 2026-03-09
```

## READY checklist

- [ ] One-day end-to-end run succeeds (`run_day`)
- [ ] Settlement updates `result/profit/bankroll` (`settle`)
- [ ] Daily and weekly reports generated under `reports/v2/` (`report`)
- [ ] 7-day orchestrator completes without crashing (`run_7d`)
