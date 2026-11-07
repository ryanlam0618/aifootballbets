#!/usr/bin/env python3
"""afb-T11: AH (Asian Handicap) backtest - "is AH easier to beat than 1x2?"

Question (Kris 2026-11-07): "AH (兩個 option + 走水) 會唔會易贏過 1x2?" —
answered with data on the T10-AH closing-odds dataset.

Design (T9b methodology carried over, zero leakage):
- Sample: every match with AH FullTime closing odds (afb_odds_snapshots,
  run_id='clv_backfill_ah', preview-only average view). ONE main line per
  match = the line whose two-sided de-vig probabilities are closest to
  balanced (the market's main line).
- Train: all finished matches strictly before the sample start; DC frozen at
  the boundary; pi-ratings initialised there then walk-forward through the
  sample in date order (update AFTER collecting probs - as-of discipline).
- Calibration FIRST (T2 family): binary isotonic (PAVA) on the cover
  probability, fitted on the chronological CALIBRATION half per source,
  applied to the TEST half. Uncalibrated metrics reported alongside.
- Sources: market (proportional 2-way de-vig of the average-view quote),
  dc (DC score matrix -> ah_probs quarter-line pricing), pi (goal_means ->
  score matrix -> ah_probs), dc_pi blend (weight fitted on calib by Brier).
- KPI (primary): CLV - per-side edge = p_model_cover / p_market_cover - 1;
  bet = side with edge >= threshold; flat stake 1 settled with REAL AH
  quarter-line settlement at ACTUAL closing odds (win -> +(o-1), push -> 0,
  lose -> -1; quarter lines = half stake on each adjacent line at the same
  odds). Reference: Brier (cover prob vs settled outcome 1/0.5/0), hit rate.
- Market baseline: the de-vig market cover probability itself.
- Structural analysis: model-vs-market miscalibration by line depth, side
  (home/away), and league. Comparison with T9b 1x2 (market rps 0.19482 vs
  best model pi 0.21236) via the model-minus-market gap on a common subset.

Outputs: reports/backtest_t11_ah_report.json + .md
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
from models.calibration import isotonic_pava, isotonic_predict  # noqa: E402
from models.dc_model import ah_probs, fit_dc  # noqa: E402
from models.pi_ratings import PiParams, PiRatingModel, league_mu_totals  # noqa: E402
from scripts.backtest_dc import load_matches, to_match_records  # noqa: E402

SOURCES = ("market", "dc", "pi", "dc_pi")


# ------------------------------------------------------------ AH settlement

def settle_ah(margin: int, home_line: float, odds: float) -> float:
    """P/L per 1 unit staked on HOME + home_line at decimal `odds`.

    Quarter lines (x.25/x.75) are half stakes on the two adjacent lines at the
    same odds; integer/half lines settle directly. Push returns 0.
    """
    q = round(home_line * 4)
    if q % 2 == 0:  # integer or half line
        d = margin + home_line
        if d > 0:
            return odds - 1.0
        if d == 0:
            return 0.0
        return -1.0
    # quarter line
    if q > 0:
        l1, l2 = (q - 1) / 4.0, (q + 1) / 4.0
    else:
        l1, l2 = (q + 1) / 4.0, (q - 1) / 4.0
    pl = 0.0
    for line in (l1, l2):
        d = margin + line
        if d > 0:
            pl += 0.5 * (odds - 1.0)
        elif d == 0:
            pl += 0.0
        else:
            pl -= 0.5
    return pl


# ------------------------------------------------------- sample construction

def load_ah_sample(cur) -> List[dict]:
    """One row per match: main line (closest to balanced), quotes, names."""
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
        # afb-T11 sanity: |line| > 9.75 exceeds the 11x11 score matrix (max
        # goals 10) and the observed 'AH 100.0' rows (both sides 1.89!) are
        # scrape artifacts - drop them.
        if abs(line) > 9.75:
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
            p_home = (1.0 / oh) / inv  # push-conditional cover prob (proportional de-vig)
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


# ------------------------------------------------------------------- metrics

def brier_ah(probs: List[float], outcomes: List[float]) -> float:
    """Outcome: 1 win, 0.5 push, 0 lose."""
    if not outcomes:
        return None
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / len(outcomes)


def clv_ah(rows: List[dict], probs: List[float], ev_threshold: float) -> dict:
    """Per-match best-side CLV bet, settled with real AH rules at actual odds."""
    edges_all: List[float] = []
    bets = stakes = payouts = 0.0
    n_bets = hits = 0
    for row, p_model in zip(rows, probs):
        cands = []
        for side, o_key, p_mkt_key in (("home", "o_home", "p_mkt_home"),
                                       ("away", "o_away", "p_mkt_away")):
            pc = row[p_mkt_key]
            pm = p_model if side == "home" else 1.0 - p_model
            if pc <= 0.02:
                continue
            cands.append((pm / pc - 1.0, side, pc, row[o_key]))
        if not cands:
            continue
        cands.sort(key=lambda c: -c[0])
        edges_all.append(cands[0][0])
        edge, side, pc, odds = cands[0]
        if edge < ev_threshold:
            continue
        margin = row["home_score"] - row["away_score"]
        line = row["line"]
        if side == "home":
            pl = settle_ah(margin, line, odds)
        else:
            # away bet at HOME line L wins iff margin < L (push iff ==);
            # equivalent home bet: margin' = -margin at line' = -L
            # (both negated - verified per-case: draw on +-0.25 = half win,
            # home-by-1 = full lose, away-by-1 = full win at the away odds).
            pl = settle_ah(-margin, -line, odds)
        n_bets += 1
        stakes += 1.0
        payouts += 1.0 + pl
        hits += 1 if pl > 0 else 0
    edges_all.sort()
    n = len(edges_all)
    return {
        "mean_edge_pp": round(100 * sum(edges_all) / n, 3) if n else None,
        "bets": n_bets,
        "roi_actual_odds": round((payouts - stakes) / stakes, 4) if stakes else None,
        "bet_hit_rate": round(hits / n_bets, 4) if n_bets else None,
    }


def isotonic_fit_predict(probs: List[float], outcomes: List[float]
                         ) -> Tuple[List[float], List[Tuple[float, float]]]:
    bp = isotonic_pava(list(zip(probs, outcomes)))
    return [isotonic_predict(bp, p) for p in probs], bp


# --------------------------------------------------------------------- main

def main() -> int:
    p = argparse.ArgumentParser(description="T11 AH backtest")
    p.add_argument("--half-life", type=float, default=365.0)
    p.add_argument("--min-matches", type=int, default=10)
    p.add_argument("--max-sweeps", type=int, default=30)
    p.add_argument("--tol", type=float, default=1e-4)
    p.add_argument("--max-goals", type=int, default=10)
    p.add_argument("--ev-threshold", type=float, default=0.02)
    p.add_argument("--out-prefix", type=str,
                   default=str(REPO_ROOT / "reports" / "backtest_t11_ah_report"))
    args = p.parse_args()

    conn = afb_mysql_connect()
    cur = conn.cursor()

    # ---- AH sample ----
    sample = load_ah_sample(cur)
    if len(sample) < 500:
        print("[FATAL] AH sample too small")
        return 1
    sample_start = str(sample[0]["match_date"])[:10]
    sample_end = str(sample[-1]["match_date"])[:10]
    print(f"[sample] {len(sample)} matches with AH, {sample_start} .. {sample_end}")

    # ---- training history ----
    matches_all = load_matches(conn, min_date=str(settings_v2.afb_history_min_date))
    train = [m for m in matches_all if str(m["match_date"])[:10] < sample_start]
    print(f"[train] {len(train)} matches before {sample_start}")

    # ---- DC frozen at boundary ----
    boundary = date.fromisoformat(sample_start) - timedelta(days=1)
    print("[fit] DC frozen at", boundary)
    dc = fit_dc(to_match_records(train), asof=boundary,
                half_life_days=args.half_life, min_matches=args.min_matches,
                max_sweeps=args.max_sweeps, tol=args.tol)

    # ---- calib/test split ----
    cut = len(sample) // 2
    calib_ids = {r["match_id"] for r in sample[:cut]}
    print(f"[split] calib={cut} test={len(sample) - cut}")

    # ---- pi walk-forward ----
    print("[pi] walk-forward through sample ...")
    pi = PiRatingModel(params=PiParams(kappa=0.05, omega_home=0.6))
    for m in to_match_records(train):
        pi.update(m.home, m.away, m.home_goals, m.away_goals)
    mu_totals = league_mu_totals(to_match_records(train), asof=boundary,
                                 half_life_days=args.half_life)

    data: Dict[str, Dict[str, list]] = {
        s: {"rows": {c: [] for c in ("calib", "test")},
            "p_raw": {c: [] for c in ("calib", "test")},
            "out": {c: [] for c in ("calib", "test")}}
        for s in SOURCES
    }
    for row in sample:
        part = "calib" if row["match_id"] in calib_ids else "test"
        inv = 1.0 / row["o_home"] + 1.0 / row["o_away"]
        p_mkt_home = (1.0 / row["o_home"]) / inv
        row["p_mkt_home"] = p_mkt_home
        row["p_mkt_away"] = 1.0 - p_mkt_home
        margin = row["home_score"] - row["away_score"]
        # settled outcome from the HOME side perspective: 1 win, 0.5 push, 0 lose
        q = round(row["line"] * 4)
        if q % 2 == 0:
            d = margin + row["line"]
            outcome = 1.0 if d > 0 else (0.5 if d == 0 else 0.0)
        else:
            l1, l2 = ((row["line"] * 4 - 1) / 4.0, (row["line"] * 4 + 1) / 4.0) \
                if q > 0 else ((row["line"] * 4 + 1) / 4.0, (row["line"] * 4 - 1) / 4.0)
            o1 = margin + l1
            o2 = margin + l2
            outcome = 0.5 * (1.0 if o1 > 0 else (0.5 if o1 == 0 else 0.0)) \
                + 0.5 * (1.0 if o2 > 0 else (0.5 if o2 == 0 else 0.0))
        row["outcome_home"] = outcome

        # DC (frozen boundary) - main league of the match drives per-league HA
        mat_dc = dc.score_matrix(row["home"], row["away"], max_goals=args.max_goals,
                                 league=row["league"])
        pr = ah_probs(mat_dc, row["line"])
        p_dc = pr["home"]["win"] / (pr["home"]["win"] + pr["home"]["lose"]) \
            if (pr["home"]["win"] + pr["home"]["lose"]) > 0 else 0.5

        # pi (as-of; update AFTER)
        mu = mu_totals.get(row["league"] or "", mu_totals[""])
        mat_pi = pi.score_matrix(row["home"], row["away"], mu_total=mu,
                                 max_goals=args.max_goals)
        prp = ah_probs(mat_pi, row["line"])
        p_pi = prp["home"]["win"] / (prp["home"]["win"] + prp["home"]["lose"]) \
            if (prp["home"]["win"] + prp["home"]["lose"]) > 0 else 0.5

        for s, pv in (("market", p_mkt_home), ("dc", p_dc), ("pi", p_pi)):
            data[s]["rows"][part].append(row)
            data[s]["p_raw"][part].append(pv)
            data[s]["out"][part].append(outcome)
        # update pi AFTER the match (as-of discipline)
        pi.update(row["home"], row["away"], row["home_score"], row["away_score"])

    # ---- dc_pi blend weight fitted on calib (Brier) ----
    best_w, best_b = 0.5, None
    for w in [i / 10 for i in range(0, 11)]:
        pb = [w * a + (1 - w) * b for a, b in zip(data["dc"]["p_raw"]["calib"],
                                                  data["pi"]["p_raw"]["calib"])]
        b = brier_ah(pb, data["market"]["out"]["calib"])
        if best_b is None or b < best_b:
            best_w, best_b = w, b
    print(f"[blend] dc_pi w*={best_w} (calib Brier {round(best_b, 5)})")
    for part in ("calib", "test"):
        pb = [best_w * a + (1 - best_w) * b for a, b in zip(
            data["dc"]["p_raw"][part], data["pi"]["p_raw"][part])]
        data["dc_pi"]["rows"][part] = data["dc"]["rows"][part]
        data["dc_pi"]["p_raw"][part] = pb
        data["dc_pi"]["out"][part] = data["dc"]["out"][part]

    # ---- calibration (binary isotonic per source, fitted on calib) ----
    results = {}
    for s in SOURCES:
        results[s] = {}
        cal_probs = data[s]["p_raw"]["calib"]
        cal_out = data[s]["out"]["calib"]
        bp = isotonic_pava(list(zip(cal_probs, cal_out)))
        for part in ("calib", "test"):
            raw = data[s]["p_raw"][part]
            rows = data[s]["rows"][part]
            out = data[s]["out"][part]
            cal = [isotonic_predict(bp, v) for v in raw]
            for tag, pp in (("raw", raw), ("cal", cal)):
                results[s][f"{part}_{tag}"] = {
                    "n": len(out),
                    "brier": round(brier_ah(pp, out), 5) if out else None,
                    "mean_prob": round(sum(pp) / len(pp), 4) if pp else None,
                }
            if part == "test":
                results[s]["test_clv_raw"] = clv_ah(rows, raw, args.ev_threshold)
                results[s]["test_clv_cal"] = clv_ah(rows, cal, args.ev_threshold)

    # ---- structural analysis (test half, calibrated model probs vs market) ----
    def struct_bucket(keyfn) -> Dict[str, dict]:
        agg = defaultdict(lambda: {"n": 0, "mkt_b": 0.0, "dc_b": 0.0, "pi_b": 0.0})
        # recompute calibrated probs per source for the test half
        cal_store = {}
        for s in SOURCES:
            bp = isotonic_pava(list(zip(data[s]["p_raw"]["calib"], data[s]["out"]["calib"])))
            cal_store[s] = [isotonic_predict(bp, v) for v in data[s]["p_raw"]["test"]]
        for i, row in enumerate(data["market"]["rows"]["test"]):
            k = keyfn(row)
            o = data["market"]["out"]["test"][i]
            a = agg[k]
            a["n"] += 1
            a["mkt_b"] += (data["market"]["p_raw"]["test"][i] - o) ** 2
            a["dc_b"] += (cal_store["dc"][i] - o) ** 2
            a["pi_b"] += (cal_store["pi"][i] - o) ** 2
        return {k: {"n": v["n"],
                    "market_brier": round(v["mkt_b"] / v["n"], 5),
                    "dc_minus_market": round((v["dc_b"] - v["mkt_b"]) / v["n"], 5),
                    "pi_minus_market": round((v["pi_b"] - v["mkt_b"]) / v["n"], 5)}
                for k, v in sorted(agg.items())}

    by_depth = struct_bucket(lambda r: (
        "0" if abs(r["line"]) < 0.3 else
        "0.3-0.75" if abs(r["line"]) <= 0.75 else
        "1.0-1.75" if abs(r["line"]) <= 1.75 else ">=2.0"))
    by_side = struct_bucket(lambda r: "home_side" if r["p_mkt_home"] >= 0.5 else "away_side")
    by_league = struct_bucket(lambda r: r["league"])

    # ---- 1x2 common-subset comparison (T9b join) ----
    cur.execute("SELECT match_id FROM clv_consensus_closing")
    # afb_odds_snapshots.match_id is VARCHAR; clv ids come back as int - cast
    # both sides to int for the intersection (first run found 0 overlap).
    clv_ids = {int(r[0]) for r in cur.fetchall()}
    common = [r for r in data["market"]["rows"]["test"] if int(r["match_id"]) in clv_ids]
    n_common = len(common)

    # ---- assemble report ----
    meta = {
        "sample_n": len(sample),
        "sample_start": sample_start,
        "sample_end": sample_end,
        "boundary": str(boundary),
        "train_n": len(train),
        "calib_n": cut,
        "test_n": len(sample) - cut,
        "blend_w_dc": best_w,
        "ev_threshold": args.ev_threshold,
        "common_1x2_subset_test_n": n_common,
        "t9b_1x2_reference": {"market_rps": 0.19482, "best_model_rps": 0.21236,
                              "best_model": "pi"},
    }
    report = {"meta": meta, "sources": results,
              "structural": {"by_line_depth": by_depth, "by_side": by_side,
                             "by_league": by_league}}
    Path(args.out_prefix + ".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# T11 AH BACKTEST (afb-T11)", "",
             f"sample: {meta['sample_n']} matches ({sample_start} .. {sample_end}), "
             f"calib {meta['calib_n']} / test {meta['test_n']}, "
             f"DC boundary {meta['boundary']}, train {meta['train_n']}",
             f"main line per match (closest to balanced); dc_pi blend w*={best_w}",
             f"common subset with 1x2 CLV sample (test half): {n_common} matches",
             ""]
    for s in SOURCES:
        r = results[s]
        lines.append(f"## {s}")
        for part in ("test",):
            for tag in ("raw", "cal"):
                d = r[f"{part}_{tag}"]
                lines.append(f"- {part}/{tag}: brier={d['brier']} (n={d['n']})")
        for tag in ("raw", "cal"):
            c = r[f"test_clv_{tag}"]
            lines.append(f"- CLV {tag}: mean_edge={c['mean_edge_pp']}pp bets={c['bets']} "
                         f"roi_actual={c['roi_actual_odds']} hit={c['bet_hit_rate']}")
        lines.append("")
    lines.append("## structural (calibrated model Brier minus market Brier, test half)")
    lines.append("### by line depth")
    for k, v in by_depth.items():
        lines.append(f"- {k}: n={v['n']} market={v['market_brier']} dc-mkt={v['dc_minus_market']} pi-mkt={v['pi_minus_market']}")
    lines.append("### by side")
    for k, v in by_side.items():
        lines.append(f"- {k}: n={v['n']} market={v['market_brier']} dc-mkt={v['dc_minus_market']} pi-mkt={v['pi_minus_market']}")
    lines.append("### by league")
    for k, v in by_league.items():
        lines.append(f"- {k}: n={v['n']} market={v['market_brier']} dc-mkt={v['dc_minus_market']} pi-mkt={v['pi_minus_market']}")
    Path(args.out_prefix + ".md").write_text("\n".join(lines), encoding="utf-8")

    print("[done] wrote", args.out_prefix + ".json/.md")
    for s in SOURCES:
        r = results[s]
        print(f"  {s}: test brier raw={r['test_raw']['brier']} cal={r['test_cal']['brier']} "
              f"clv(raw)={r['test_clv_raw']['roi_actual_odds']} "
              f"clv(cal)={r['test_clv_cal']['roi_actual_odds']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
