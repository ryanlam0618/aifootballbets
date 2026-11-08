#!/usr/bin/env python3
"""afb-T12c: AH-only bootstrap + sensitivity - is the T12b AH edge real or path luck?

Question (Kris 2026-11-08 15:51): T12b's AH_pi numbers (flat +24,253 /
quarter-Kelly 17.15M / 1% bankroll 94,942) are single-path results - verify
whether they are a real edge or path luck.

Design:
- Bet records: the 4,204 AH model-pick bets from build_priced_bets() (pi
  primary; per-bet per-unit P/L, model pick probability, real odds, line).
  Zero leakage: same walk-forward as T9b/T11/T12.
- Bootstrap: 1,000 i.i.d. resamples (with replacement) of the 4,204 per-bet
  records; per staking scheme (flat 100 / quarter-Kelly cap 5% / 1%
  bankroll) simulate the bankroll journey per path. i.i.d. resampling tests
  whether the positive mean of the per-bet P/L distribution survives
  resampling; it does NOT model time/season clustering (documented caveat).
- Kelly fraction sensitivity: 1/8, 1/4, 1/2, full - point estimate on the
  actual sequence + bootstrap distribution per fraction.
- Line-depth split: shallow |line|<=0.5 / mid (0.5,1.5) / deep >=1.5 -
  per-bet ROI + flat-100 bootstrap per bucket (where does the +5.77% live?).
- Vig sensitivity: effective odds o_eff = 1 + (o-1)*(1-v), v in
  {0, 5%, 10%, 15%} - flat-100 ROI recomputed per level.
- DIMENSIONAL SANITY CHECK (T12 stake-bug lesson, mandatory): for every
  reported journey assert final == bankroll0 + sum(stake*pl_per_unit),
  total_staked == sum(stakes), and ROI == profit/total_staked - only then
  write the report.

Zero DB writes (SELECT-only via build_priced_bets).

Outputs: reports/bankroll_sim_t12c_report.json + .md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402
from scripts.bankroll_sim_t12 import build_priced_bets  # noqa: E402

BANKROLL0 = 10_000.0
KELLY_FRACTION = 0.25
KELLY_CAP = 0.05
FLAT = 100.0


# ------------------------------------------------------------- journeys

def journey_flat(pl: np.ndarray) -> dict:
    """Flat-100 journey; returns terminal value + bankrupt flag."""
    cum = np.cumsum(pl) * FLAT
    # bankrupt when bankroll < stake: 10000 + cum < 100
    cross = np.where(cum <= -(BANKROLL0 - FLAT))[0]
    if cross.size:
        i = cross[0]
        return {"final": BANKROLL0 + cum[i], "bankrupt": True, "stop_idx": int(i) + 1}
    return {"final": BANKROLL0 + cum[-1], "bankrupt": False,
            "stop_idx": int(len(pl))}


def journey_scaled(pl: np.ndarray, p: np.ndarray, odds: np.ndarray,
                   staking: str, kelly_fraction: float = KELLY_FRACTION) -> dict:
    """Sequential proportional journeys (kelly / pct1). Stake depends on the
    running bankroll, so this is a plain loop."""
    bankroll = BANKROLL0
    for i in range(len(pl)):
        if bankroll <= 0:
            return {"final": bankroll, "bankrupt": True, "stop_idx": i}
        if staking == "kelly":
            b_val = odds[i] - 1.0
            kelly_full = (p[i] * odds[i] - 1.0) / b_val if b_val > 0 else -1.0
            frac = kelly_full * kelly_fraction
            if frac <= 0:
                continue
            frac = min(frac, KELLY_CAP)
            stake = bankroll * frac
            if stake < 1.0:
                continue
        else:  # pct1
            stake = bankroll * 0.01
            if stake < 1.0:
                return {"final": bankroll, "bankrupt": True, "stop_idx": i}
        bankroll += pl[i] * stake
    return {"final": bankroll, "bankrupt": False, "stop_idx": len(pl)}


def bootstrap_stats(finals: np.ndarray) -> dict:
    pos_pct = float((finals > BANKROLL0).mean() * 100.0)
    return {
        "positive_paths_pct": round(pos_pct, 2),
        "median_final": round(float(np.median(finals)), 2),
        "p5": round(float(np.percentile(finals, 5)), 2),
        "p95": round(float(np.percentile(finals, 95)), 2),
        "min_final": round(float(finals.min()), 2),
        "max_final": round(float(finals.max()), 2),
    }


# --------------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description="T12c AH bootstrap + sensitivity")
    p.add_argument("--paths", type=int, default=1000)
    p.add_argument("--seed", type=int, default=20261108)
    p.add_argument("--out-prefix", type=str,
                   default=str(REPO_ROOT / "reports" / "bankroll_sim_t12c_report"))
    args = p.parse_args()
    rng = np.random.default_rng(args.seed)

    conn = afb_mysql_connect()
    cur = conn.cursor()
    final_1x2, final_ah, meta = build_priced_bets(conn, cur)

    # ---- AH bet records (pi primary) ----
    pl = np.array([b["pl_pi"] for b in final_ah], dtype=float)      # per-unit P/L
    pp = np.array([b["p_pi_pick"] for b in final_ah], dtype=float)  # model cover prob
    od = np.array([b["odds_pi"] for b in final_ah], dtype=float)    # real odds
    ln = np.array([abs(b["line"]) for b in final_ah], dtype=float)
    n = len(pl)
    print(f"[ah] {n} model-pick bets; raw per-unit ROI "
          f"{pl.sum() / n * 100:.2f}%")

    report: Dict[str, dict] = {"meta": {
        "ah_bets": n, "bootstrap_paths": args.paths, "seed": args.seed,
        "raw_per_unit_roi": round(float(pl.sum() / n), 5),
        "bootstrap_note": "i.i.d. resampling with replacement; does NOT model time/season clustering",
        "boundary": meta["boundary"], "train_n": meta["train_n"],
    }}

    # ---- dimensional sanity check (T12 lesson) on the ACTUAL sequence ----
    def sanity(name: str, stakes: np.ndarray, pls: np.ndarray, final: float) -> None:
        total = float(stakes.sum())
        profit = float((stakes * pls).sum())
        recon = BANKROLL0 + profit
        assert abs(total - float(stakes.sum())) < 1e-6
        assert abs(recon - final) < 0.01, \
            f"[SANITY FAIL] {name}: rebuilt {recon} != final {final}"
        roi = profit / total if total else 0.0
        assert abs((final - BANKROLL0) / total - roi) < 1e-6 or total == 0, \
            f"[SANITY FAIL] {name}: ROI mismatch"
        print(f"[sanity] {name}: total_staked={total:.2f} profit={profit:.2f} "
              f"final={final:.2f} OK")

    # ---- 1) point estimates on the ACTUAL sequence ----
    point = {}
    j = journey_flat(pl)
    sanity("flat", np.full(n, FLAT), pl, j["final"])
    point["flat"] = {**j, "total_staked": n * FLAT,
                     "roi_on_staked": round(float(pl.sum() * FLAT) / (n * FLAT), 5)}
    for frac, tag in ((0.125, "1/8"), (0.25, "1/4"), (0.5, "1/2"), (1.0, "full")):
        stakes_k = np.zeros(n)
        pls_k = np.zeros(n)
        bankroll = BANKROLL0
        for i in range(n):
            b_val = od[i] - 1.0
            kelly_full = (pp[i] * od[i] - 1.0) / b_val if b_val > 0 else -1.0
            frac_i = kelly_full * frac
            if frac_i <= 0:
                continue
            frac_i = min(frac_i, KELLY_CAP)
            stake = bankroll * frac_i
            if stake < 1.0:
                continue
            stakes_k[i] = stake
            pls_k[i] = pl[i]
            bankroll += pl[i] * stake
        sanity(f"kelly_{tag}", stakes_k, pls_k, bankroll)
        point[f"kelly_{tag}"] = {
            "final": round(bankroll, 2), "profit": round(bankroll - BANKROLL0, 2),
            "bets_placed": int((stakes_k > 0).sum()),
            "total_staked": round(float(stakes_k.sum()), 2),
            "roi_on_staked": round(float(pls_k.sum()) / float(stakes_k.sum()), 5)
            if stakes_k.sum() > 0 else None,
            "max_single_loss": round(float((stakes_k * pls_k).min()), 2),
        }
    stakes_p = np.full(n, 0.0)  # pct1 needs the running bankroll
    bankroll = BANKROLL0
    for i in range(n):
        stake = bankroll * 0.01
        stakes_p[i] = stake
        bankroll += pl[i] * stake
    sanity("pct1", stakes_p, pl, bankroll)
    point["pct1"] = {"final": round(bankroll, 2),
                     "profit": round(bankroll - BANKROLL0, 2),
                     "total_staked": round(float(stakes_p.sum()), 2),
                     "roi_on_staked": round(float((stakes_p * pl).sum())
                                            / float(stakes_p.sum()), 5)}
    report["point"] = point

    # ---- 2) bootstrap 1,000 paths per staking ----
    boot: Dict[str, dict] = {}
    idx_all = rng.integers(0, n, size=(args.paths, n))
    # flat (vectorised)
    finals = np.empty(args.paths)
    for k in range(args.paths):
        finals[k] = journey_flat(pl[idx_all[k]])["final"]
    boot["flat"] = bootstrap_stats(finals)
    boot["flat"]["bankruptcy_paths_pct"] = round(
        float(sum(journey_flat(pl[idx_all[k]])["bankrupt"]
                  for k in range(args.paths)) / args.paths * 100), 2)
    # kelly 1/4 + pct1 (sequential)
    for staking, tag in (("kelly", "kelly_1/4"), ("pct1", "pct1")):
        finals = np.empty(args.paths)
        for k in range(args.paths):
            r = journey_scaled(pl[idx_all[k]], pp[idx_all[k]], od[idx_all[k]], staking)
            finals[k] = r["final"]
        boot[tag] = bootstrap_stats(finals)
        boot[tag]["bankruptcy_paths_pct"] = round(
            float(sum(journey_scaled(pl[idx_all[k]], pp[idx_all[k]],
                                     od[idx_all[k]], staking)["bankrupt"]
                      for k in range(args.paths)) / args.paths * 100), 2)
    report["bootstrap"] = boot

    # ---- 3) Kelly fraction sensitivity (point + bootstrap) ----
    kelly_sens: Dict[str, dict] = {}
    for frac, tag in ((0.125, "1/8"), (0.25, "1/4"), (0.5, "1/2"), (1.0, "full")):
        bankroll = BANKROLL0
        for i in range(n):
            b_val = od[i] - 1.0
            kelly_full = (pp[i] * od[i] - 1.0) / b_val if b_val > 0 else -1.0
            frac_i = kelly_full * frac
            if frac_i <= 0:
                continue
            frac_i = min(frac_i, KELLY_CAP)
            stake = bankroll * frac_i
            if stake < 1.0:
                continue
            bankroll += pl[i] * stake
        finals = np.empty(args.paths)
        for k in range(args.paths):
            r = journey_scaled(pl[idx_all[k]], pp[idx_all[k]], od[idx_all[k]],
                               "kelly", kelly_fraction=frac)
            finals[k] = r["final"]
        kelly_sens[tag] = {
            "point_final": round(bankroll, 2),
            **{f"boot_{k}": v for k, v in bootstrap_stats(finals).items()},
        }
    report["kelly_sensitivity"] = kelly_sens

    # ---- 4) line-depth split (per-bet ROI + flat bootstrap per bucket) ----
    depth_split: Dict[str, dict] = {}
    buckets = (("shallow_<=0.5", ln <= 0.5),
               ("mid_0.5-1.5", (ln > 0.5) & (ln < 1.5)),
               ("deep_>=1.5", ln >= 1.5))
    for tag, mask in buckets:
        sub_pl = pl[mask]
        m = mask.sum()
        if m < 30:
            depth_split[tag] = {"n": int(m), "note": "too few bets"}
            continue
        finals = np.empty(args.paths)
        for k in range(args.paths):
            sidx = rng.integers(0, m, size=m)
            finals[k] = journey_flat(sub_pl[sidx])["final"]
        depth_split[tag] = {
            "n": int(m),
            "per_unit_roi": round(float(sub_pl.sum() / m), 5),
            "flat100_roi_on_staked": round(float(sub_pl.sum()) / m, 5),
            **bootstrap_stats(finals),
        }
    report["line_depth_split"] = depth_split

    # ---- 5) vig sensitivity (flat-100 ROI at HKJC-level costs) ----
    vig_sens: Dict[str, dict] = {}
    for v in (0.0, 0.05, 0.10, 0.15):
        o_eff = 1.0 + (od - 1.0) * (1.0 - v)
        # recompute per-unit P/L under the shrunken odds, same picks/outcomes:
        # the pick either wins (payout o_eff-1) or loses (-1); push (pl==0) stays 0
        pl_v = np.where(pl > 0, (o_eff - 1.0), np.where(pl < 0, -1.0, 0.0))
        # dimensional sanity (T12 lesson): pl_v.sum() is PER-UNIT; the
        # flat-100 profit is pl_v.sum()*FLAT and staked is n*FLAT, so
        # ROI = pl_v.sum()/n (NOT pl_v.sum()/(n*FLAT) - that was 100x low).
        profit_flat100 = float(pl_v.sum()) * FLAT
        roi = profit_flat100 / (n * FLAT)
        vig_sens[f"vig_{int(v*100)}pct"] = {
            "roi_on_staked": round(roi, 5),
            "profit_flat100": round(profit_flat100, 2),
        }
    report["vig_sensitivity"] = vig_sens

    Path(args.out_prefix + ".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# T12c AH BOOTSTRAP + SENSITIVITY (afb-T12c)", "",
             f"bets {n}; bootstrap {args.paths} i.i.d. paths (seed {args.seed});",
             "caveat: i.i.d. resampling does not model time/season clustering",
             "",
             "## point estimates (actual sequence)",
             f"- flat 100: {point['flat']}",
             f"- pct1: {point['pct1']}",
             "- kelly: " + "; ".join(f"{t}: final {point[f'kelly_{t}']['final']}"
                                     for t in ("1/8", "1/4", "1/2", "full")),
             "",
             "## bootstrap (1,000 paths)"]
    for tag in ("flat", "kelly_1/4", "pct1"):
        b = boot[tag]
        lines.append(f"- {tag}: positive {b['positive_paths_pct']}% | median "
                     f"{b['median_final']} | p5 {b['p5']} | p95 {b['p95']} | "
                     f"bankrupt {b['bankruptcy_paths_pct']}%")
    lines.append("")
    lines.append("## kelly fraction sensitivity")
    for t, v in kelly_sens.items():
        lines.append(f"- {t}: point {v['point_final']} | boot median {v['boot_median_final']} "
                     f"| p5 {v['boot_p5']} | p95 {v['boot_p95']}")
    lines.append("")
    lines.append("## line-depth split (where does the +5.77% live?)")
    for t, v in depth_split.items():
        lines.append(f"- {t}: {v}")
    lines.append("")
    lines.append("## vig sensitivity (flat-100 ROI)")
    for t, v in vig_sens.items():
        lines.append(f"- {t}: ROI {v['roi_on_staked']} | profit {v['profit_flat100']}")
    Path(args.out_prefix + ".md").write_text("\n".join(lines), encoding="utf-8")

    print("[done] wrote", args.out_prefix + ".json/.md")
    for tag in ("flat", "kelly_1/4", "pct1"):
        b = boot[tag]
        print(f"  boot {tag}: positive {b['positive_paths_pct']}% median "
              f"{b['median_final']} p5 {b['p5']} p95 {b['p95']}")
    for t, v in vig_sens.items():
        print(f"  {t}: ROI {v['roi_on_staked']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
