#!/usr/bin/env python3
"""afb-T13: 25/26 season OUT-OF-SAMPLE validation of the AH model-pick rule.

Question (Kris 2026-11-08 20:57): the T12c window (23-24+24-25 test half)
showed rule B (model's favourite on AH shallow/mid lines) at +5.77% flat-100
ROI, bootstrap-robust WITHIN the window. The model training boundary is
2023-02-16, so the 25/26 season (finished May 2026) is PURE out-of-sample.
Scrape its AH odds (T10 pipeline) and re-run rule B: replicate or flip?

Zero-leakage design:
- Model: the SAME pre-2023-trained models - DC frozen at 2023-02-16 (NEVER
  retrained on 25/26 data); pi-ratings initialised on all finished matches
  before the boundary, then walk-forward through EVERY finished match in
  date order (23-24 -> 24-25 -> 25/26), pricing each 25/26 AH match as-of
  (update AFTER pricing). pi legitimately consumes past results only.
- Rule B: bet the side with model cover prob > 0.5, ONLY on shallow/mid
  lines (|line| <= 1.5; T12c showed deep lines carry no edge).
- Settlement: pre-de-vig closing odds (average-view quotes) + T1
  quarter-line rules.
- Staking: flat 100 / quarter-Kelly (cap 5%, skip kelly<=0) / 1% bankroll.
- Bootstrap: 1,000 i.i.d. paths per staking (same T12c method).
- DIMENSIONAL SANITY CHECKS mandatory (T12 stake-bug lesson).
- Comparison: 25/26 vs the T12c window (+5.77% overall; shallow +6.83% /
  mid +7.22% / deep -0.81%), item by item.

Zero DB writes. If it flips - reported as-is.

Outputs: reports/bankroll_sim_t13_oos_report.json + .md
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

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402
from models.dc_model import ah_probs, fit_dc  # noqa: E402
from models.pi_ratings import PiParams, PiRatingModel, league_mu_totals  # noqa: E402
from scripts.backtest_dc import load_matches, to_match_records  # noqa: E402
from scripts.backtest_t11_ah import settle_ah  # noqa: E402
from scripts.bankroll_sim_t12 import build_priced_bets  # noqa: E402

BANKROLL0 = 10_000.0
KELLY_FRACTION = 0.25
KELLY_CAP = 0.05
BOUNDARY = date(2023, 2, 16)
OOS_START = "2025-07-01"
MAX_LINE = 1.5  # rule B: shallow/mid lines only


# ------------------------------------------------------- 25/26 AH sample

def load_ah_sample_oos(cur) -> List[dict]:
    """One row per 25/26 match: main line (closest to balanced), quotes."""
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
          AND m.match_date >= '2025-07-01'
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
        if abs(line) > 9.75:  # scrape artifacts (T12 lesson)
            continue
        per_match[mid][line][sel] = float(odds)
        meta[mid] = {"match_date": md, "home_score": int(hs), "away_score": int(as_),
                     "home": home, "away": away, "league": league}
    out: List[dict] = []
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
        m = meta[mid]
        out.append({"match_id": mid, "line": line, "o_home": oh, "o_away": oa, **m})
    out.sort(key=lambda r: (str(r["match_date"])[:10], r["match_id"]))
    return out


# ------------------------------------------------------------- staking

def run_journey(bets: List[dict], staking: str) -> dict:
    bankroll = BANKROLL0
    curve = [bankroll]
    peak = bankroll
    max_dd = 0.0
    wins = losses = pushes = skipped = 0
    total_staked = 0.0
    bankrupt_at = None
    stakes: List[float] = []
    staked_pls: List[float] = []  # pl_per_unit of each STAKED bet (skip-aware)
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
            if stake < 1.0:
                continue
        else:  # pct1
            stake = bankroll * 0.01
            if stake < 1.0:
                bankrupt_at = i - 1
                break
        pl = b["pl_per_unit"] * stake
        bankroll += pl
        total_staked += stake
        stakes.append(stake)
        staked_pls.append(b["pl_per_unit"])
        if pl > 0:
            wins += 1
        elif pl < 0:
            losses += 1
        else:
            pushes += 1
        curve.append(bankroll)
        if bankroll > peak:
            peak = bankroll
        dd = peak - bankroll
        if dd > max_dd:
            max_dd = dd
        if bankroll <= 0:
            bankrupt_at = i
            break
    # DIMENSIONAL SANITY (T12 lesson): rebuild from the staked (stake, pl)
    # pairs - skip-aware, so skipped bets never desync the pairing
    rebuilt = BANKROLL0 + sum(s * p_ for s, p_ in zip(stakes, staked_pls))
    assert abs(rebuilt - bankroll) < 0.01, \
        f"[SANITY FAIL] {staking}: rebuilt {rebuilt} != final {bankroll}"
    roi = (bankroll - BANKROLL0) / total_staked if total_staked else 0.0
    return {
        "final_bankroll": round(bankroll, 2),
        "bets_placed": len(curve) - 1,
        "skipped": skipped,
        "total_staked": round(total_staked, 2),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "max_drawdown": round(max_dd, 2),
        "min_bankroll": round(min(curve), 2),
        "bankrupt_at_bet": bankrupt_at,
        "bankrupt": bankrupt_at is not None,
        "profit": round(bankroll - BANKROLL0, 2),
        "roi_on_staked": round(roi, 5),
    }


def bootstrap_stats(finals: np.ndarray) -> dict:
    return {
        "positive_paths_pct": round(float((finals > BANKROLL0).mean() * 100.0), 2),
        "median_final": round(float(np.median(finals)), 2),
        "p5": round(float(np.percentile(finals, 5)), 2),
        "p95": round(float(np.percentile(finals, 95)), 2),
        "min_final": round(float(finals.min()), 2),
        "max_final": round(float(finals.max()), 2),
    }


# --------------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description="T13 25/26 OOS validation")
    p.add_argument("--paths", type=int, default=1000)
    p.add_argument("--seed", type=int, default=20261108)
    p.add_argument("--out-prefix", type=str,
                   default=str(REPO_ROOT / "reports" / "bankroll_sim_t13_oos_report"))
    args = p.parse_args()
    rng = np.random.default_rng(args.seed)

    conn = afb_mysql_connect()
    cur = conn.cursor()

    # ---- 25/26 AH sample ----
    sample = load_ah_sample_oos(cur)
    rule_b = [r for r in sample if abs(r["line"]) <= MAX_LINE]
    print(f"[oos] {len(sample)} 25/26 matches with AH; rule B (|line|<={MAX_LINE}): {len(rule_b)}")

    # ---- models: pre-2023 training, zero retraining ----
    matches_all = load_matches(conn, min_date="2015-01-01")
    train = [m for m in matches_all if str(m["match_date"])[:10] < str(BOUNDARY)]
    print(f"[train] {len(train)} matches before {BOUNDARY}")
    dc = fit_dc(to_match_records(train), asof=BOUNDARY,
                half_life_days=365.0, min_matches=10, max_sweeps=30, tol=1e-4)

    # ---- walk-forward universe: every finished match from the boundary on ----
    fwd = [m for m in matches_all if str(m["match_date"])[:10] >= str(BOUNDARY)]
    fwd.sort(key=lambda m: (str(m["match_date"])[:10], m["match_id"]))
    ah_by_key = {(str(r["match_date"])[:10], str(r["home"]).lower(), str(r["away"]).lower()): r
                 for r in rule_b}
    # match the AH sample to walk-forward rows by match_id instead:
    ah_by_id = {str(r["match_id"]): r for r in rule_b}

    pi = PiRatingModel(params=PiParams(kappa=0.05, omega_home=0.6))
    for m in to_match_records(train):
        pi.update(m.home, m.away, m.home_goals, m.away_goals)
    mu_totals = league_mu_totals(to_match_records(train), asof=BOUNDARY,
                                 half_life_days=365.0)

    bets: List[dict] = []
    priced = 0
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
            mat_dc = dc.score_matrix(m["home"], m["away"], max_goals=10,
                                     league=m.get("league"))
            prd = ah_probs(mat_dc, ah["line"])
            denom_d = prd["home"]["win"] + prd["home"]["lose"]
            pdh = prd["home"]["win"] / denom_d if denom_d > 0 else 0.5
            margin = ah["home_score"] - ah["away_score"]
            for model, p_home, side_d, plf in (("pi", ph, "home", "pl_pi"),
                                               ("dc", pdh, None, "pl_dc")):
                side = "home" if p_home > 0.5 else "away"
                o = ah["o_home"] if side == "home" else ah["o_away"]
                line = ah["line"] if side == "home" else -ah["line"]
                mg = margin if side == "home" else -margin
                pl = settle_ah(mg, line, o)
                bets.append({"date": str(m["match_date"])[:10], "match_id": mid,
                             "league": m.get("league"), "model": model,
                             "side": side, "odds": o, "line": ah["line"],
                             "p_pick": p_home if side == "home" else 1.0 - p_home,
                             "pl_per_unit": pl})
            priced += 1
        # pi update AFTER pricing (as-of discipline)
        pi.update(m["home"], m["away"], m["home_goals"], m["away_goals"])
    print(f"[priced] {priced} 25/26 rule-B matches; {len(bets)} bet records (pi+dc)")

    # ---- dimensional sanity on the pi flat journey ----
    bets_pi = sorted([b for b in bets if b["model"] == "pi"],
                     key=lambda b: (b["date"], b["match_id"]))
    bets_dc = sorted([b for b in bets if b["model"] == "dc"],
                     key=lambda b: (b["date"], b["match_id"]))
    j = run_journey(bets_pi, "flat")
    rebuilt = BANKROLL0 + sum(100.0 * b["pl_per_unit"] for b in bets_pi[:j["bets_placed"]])
    assert abs(rebuilt - j["final_bankroll"]) < 0.01, \
        f"[SANITY FAIL] flat pi: rebuilt {rebuilt} != {j['final_bankroll']}"
    print(f"[sanity] flat pi: staked={j['total_staked']:.2f} profit={j['profit']:.2f} "
          f"final={j['final_bankroll']:.2f} OK")

    # ---- portfolios ----
    portfolios = {
        "flat_pi": run_journey(bets_pi, "flat"),
        "kelly_pi": run_journey(bets_pi, "kelly"),
        "pct1_pi": run_journey(bets_pi, "pct1"),
        "flat_dc": run_journey(bets_dc, "flat"),
        "kelly_dc": run_journey(bets_dc, "kelly"),
        "pct1_dc": run_journey(bets_dc, "pct1"),
    }

    # ---- bootstrap (pi flat / kelly / pct1) ----
    pl_pi = np.array([b["pl_per_unit"] for b in bets_pi])
    pp_pi = np.array([b["p_pick"] for b in bets_pi])
    od_pi = np.array([b["odds"] for b in bets_pi])
    n_pi = len(pl_pi)
    boot: Dict[str, dict] = {}
    idx_all = rng.integers(0, n_pi, size=(args.paths, n_pi))
    for staking in ("flat", "kelly", "pct1"):
        finals = np.empty(args.paths)
        for k in range(args.paths):
            if staking == "flat":
                cum = np.cumsum(pl_pi[idx_all[k]] * 100.0)
                cross = np.where(cum <= -(BANKROLL0 - 100.0))[0]
                finals[k] = BANKROLL0 + (cum[cross[0]] if cross.size else cum[-1])
            else:
                r = run_journey(
                    [{"pl_per_unit": pl_pi[idx_all[k]][i],
                      "p_pick": pp_pi[idx_all[k]][i],
                      "odds": od_pi[idx_all[k]][i]} for i in range(n_pi)],
                    staking)
                finals[k] = r["final_bankroll"]
        boot[staking] = bootstrap_stats(finals)

    # ---- depth split within rule B (shallow <=0.5 vs 0.5-1.5) ----
    depth: Dict[str, dict] = {}
    for tag, mask in (("shallow_<=0.5", np.array([abs(b["line"]) <= 0.5 for b in bets_pi])),
                      ("mid_0.5-1.5", np.array([0.5 < abs(b["line"]) <= 1.5 for b in bets_pi]))):
        sub = [b for b, m_ in zip(bets_pi, mask) if m_]
        sub_pl = pl_pi[mask]
        if len(sub) < 20:
            depth[tag] = {"n": len(sub), "note": "too few bets"}
            continue
        finals = np.empty(args.paths)
        for k in range(args.paths):
            sidx = rng.integers(0, len(sub_pl), size=len(sub_pl))
            cum = np.cumsum(sub_pl[sidx] * 100.0)
            finals[k] = BANKROLL0 + cum[-1]
        depth[tag] = {"n": len(sub),
                      "roi_on_staked": round(float(sub_pl.sum()) / len(sub), 5),
                      **bootstrap_stats(finals)}

    # ---- T12c window reference ----
    t12c_ref = {"overall_roi_on_staked": 0.0577, "shallow_roi": 0.0683,
                "mid_roi": 0.0722, "deep_roi": -0.0081}

    report = {
        "meta": {"bankroll0": BANKROLL0, "oos_season": "2025/26",
                 "oos_start": OOS_START, "boundary": str(BOUNDARY),
                 "train_n": len(train), "ah_matches_sampled": len(sample),
                 "rule_b_matches": len(rule_b), "max_line": MAX_LINE,
                 "bootstrap_paths": args.paths, "seed": args.seed,
                 "model": "pre-2023 DC (frozen) + pi walk-forward as-of (no retraining)",
                 "t12c_window_reference": t12c_ref},
        "portfolios": portfolios,
        "bootstrap": boot,
        "depth_split": depth,
    }
    Path(args.out_prefix + ".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# T13 25/26 OUT-OF-SAMPLE VALIDATION (afb-T13)", "",
             f"OOS season 25/26: {len(sample)} matches with AH, rule B "
             f"(|line|<={MAX_LINE}) {len(rule_b)}; boundary {BOUNDARY} (train {len(train)});",
             "model = pre-2023 DC frozen + pi walk-forward as-of (zero retraining)",
             "",
             "## portfolios"]
    for name, r in portfolios.items():
        lines.append(f"## {name}")
        for k, v in r.items():
            lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## bootstrap (1,000 i.i.d. paths, pi)")
    for t, v in boot.items():
        lines.append(f"- {t}: positive {v['positive_paths_pct']}% | median {v['median_final']} "
                     f"| p5 {v['p5']} | p95 {v['p95']}")
    lines.append("")
    lines.append("## depth split (pi, rule B)")
    for t, v in depth.items():
        lines.append(f"- {t}: {v}")
    Path(args.out_prefix + ".md").write_text("\n".join(lines), encoding="utf-8")

    print("[done] wrote", args.out_prefix + ".json/.md")
    for name, r in portfolios.items():
        print(f"  {name}: final={r['final_bankroll']} ROI={r['roi_on_staked']} "
              f"bets={r['bets_placed']} maxDD={r['max_drawdown']}")
    for t, v in depth.items():
        print(f"  depth {t}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
