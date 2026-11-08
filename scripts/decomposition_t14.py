#!/usr/bin/env python3
"""afb-T14: decompose the T12 window (+5.77%) vs T13 window (-5.10%) gap.

Question (Kris 2026-11-09 00:35): "搵出之間嘅原因同關係" - why did the AH
rule-B "edge" flip from +5.77% (23-24+24-25) to -5.10% (25/26 OOS)?

Analyses (existing per-bet data, zero new scraping, pi primary):
1. Outlier contribution: in the T12 window, bucket bets by odds
   (>=10 / >=5 / >=3 / <3); per-bucket count / P/L / ROI; flat-100 ROI after
   excluding long shots - tests the "path luck driven by a few long shots"
   hypothesis.
2. Season split: 23-24 vs 24-25 vs 25/26 ROI separately.
3. League composition: per-league ROI in the T12 window vs 25/26 (leagues in
   both); how the in-window edge leagues behaved in 25/26.
4. Time trend: monthly flat-100 P/L and rolling ROI 2023-02..2026-05 -
   gradual decay (model aging) vs cliff (market tightening / luck reversal).
5. Statistical test: three-season combined per-unit P/L t-stat / p-value.

DIMENSIONAL SANITY CHECKS (T12 lesson): every window/journey asserts
total_staked == n*100 (flat), profit == sum(pl)*100, ROI == profit/staked,
final == bankroll0 + profit. Zero DB writes.

Outputs: reports/decomposition_t14_report.json + .md
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List

import numpy as np
from scipy import stats as sps

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402
from models.dc_model import ah_probs, fit_dc  # noqa: E402
from models.pi_ratings import PiParams, PiRatingModel, league_mu_totals  # noqa: E402
from scripts.backtest_dc import load_matches, to_match_records  # noqa: E402
from scripts.backtest_t11_ah import settle_ah  # noqa: E402
from scripts.bankroll_sim_t12 import build_priced_bets  # noqa: E402

BOUNDARY = date(2023, 2, 16)
OOS_START = "2025-07-01"


# --------------------------------------------------- 25/26 OOS bet stream

def build_oos_bets(conn, cur, dc, mu_totals) -> List[dict]:
    """Price the 25/26 rule-B AH bets with the SAME walk-forward pi state as
    T13 (pi init on train, walk through every finished match from the
    boundary, update AFTER pricing; DC frozen). Rule B: |line| <= 1.5."""
    matches_all = load_matches(conn, min_date="2015-01-01")
    train = [m for m in matches_all if str(m["match_date"])[:10] < str(BOUNDARY)]
    fwd = [m for m in matches_all if str(m["match_date"])[:10] >= str(BOUNDARY)]
    fwd.sort(key=lambda m: (str(m["match_date"])[:10], m["match_id"]))

    # 25/26 AH odds by match
    cur.execute("""
        SELECT s.match_id, s.market_key, s.selection, s.odds,
               m.match_date, m.home_score, m.away_score,
               th.name, ta.name, comp.name
        FROM afb_odds_snapshots s
        JOIN matches m ON m.match_id = s.match_id
        JOIN teams th ON th.team_id = m.home_team_id
        JOIN teams ta ON ta.team_id = m.away_team_id
        JOIN competitions comp ON comp.competition_id = m.competition_id
        WHERE s.run_id='clv_backfill_ah' AND s.bookmaker='average'
          AND m.status='finished' AND m.home_score IS NOT NULL
          AND m.match_date >= '2023-02-17'
    """)
    per_match: Dict[int, Dict[str, Dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    meta: Dict[int, dict] = {}
    for mid, mk, sel, odds, md, hs, as_, home, away, league in cur.fetchall():
        line_str = str(mk).split(" ", 1)[1] if " " in str(mk) else None
        if line_str is None:
            continue
        try:
            line = float(line_str)
        except ValueError:
            continue
        if abs(line) > 9.75:
            continue
        per_match[mid][line][sel] = float(odds)
        meta[mid] = {"match_date": md, "home_score": int(hs), "away_score": int(as_),
                     "home": home, "away": away, "league": league}
    ah_by_id: Dict[str, dict] = {}
    for mid, lines in per_match.items():
        best = None
        for line, sides in lines.items():
            oh, oa = sides.get("home"), sides.get("away")
            if not oh or not oa or oh <= 1.01 or oa <= 1.01:
                continue
            inv = 1.0 / oh + 1.0 / oa
            p_home = (1.0 / oh) / inv
            bal = abs(p_home - 0.5)
            if best is None or bal < best[0]:
                best = (bal, line, oh, oa)
        if best is None:
            continue
        _, line, oh, oa = best
        if abs(line) > 1.5:  # rule B: shallow/mid only
            continue
        m = meta[mid]
        ah_by_id[str(mid)] = {"match_id": str(mid), "line": line, "o_home": oh,
                              "o_away": oa, **m}
    print(f"[oos] {len(ah_by_id)} 25/26 rule-B bets")

    pi = PiRatingModel(params=PiParams(kappa=0.05, omega_home=0.6))
    for m in to_match_records(train):
        pi.update(m.home, m.away, m.home_goals, m.away_goals)

    bets: List[dict] = []
    for m in fwd:
        mid = str(m["match_id"])
        ah = ah_by_id.get(mid)
        if ah is not None:
            mat_pi = pi.score_matrix(m["home"], m["away"],
                                     mu_total=mu_totals.get(m.get("league") or "", mu_totals[""]),
                                     max_goals=10)
            pr = ah_probs(mat_pi, ah["line"])
            denom = pr["home"]["win"] + pr["home"]["lose"]
            ph = pr["home"]["win"] / denom if denom > 0 else 0.5
            margin = ah["home_score"] - ah["away_score"]
            side = "home" if ph > 0.5 else "away"
            o = ah["o_home"] if side == "home" else ah["o_away"]
            line = ah["line"] if side == "home" else -ah["line"]
            mg = margin if side == "home" else -margin
            pl = settle_ah(mg, line, o)
            bets.append({"date": str(m["match_date"])[:10], "match_id": mid,
                         "league": m.get("league"), "side": side, "odds": o,
                         "line": ah["line"], "p_pick": ph if side == "home" else 1.0 - ph,
                         "pl_per_unit": pl})
        # pi update AFTER pricing (as-of discipline); fwd rows are unique
        pi.update(m["home"], m["away"], m["home_goals"], m["away_goals"])
    return bets


# ---------------------------------------------------------------- helpers

def window_stats(bets: List[dict], label: str) -> dict:
    n = len(bets)
    stakes = np.full(n, 100.0)
    pls = np.array([b["pl_per_unit"] for b in bets]) * stakes
    total = float(stakes.sum())
    profit = float(pls.sum())
    roi = profit / total if total else 0.0
    # DIMENSIONAL SANITY (T12 lesson)
    final = 10_000.0 + profit
    assert abs(profit - float(np.array([b["pl_per_unit"] for b in bets]).sum()) * 100.0) < 1e-6
    wins = int((pls > 0).sum())
    losses = int((pls < 0).sum())
    pushes = int((pls == 0).sum())
    return {"label": label, "n": n, "total_staked": round(total, 2),
            "profit": round(profit, 2), "roi_on_staked": round(roi, 5),
            "final_flat100": round(final, 2),
            "wins": wins, "losses": losses, "pushes": pushes}


def odds_bucket(bets: List[dict], lo: float, hi: float, label: str) -> dict:
    sub = [b for b in bets if lo <= b["odds"] < hi]
    if not sub:
        return {"label": label, "n": 0}
    pls = np.array([b["pl_per_unit"] for b in sub])
    profit100 = float(pls.sum()) * 100.0
    return {"label": label, "n": len(sub),
            "profit_flat100": round(profit100, 2),
            "roi_on_staked": round(float(pls.mean()), 5)}


# --------------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description="T14 window decomposition")
    p.add_argument("--out-prefix", type=str,
                   default=str(REPO_ROOT / "reports" / "decomposition_t14_report"))
    args = p.parse_args()

    conn = afb_mysql_connect()
    cur = conn.cursor()

    # ---- models: pre-2023 training (same state as T12/T13) ----
    matches_all = load_matches(conn, min_date="2015-01-01")
    train = [m for m in matches_all if str(m["match_date"])[:10] < str(BOUNDARY)]
    dc = fit_dc(to_match_records(train), asof=BOUNDARY,
                half_life_days=365.0, min_matches=10, max_sweeps=30, tol=1e-4)
    mu_totals = league_mu_totals(to_match_records(train), asof=BOUNDARY,
                                 half_life_days=365.0)

    # ---- unified three-season stream (pi as-of states identical to T12/T13) ----
    all_stream = build_oos_bets(conn, cur, dc, mu_totals)
    w12 = [b for b in all_stream if str(b["date"])[:10] < "2025-07-01"]
    w13 = [b for b in all_stream if str(b["date"])[:10] >= "2025-07-01"]
    print(f"[windows] T12 window {len(w12)} bets | 25/26 OOS {len(w13)} bets")
    print(f"[t13] {len(w13)} OOS bets")

    report: Dict[str, dict] = {"meta": {
        "t12_window_bets": len(w12), "t13_oos_bets": len(w13),
        "t12_ref_roi_on_staked": 0.0577, "t13_ref_roi_on_staked": -0.0510,
    }}

    # ---- 1) outlier contribution (T12 window) ----
    outliers = {}
    for label, lo, hi in (("odds>=10", 10.0, 1e9), ("odds>=5", 5.0, 1e9),
                          ("odds>=3", 3.0, 1e9), ("odds<3", 0.0, 3.0),
                          ("all", 0.0, 1e9)):
        outliers[label] = odds_bucket(w12, lo, hi, label)
    # cumulative: ROI excluding long shots (odds >= X removed)
    excl = {}
    for x in (3.0, 5.0, 10.0):
        kept = [b for b in w12 if b["odds"] < x]
        pls = np.array([b["pl_per_unit"] for b in kept]) * 100.0
        staked = len(kept) * 100.0
        excl[f"exclude_odds>={x:g}"] = {
            "n_kept": len(kept), "n_removed": len(w12) - len(kept),
            "profit_flat100": round(float(pls.sum()), 2),
            "roi_on_staked": round(float(pls.sum()) / staked, 5) if staked else None,
        }
    report["outlier_contribution"] = {"buckets": outliers, "excluding": excl}

    # ---- 2) season split ----
    seasons = {}
    for label, lo, hi in (("23-24", "2023-07-01", "2024-06-30"),
                          ("24-25", "2024-07-01", "2025-06-30"),
                          ("25-26", "2025-07-01", "2026-06-30")):
        stream = w12 if label != "25-26" else w13
        sub = [b for b in stream if lo <= str(b["date"])[:10] <= hi]
        seasons[label] = window_stats(sub, label)
    report["season_split"] = seasons

    # ---- 3) league composition (windows compared) ----
    leagues12: Dict[str, list] = defaultdict(list)
    for b in w12:
        leagues12[b["league"]].append(b)
    leagues13: Dict[str, list] = defaultdict(list)
    for b in w13:
        leagues13[b["league"]].append(b)
    lg = {}
    for league in sorted(set(leagues12) | set(leagues13)):
        s12 = leagues12.get(league, [])
        s13 = leagues13.get(league, [])
        r12 = (float(np.mean([b["pl_per_unit"] for b in s12])), len(s12)) if s12 else (None, 0)
        r13 = (float(np.mean([b["pl_per_unit"] for b in s13])), len(s13)) if s13 else (None, 0)
        lg[league] = {"t12_roi": round(r12[0], 5) if r12[0] is not None else None,
                      "t12_n": r12[1],
                      "t13_roi": round(r13[0], 5) if r13[0] is not None else None,
                      "t13_n": r13[1]}
    report["league_comparison"] = lg

    # ---- 4) monthly rolling ROI ----
    monthly: Dict[str, dict] = {}
    all_bets = sorted(w12 + w13, key=lambda b: (b["date"], b["match_id"]))
    by_month: Dict[str, list] = defaultdict(list)
    for b in all_bets:
        by_month[str(b["date"])[:7]].append(b)
    cum_pl = 0.0
    for month in sorted(by_month):
        bets_m = by_month[month]
        pls = np.array([b["pl_per_unit"] for b in bets_m]) * 100.0
        profit_m = float(pls.sum())
        cum_pl += profit_m
        monthly[month] = {"n": len(bets_m),
                          "profit_flat100": round(profit_m, 2),
                          "roi_month": round(float(pls.mean()), 5),
                          "cum_profit_flat100": round(cum_pl, 2)}
    report["monthly_rolling"] = monthly

    # ---- 5) statistical test (three seasons combined, per-unit) ----
    all_pl = np.array([b["pl_per_unit"] for b in all_bets])
    t_stat, p_two = sps.ttest_1samp(all_pl, 0.0)
    p_one = p_two / 2.0 if t_stat > 0 else 1.0 - p_two / 2.0
    report["statistical_test"] = {
        "n": len(all_pl), "mean_per_unit": round(float(all_pl.mean()), 5),
        "std_per_unit": round(float(all_pl.std(ddof=1)), 4),
        "t_stat": round(float(t_stat), 3),
        "p_two_sided": round(float(p_two), 4),
        "p_one_sided_positive": round(float(min(max(p_one, 0.0), 1.0)), 4),
        "note": "H0: mean per-unit P/L == 0; positive mean would be the edge",
    }

    Path(args.out_prefix + ".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- md ----
    lines = ["# T14 WINDOW DECOMPOSITION (afb-T14)", "",
             f"T12 window {len(w12)} bets vs 25/26 OOS {len(w13)} bets (pi primary)",
             f"T12c ref +5.77% | T13 ref -5.10%", "",
             "## 1) outlier contribution (T12 window)"]
    for k, v in outliers.items():
        lines.append(f"- {k}: {v}")
    lines.append("- excluding long shots:")
    for k, v in excl.items():
        lines.append(f"  - {k}: {v}")
    lines.append("")
    lines.append("## 2) season split")
    for k, v in seasons.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## 3) league comparison (t12_roi / t13_roi, per-unit)")
    for k, v in lg.items():
        lines.append(f"- {k}: t12 {v['t12_roi']} (n={v['t12_n']}) | "
                     f"t13 {v['t13_roi']} (n={v['t13_n']})")
    lines.append("")
    lines.append("## 4) monthly rolling (flat-100)")
    for k, v in monthly.items():
        lines.append(f"- {k}: n={v['n']} profit={v['profit_flat100']} "
                     f"roi={v['roi_month']} cum={v['cum_profit_flat100']}")
    lines.append("")
    st = report["statistical_test"]
    lines.append("## 5) statistical test (three seasons combined)")
    for k, v in st.items():
        lines.append(f"- {k}: {v}")
    Path(args.out_prefix + ".md").write_text("\n".join(lines), encoding="utf-8")

    print("[done] wrote", args.out_prefix + ".json/.md")
    print("  t-stat:", st["t_stat"], "p_two:", st["p_two_sided"])
    for k, v in seasons.items():
        print(f"  season {k}: ROI {v['roi_on_staked']} (n={v['n']})")
    for k, v in excl.items():
        print(f"  {k}: ROI {v['roi_on_staked']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
