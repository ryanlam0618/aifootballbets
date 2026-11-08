#!/usr/bin/env python3
"""afb-T12: bankroll simulation - "bet the model's pick, ignore ROI/edge".

Question (Kris 2026-11-08): "唔睇 ROI/edge，只根據模型勝率落注（1x2/AH），
最後結果係幾多？本金 10000" - a formal flat-stake bankroll simulation.

Design (zero leakage, same test periods as T9b/T11):
- Sample: the TEST halves of the T9b 1x2 CLV sample (~2,715 matches) and the
  T11 AH sample (~4,204 matches). Model probabilities from the established
  walk-forward pipelines: DC frozen at the boundary (full-sample start - 1
  day); pi-ratings initialised on all finished matches before the boundary,
  then walk-forward through the FULL samples in date order (update AFTER
  pricing each unique match - as-of discipline; pi walks the calib half
  before the test half). RAW model probabilities are used (argmax betting is
  invariant to temperature calibration; for AH the natural rule is raw cover
  prob vs 0.5).
- Betting rule (pure probability, NO edge threshold): 1x2 - bet the outcome
  with the highest model probability; AH - bet the side with the higher model
  cover probability (home if p>0.5 else away). EVERY test-half match gets a
  bet.
- Settlement at PRE-de-vig closing odds (real market quotes):
  1x2 - bookmaker-average raw odds per outcome (afb_odds_snapshots
  run_id='clv_backfill_batch1', market_key='1X2');
  AH - the average-view quotes themselves (run_id='clv_backfill_ah'),
  settled with the T1 quarter-line rules (win +(o-1), push 0, lose -1;
  quarter = half stakes on the adjacent lines).
- Stake: flat 100 (1% of the 10,000 bankroll). Bankroll curve tracked
  chronologically; bankruptcy when bankroll <= 0 or < stake (cannot place),
  recording the bet index. Max drawdown = peak-to-trough on the curve.
- Portfolios: 1x2 alone, AH alone, and COMBINED (both bet streams merged
  chronologically into one bankroll journey). pi is the primary model (best
  in T9b/T11); DC reported as a robustness variant.

afb-T12b builds on this file: build_priced_bets() is importable and shared
with scripts/bankroll_sim_t12b.py (dynamic staking variants).

Zero DB writes. Expected result is negative - reported as-is.

Outputs: reports/bankroll_sim_t12_report.json + .md
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402
from config import settings_v2  # noqa: E402
from models.dc_model import ah_probs, fit_dc  # noqa: E402
from models.pi_ratings import PiParams, PiRatingModel, league_mu_totals  # noqa: E402
from scripts.backtest_dc import load_matches, one_x_two_outcome, to_match_records  # noqa: E402
from scripts.backtest_t11_ah import load_ah_sample, settle_ah  # noqa: E402

BANKROLL0 = 10_000.0
STAKE = 100.0
SEL_1X2 = ("Home", "Draw", "Away")


# ----------------------------------------------------------- bankroll engine

def run_bankroll(bets: List[dict]) -> dict:
    """Chronological flat-stake bankroll journey. bets must be date-sorted."""
    bankroll = BANKROLL0
    curve = [bankroll]
    peak = bankroll
    max_dd = 0.0
    wins = losses = pushes = 0
    total_staked = 0.0
    bankrupt_at = None
    for i, b in enumerate(bets, start=1):
        if bankroll <= 0 or bankroll < STAKE:
            bankrupt_at = i - 1
            break
        pl = b["pl"] * STAKE  # b["pl"] is PER-UNIT; scale by the real stake
        bankroll += pl
        total_staked += STAKE
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
    return {
        "final_bankroll": round(bankroll, 2),
        "bets_placed": len(curve) - 1,
        "total_staked": round(total_staked, 2),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "max_drawdown": round(max_dd, 2),
        "peak_bankroll": round(peak, 2),
        "bankrupt_at_bet": bankrupt_at,
        "bankrupt": bankrupt_at is not None,
        "profit": round(bankroll - BANKROLL0, 2),
    }


# ------------------------------------------------------- priced bet streams

def build_priced_bets(conn, cur, half_life: float = 365.0, min_matches: int = 10,
                      max_sweeps: int = 30, tol: float = 1e-4,
                      max_goals: int = 10) -> Tuple[List[dict], List[dict], dict]:
    """Price the T9b/T11 test-half bet streams (model picks + real-odds P/L).

    Returns (final_1x2, final_ah, meta). Each bet carries: date, match_id,
    league, pick and per-unit P/L for pi (primary) and dc (robustness), plus
    the picked side's model probability and real odds (for staking schemes).
    Zero leakage: DC frozen at the full-sample boundary; pi walks the FULL
    samples in date order (calib before test), update AFTER pricing.
    """
    # ---- 1x2 sample: T9b query and split, exactly ----
    cur.execute("""SELECT c.match_id, c.p_home_shin_med, c.p_draw_shin_med, c.p_away_shin_med,
                          m.match_date, th.name, ta.name, m.home_score, m.away_score, comp.name
        FROM clv_consensus_closing c
        JOIN matches m ON m.match_id = c.match_id
        JOIN teams th ON th.team_id = m.home_team_id
        JOIN teams ta ON ta.team_id = m.away_team_id
        JOIN competitions comp ON comp.competition_id = m.competition_id
        WHERE m.status='finished' AND m.home_score IS NOT NULL
        ORDER BY m.match_date, c.match_id""")
    sample_1x2 = cur.fetchall()
    cut1 = len(sample_1x2) // 2
    test_1x2 = sample_1x2[cut1:]
    print(f"[1x2] sample {len(sample_1x2)}, test half {len(test_1x2)}")

    # ---- AH sample: T11 loader and split, exactly ----
    sample_ah = load_ah_sample(cur)
    cut2 = len(sample_ah) // 2
    test_ah = sample_ah[cut2:]
    print(f"[AH] sample {len(sample_ah)}, test half {len(test_ah)}")

    # afb-T12 boundary follows T9b/T11: freeze at the FULL samples' start so
    # pi walks through the calib half before the test half (as-of); bets are
    # placed only on test-half events.
    starts = [str(sample_1x2[0][4])[:10], str(sample_ah[0]["match_date"])[:10]]
    sample_start = min(starts)
    boundary = date.fromisoformat(sample_start) - timedelta(days=1)
    print(f"[boundary] {boundary} (full-sample start {sample_start})")

    # ---- training history ----
    matches_all = load_matches(conn, min_date=str(settings_v2.afb_history_min_date))
    train = [m for m in matches_all if str(m["match_date"])[:10] < sample_start]
    print(f"[train] {len(train)} matches before {sample_start}")

    # ---- DC frozen at boundary ----
    dc = fit_dc(to_match_records(train), asof=boundary,
                half_life_days=half_life, min_matches=min_matches,
                max_sweeps=max_sweeps, tol=tol)

    # ---- unique events across both markets (FULL samples: pi walks the
    # calib half too; bets placed only on test-half events) ----
    events: Dict[str, dict] = {}
    for part, rows in (("calib", sample_1x2[:cut1]), ("test", test_1x2)):
        for row in rows:
            mid, _, _, _, md, home, away, hsc, asc, league = row
            events[f"1x2:{mid}"] = {"date": str(md)[:10], "match_id": str(mid),
                                    "home": home, "away": away, "hsc": int(hsc),
                                    "asc": int(asc), "league": league,
                                    "market": "1x2", "part": part}
    for part, rows in (("calib", sample_ah[:cut2]), ("test", test_ah)):
        for row in rows:
            events[f"ah:{row['match_id']}"] = {
                "date": str(row["match_date"])[:10], "match_id": str(row["match_id"]),
                "home": row["home"], "away": row["away"], "hsc": row["home_score"],
                "asc": row["away_score"], "league": row["league"],
                "market": "ah", "part": part}
    ordered = sorted(events.values(), key=lambda e: (e["date"], e["match_id"]))
    print(f"[events] unique matches priced (calib+test): {len(ordered)}")

    # ---- pi walk-forward (init on train; update AFTER pricing each unique match) ----
    pi = PiRatingModel(params=PiParams(kappa=0.05, omega_home=0.6))
    for m in to_match_records(train):
        pi.update(m.home, m.away, m.home_goals, m.away_goals)
    mu_totals = league_mu_totals(to_match_records(train), asof=boundary,
                                 half_life_days=half_life)

    rows_1x2_by_id = {str(r[0]): r for r in test_1x2}
    ah_by_id = {str(r["match_id"]): r for r in test_ah}

    # raw bookmaker-average 1x2 odds (pre-de-vig real quotes)
    odds_map: Dict[int, Dict[str, float]] = defaultdict(dict)
    cur.execute("""
        SELECT match_id, selection, AVG(odds) AS o
        FROM afb_odds_snapshots
        WHERE run_id='clv_backfill_batch1' AND market_key='1X2'
        GROUP BY match_id, selection
    """)
    for mid, sel, o in cur.fetchall():
        odds_map[int(mid)][str(sel)] = float(o)

    bets_1x2: List[dict] = []
    bets_ah: List[dict] = []
    skipped_1x2 = 0
    processed: set = set()

    for ev in ordered:
        if ev["market"] == "1x2":
            if ev["part"] != "test":
                pass  # calib event: pi update happens below
            else:
                row = rows_1x2_by_id[ev["match_id"]]
                _, _, _, _, md, home, away, hsc, asc, league = row
                o = odds_map.get(int(ev["match_id"]))
                if not o or not all(k in o for k in ("1", "X", "2")):
                    skipped_1x2 += 1
                else:
                    p_pi = pi.probs_1x2(home, away,
                                        mu_total=mu_totals.get(league or "", mu_totals[""]),
                                        max_goals=max_goals)
                    p_dc = dc.probs_1x2(home, away, max_goals=max_goals)
                    outcome = one_x_two_outcome(hsc, asc)
                    o_real = {"Home": o["1"], "Draw": o["X"], "Away": o["2"]}
                    pick_pi = max(SEL_1X2, key=lambda s: p_pi[s])
                    pick_dc = max(SEL_1X2, key=lambda s: p_dc[s])
                    bets_1x2.append({
                        "date": ev["date"], "match_id": ev["match_id"],
                        "outcome": outcome, "league": league,
                        "pick_pi": pick_pi,
                        "pl_pi": (o_real[pick_pi] - 1.0) if outcome == pick_pi else -1.0,
                        "pick_dc": pick_dc,
                        "pl_dc": (o_real[pick_dc] - 1.0) if outcome == pick_dc else -1.0,
                        "odds_pi": o_real[pick_pi], "odds_dc": o_real[pick_dc],
                        "p_pi_pick": p_pi[pick_pi], "p_dc_pick": p_dc[pick_dc],
                    })
        elif ev["market"] == "ah" and ev["part"] == "test":
            row = ah_by_id[ev["match_id"]]
            mat_pi = pi.score_matrix(ev["home"], ev["away"],
                                     mu_total=mu_totals.get(ev["league"] or "", mu_totals[""]),
                                     max_goals=max_goals)
            pr = ah_probs(mat_pi, row["line"])
            denom = pr["home"]["win"] + pr["home"]["lose"]
            ph = pr["home"]["win"] / denom if denom > 0 else 0.5
            mat_dc = dc.score_matrix(ev["home"], ev["away"], max_goals=max_goals,
                                     league=ev["league"])
            prd = ah_probs(mat_dc, row["line"])
            denom_d = prd["home"]["win"] + prd["home"]["lose"]
            pdh = prd["home"]["win"] / denom_d if denom_d > 0 else 0.5
            margin = row["home_score"] - row["away_score"]
            side = "home" if ph > 0.5 else "away"
            o = row["o_home"] if side == "home" else row["o_away"]
            line = row["line"] if side == "home" else -row["line"]
            mg = margin if side == "home" else -margin
            pl_pi = settle_ah(mg, line, o)
            side_d = "home" if pdh > 0.5 else "away"
            o_d = row["o_home"] if side_d == "home" else row["o_away"]
            line_d = row["line"] if side_d == "home" else -row["line"]
            mg_d = margin if side_d == "home" else -margin
            pl_dc = settle_ah(mg_d, line_d, o_d)
            bets_ah.append({
                "date": ev["date"], "match_id": ev["match_id"],
                "side_pi": side, "pl_pi": pl_pi, "side_dc": side_d, "pl_dc": pl_dc,
                "odds_pi": o, "odds_dc": o_d,
                "p_pi_pick": ph if side == "home" else 1.0 - ph,
                "p_dc_pick": pdh if side_d == "home" else 1.0 - pdh,
                "league": ev["league"],
            })
        # pi update AFTER the event (as-of discipline) - once per unique match
        if ev["match_id"] not in processed:
            pi.update(ev["home"], ev["away"], ev["hsc"], ev["asc"])
            processed.add(ev["match_id"])

    final_1x2 = sorted(bets_1x2, key=lambda b: (b["date"], b["match_id"]))
    final_ah = sorted(bets_ah, key=lambda b: (b["date"], b["match_id"]))
    meta = {"1x2_test_n": len(test_1x2), "1x2_bets": len(final_1x2),
            "1x2_skipped_no_raw_odds": skipped_1x2,
            "ah_test_n": len(test_ah), "ah_bets": len(final_ah),
            "boundary": str(boundary), "train_n": len(train)}
    return final_1x2, final_ah, meta


# --------------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description="T12 bankroll simulation")
    p.add_argument("--stake", type=float, default=100.0)
    p.add_argument("--out-prefix", type=str,
                   default=str(REPO_ROOT / "reports" / "bankroll_sim_t12_report"))
    args = p.parse_args()
    stake = args.stake

    conn = afb_mysql_connect()
    cur = conn.cursor()

    final_1x2, final_ah, meta = build_priced_bets(conn, cur)
    combined = sorted(final_1x2 + final_ah, key=lambda b: (b["date"], b["match_id"]))

    # ---- portfolios (pi primary; dc robustness) ----
    portfolios = {
        "1x2_pi": run_bankroll([{**b, "pl": b["pl_pi"]} for b in final_1x2]),
        "ah_pi": run_bankroll([{**b, "pl": b["pl_pi"]} for b in final_ah]),
        "combined_pi": run_bankroll([{**b, "pl": b["pl_pi"]} for b in combined]),
        "1x2_dc": run_bankroll([{**b, "pl": b["pl_dc"]} for b in final_1x2]),
        "ah_dc": run_bankroll([{**b, "pl": b["pl_dc"]} for b in final_ah]),
        "combined_dc": run_bankroll([{**b, "pl": b["pl_dc"]} for b in combined]),
    }

    report = {
        "meta": {"bankroll0": BANKROLL0, "stake": stake,
                 "sample": "T9b/T11 test halves",
                 **meta,
                 "model": "pi primary (raw probs, argmax/majority-side pick); dc robustness",
                 "settlement": "pre-de-vig closing odds (bookmaker-average 1x2; average-view AH quotes); T1 quarter-line rules"},
        "portfolios": portfolios,
    }
    Path(args.out_prefix + ".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# T12 BANKROLL SIMULATION (afb-T12)", "",
             f"bankroll0={BANKROLL0:.0f} stake={stake:.0f} flat; "
             "model=pi primary (raw probs; pick = highest model probability)",
             f"1x2 test bets {meta['1x2_bets']}/{meta['1x2_test_n']} (skipped, no raw odds: {meta['1x2_skipped_no_raw_odds']}); "
             f"AH test bets {meta['ah_bets']}/{meta['ah_test_n']}; boundary {meta['boundary']}; train {meta['train_n']}",
             ""]
    for name in ("1x2_pi", "ah_pi", "combined_pi", "1x2_dc", "ah_dc", "combined_dc"):
        r = portfolios[name]
        lines.append(f"## {name}")
        for k, v in r.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    Path(args.out_prefix + ".md").write_text("\n".join(lines), encoding="utf-8")

    print("[done] wrote", args.out_prefix + ".json/.md")
    for name in ("1x2_pi", "ah_pi", "combined_pi", "1x2_dc", "ah_dc", "combined_dc"):
        r = portfolios[name]
        print(f"  {name}: final={r['final_bankroll']} bets={r['bets_placed']} "
              f"W/L/P={r['wins']}/{r['losses']}/{r['pushes']} "
              f"maxDD={r['max_drawdown']} bankrupt={r['bankrupt']}"
              + (f" at bet {r['bankrupt_at_bet']}" if r["bankrupt_at_bet"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
