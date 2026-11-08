#!/usr/bin/env python3
"""afb-T12b: dynamic staking simulation - flat vs quarter-Kelly vs 1% bankroll.

Question (Kris 2026-11-08 15:07): "跑咗先知會唔會輸" - on top of the T12
model-pick bet streams (NO edge filter, model's own pick), compare three
staking schemes:

  1. flat 100        (T12 baseline)
  2. quarter Kelly   stake = bankroll * (p_model*odds - 1)/(odds-1) / 4,
                     capped at 5% of bankroll per bet; skipped when the full
                     Kelly fraction is <= 0 (negative model EV at these odds)
  3. bankroll 1%     stake = 1% of the CURRENT bankroll (scales both ways)

Same T12 samples (T9b/T11 test halves, ~6,919 bets), same pick rule, same
settlement (pre-de-vig closing odds; T1 quarter-line rules for AH), same
walk-forward discipline (DC frozen at the boundary, pi as-of walk-forward).
Matrix: 3 stakings x {1x2, AH, combined} x {pi, dc} = 18 portfolios.

Kelly special report: max single-bet loss, max stake as % of bankroll, stake
volatility, longest heavy-bet streak (>=2% bankroll).

Zero DB writes. Expected: with a noise edge, Kelly amplifies variance and can
end WORSE than flat - reported as-is.

Outputs: reports/bankroll_sim_t12b_report.json + .md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402
from scripts.bankroll_sim_t12 import build_priced_bets  # noqa: E402

BANKROLL0 = 10_000.0
KELLY_FRACTION = 0.25          # quarter Kelly
KELLY_CAP = 0.05               # max 5% of bankroll per bet


# ------------------------------------------------------- staking + journeys

def run_journey(bets: List[dict], staking: str) -> dict:
    """Chronological journey with the given staking scheme.

    Each bet dict carries: pl_per_unit (P/L for a 1-unit stake), p_pick
    (model probability of the picked side), odds (real decimal odds of the
    picked side).
    """
    bankroll = BANKROLL0
    curve = [bankroll]
    peak = bankroll
    max_dd = 0.0
    wins = losses = pushes = skipped = 0
    total_staked = 0.0
    bankrupt_at = None
    stakes: List[float] = []
    max_single_loss = 0.0
    max_single_loss_pct = 0.0
    max_stake_pct = 0.0
    heavy_streak = longest_heavy = 0

    for i, b in enumerate(bets, start=1):
        if bankroll <= 0:
            bankrupt_at = i - 1
            break
        if staking == "flat":
            stake = 100.0
            if bankroll < stake:
                bankrupt_at = i - 1
                break
        elif staking == "kelly":
            b_val = b["odds"] - 1.0
            kelly_full = (b["p_pick"] * b["odds"] - 1.0) / b_val if b_val > 0 else -1.0
            frac = kelly_full * KELLY_FRACTION
            if frac <= 0:
                skipped += 1
                continue
            frac = min(frac, KELLY_CAP)
            stake = bankroll * frac
            stake = round(stake, 2)
            if stake < 1.0:
                skipped += 1
                continue
        elif staking == "pct1":
            stake = round(bankroll * 0.01, 2)
            if stake < 1.0:
                bankrupt_at = i - 1
                break
        else:
            raise ValueError(staking)

        pl_per_unit = b["pl_per_unit"]
        pl = pl_per_unit * stake
        bankroll += pl
        total_staked += stake
        stakes.append(stake)
        stake_pct = stake / bankroll if bankroll > 0 else 0.0
        max_stake_pct = max(max_stake_pct, stake_pct)
        if pl < 0:
            losses += 1
            if -pl > max_single_loss:
                max_single_loss = -pl
                max_single_loss_pct = -pl / (bankroll - pl) if (bankroll - pl) > 0 else 0.0
        elif pl > 0:
            wins += 1
        else:
            pushes += 1
        if stake_pct >= 0.02:
            heavy_streak += 1
            longest_heavy = max(longest_heavy, heavy_streak)
        else:
            heavy_streak = 0
        curve.append(bankroll)
        if bankroll > peak:
            peak = bankroll
        dd = peak - bankroll
        if dd > max_dd:
            max_dd = dd
        if bankroll <= 0:
            bankrupt_at = i
            break

    stake_std = 0.0
    if len(stakes) > 1:
        mean = sum(stakes) / len(stakes)
        stake_std = (sum((x - mean) ** 2 for x in stakes) / (len(stakes) - 1)) ** 0.5
    return {
        "final_bankroll": round(bankroll, 2),
        "bets_placed": len(curve) - 1,
        "skipped": skipped,
        "total_staked": round(total_staked, 2),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "max_drawdown": round(max_dd, 2),
        "peak_bankroll": round(peak, 2),
        "min_bankroll": round(min(curve), 2),
        "bankrupt_at_bet": bankrupt_at,
        "bankrupt": bankrupt_at is not None,
        "profit": round(bankroll - BANKROLL0, 2),
        "max_single_loss": round(max_single_loss, 2),
        "max_single_loss_pct_of_bankroll": round(max_single_loss_pct, 4),
        "max_stake_pct": round(max_stake_pct, 4),
        "stake_std": round(stake_std, 2),
        "longest_heavy_streak_2pct": longest_heavy,
    }


# --------------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description="T12b dynamic staking simulation")
    p.add_argument("--out-prefix", type=str,
                   default=str(REPO_ROOT / "reports" / "bankroll_sim_t12b_report"))
    args = p.parse_args()

    conn = afb_mysql_connect()
    cur = conn.cursor()

    final_1x2, final_ah, meta = build_priced_bets(conn, cur)
    combined = sorted(final_1x2 + final_ah, key=lambda b: (b["date"], b["match_id"]))

    # normalise bet streams: per-unit P/L + pick prob + real odds per model
    def stream_1x2(model: str) -> List[dict]:
        return [{"date": b["date"], "match_id": b["match_id"], "league": b["league"],
                 "pl_per_unit": b[f"pl_{model}"], "p_pick": b[f"p_{model}_pick"],
                 "odds": b[f"odds_{model}"]} for b in final_1x2]

    def stream_ah(model: str) -> List[dict]:
        return [{"date": b["date"], "match_id": b["match_id"], "league": b["league"],
                 "pl_per_unit": b[f"pl_{model}"], "p_pick": b[f"p_{model}_pick"],
                 "odds": b[f"odds_{model}"]} for b in final_ah]

    def stream_combined(model: str) -> List[dict]:
        return sorted(stream_1x2(model) + stream_ah(model),
                      key=lambda b: (b["date"], b["match_id"]))

    portfolios: Dict[str, dict] = {}
    for model in ("pi", "dc"):
        for market, stream in (("1x2", stream_1x2(model)),
                               ("ah", stream_ah(model)),
                               ("combined", stream_combined(model))):
            for staking in ("flat", "kelly", "pct1"):
                name = f"{market}_{model}_{staking}"
                portfolios[name] = run_journey(stream, staking)

    report = {
        "meta": {"bankroll0": BANKROLL0,
                 "kelly": {"fraction": KELLY_FRACTION, "cap_pct": KELLY_CAP,
                           "skip_when_kelly_le_0": True},
                 "pct1": {"fraction": 0.01},
                 "pick_rule": "model's own pick (no edge filter), same as T12",
                 "settlement": "pre-de-vig closing odds; T1 quarter-line rules",
                 **meta},
        "portfolios": portfolios,
    }
    Path(args.out_prefix + ".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# T12b DYNAMIC STAKING SIMULATION (afb-T12b)", "",
             f"bankroll0={BANKROLL0:.0f}; pick rule = model's own pick (no edge filter);",
             "staking: flat 100 | quarter-Kelly (cap 5%/bet, skip kelly<=0) | bankroll 1%",
             f"1x2 bets {meta['1x2_bets']}; AH bets {meta['ah_bets']}; boundary {meta['boundary']}",
             ""]
    for model in ("pi", "dc"):
        for market in ("1x2", "ah", "combined"):
            for staking in ("flat", "kelly", "pct1"):
                name = f"{market}_{model}_{staking}"
                r = portfolios[name]
                lines.append(f"## {name}")
                for k, v in r.items():
                    lines.append(f"- {k}: {v}")
                lines.append("")
    Path(args.out_prefix + ".md").write_text("\n".join(lines), encoding="utf-8")

    print("[done] wrote", args.out_prefix + ".json/.md")
    for name, r in portfolios.items():
        print(f"  {name}: final={r['final_bankroll']} bets={r['bets_placed']} "
              f"skip={r['skipped']} W/L/P={r['wins']}/{r['losses']}/{r['pushes']} "
              f"maxDD={r['max_drawdown']} maxLoss={r['max_single_loss']} "
              f"bankrupt={r['bankrupt']}"
              + (f" at bet {r['bankrupt_at_bet']}" if r["bankrupt_at_bet"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
