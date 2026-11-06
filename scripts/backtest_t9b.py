#!/usr/bin/env python3
"""afb-T9b: model re-exam on the T9 CLV sample (rolling_xG features + CLV KPI).

Question: with (a) the full CLV sample (5,431 matches, 99.1% odds coverage vs
T4's 1,908) and (b) rolling-xG features, does any model source beat the
de-vigged closing market? T4 answer was no (market w=0 optimal, ROI<0) on the
small sample without xG.

Design (T4 methodology, upgraded):
- Sample: clv_consensus_closing (5,431 matches, 2023-24 + 2024-25) joined to
  finished matches. Chronological calib/test halves within the sample.
- Train: all finished matches strictly before the sample start (DC frozen at
  boundary; pi-ratings initialised there then walk-forward through the sample
  in date order, as-of per match - zero leakage).
- Features: afb_team_rolling_xg (strictly pre-match per T3d) -> xG-Poisson
  probability source (lambda_h = sqrt(rxf_home * rxa_away), lambda_a symmetric;
  fallback to league mean when n_history < 3).
- Blend grid: dc+xg / pi+xg weights fitted on the CALIBRATION half (RPS),
  evaluated on the TEST half. No leakage.
- KPI: primary = CLV vs de-vigged closing consensus (mean edge p_model/p_close-1,
  bets at 2% EV threshold, flat-stake ROI at fair closing odds); reference =
  RPS / log-loss / hit rate. Market baseline = the consensus closing itself.

Outputs: reports/backtest_t9b_report.json + .md
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402
from config import settings_v2  # noqa: E402
from models.calibration import apply_temperature, fit_temperature_1x2, nll_1x2  # noqa: E402
from models.dc_model import fit_dc  # noqa: E402
from models.metrics import mean_rps_1x2  # noqa: E402
from models.pi_ratings import PiRatingModel, PiParams, league_mu_totals  # noqa: E402
from scripts.backtest_dc import (  # noqa: E402
    load_matches,
    one_x_two_outcome,
    to_match_records,
)

SELECTIONS = ("Home", "Draw", "Away")


def poisson_1x2(lh: float, la: float, max_goals: int = 10) -> Dict[str, float]:
    ph = [math.exp(-lh) * lh**k / math.factorial(k) for k in range(max_goals + 1)]
    pa = [math.exp(-la) * la**k / math.factorial(k) for k in range(max_goals + 1)]
    home = draw = away = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = ph[i] * pa[j]
            if i > j:
                home += p
            elif i == j:
                draw += p
            else:
                away += p
    s = home + draw + away
    return {"Home": home / s, "Draw": draw / s, "Away": away / s}


def blend(p1: Dict[str, float], p2: Dict[str, float], w: float) -> Dict[str, float]:
    out = {sel: w * float(p1[sel]) + (1.0 - w) * float(p2[sel]) for sel in SELECTIONS}
    total = sum(out.values())
    return {sel: v / total for sel, v in out.items()} if total > 0 else out


def evaluate(prob_rows, outcomes) -> dict:
    hits = sum(1 for row, out in zip(prob_rows, outcomes) if max(row, key=row.get) == out)
    return {
        "n": len(outcomes),
        "rps": round(mean_rps_1x2(prob_rows, outcomes), 5) if outcomes else None,
        "logloss": round(nll_1x2(prob_rows, outcomes), 5) if outcomes else None,
        "hit_rate": round(hits / len(outcomes), 4) if outcomes else None,
    }


def clv_kpi(prob_rows, cons_rows, outcomes, ev_threshold: float = 0.02) -> dict:
    """Primary KPI: model vs de-vigged closing consensus.

    Per selection: edge = p_model / p_close - 1. A 'bet' is any selection with
    edge >= threshold, settled at fair closing odds (1/p_close).
    """
    edges_all, bets, stakes, payouts, hits = [], 0, 0.0, 0.0, 0
    for row, cons, out in zip(prob_rows, cons_rows, outcomes):
        match_edges = {}
        for i, sel in enumerate(SELECTIONS):
            pc = float(cons[i])
            if pc <= 0.01:
                continue
            e = float(row[sel]) / pc - 1.0
            edges_all.append(e)
            match_edges[sel] = e
        if not match_edges:
            continue
        best_sel, best_e = max(match_edges.items(), key=lambda kv: kv[1])
        if best_e < ev_threshold:
            continue
        pc = float(cons[SELECTIONS.index(best_sel)])
        bets += 1
        stakes += 1.0
        win = out == best_sel
        hits += 1 if win else 0
        payouts += (1.0 / pc) if win else 0.0
    edges_all.sort()
    n = len(edges_all)
    return {
        "mean_edge_pp": round(100 * sum(edges_all) / n, 3) if n else None,
        "edge_p90_pp": round(100 * edges_all[int(n * 0.9)], 3) if n else None,
        "bets": bets,
        "roi_fair": round((payouts - stakes) / stakes, 4) if stakes else None,
        "bet_hit_rate": round(hits / bets, 4) if bets else None,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="T9b model re-exam on the CLV sample")
    p.add_argument("--half-life", type=float, default=365.0)
    p.add_argument("--min-matches", type=int, default=10)
    p.add_argument("--max-sweeps", type=int, default=30)
    p.add_argument("--tol", type=float, default=1e-4)
    p.add_argument("--max-goals", type=int, default=10)
    p.add_argument("--ev-threshold", type=float, default=0.02)
    p.add_argument("--min-n-history", type=int, default=3)
    p.add_argument("--out-prefix", type=str, default=str(REPO_ROOT / "reports" / "backtest_t9b_report"))
    args = p.parse_args()

    conn = afb_mysql_connect()
    cur = conn.cursor()

    # ---- CLV sample (chronological), with team/league names ----
    cur.execute("""SELECT c.match_id, c.p_home_shin_med, c.p_draw_shin_med, c.p_away_shin_med,
                          m.match_date, th.name, ta.name, m.home_score, m.away_score, comp.name,
                          m.home_team_id, m.away_team_id
        FROM clv_consensus_closing c
        JOIN matches m ON m.match_id = c.match_id
        JOIN teams th ON th.team_id = m.home_team_id
        JOIN teams ta ON ta.team_id = m.away_team_id
        JOIN competitions comp ON comp.competition_id = m.competition_id
        WHERE m.status='finished' AND m.home_score IS NOT NULL
        ORDER BY m.match_date, c.match_id""")
    sample = cur.fetchall()
    if len(sample) < 500:
        print("[FATAL] CLV sample too small")
        return 1
    sample_start = sample[0][4]
    print(f"[sample] {len(sample)} CLV matches, {sample_start} .. {sample[-1][4]}")

    # ---- training history: strictly before the sample start ----
    matches_all = load_matches(conn, min_date=str(settings_v2.afb_history_min_date))
    train = [m for m in matches_all if str(m["match_date"])[:10] < str(sample_start)[:10]]
    print(f"[train] {len(train)} matches before {sample_start}")

    # ---- rolling xG map: (match_id, team_id) -> (rxf, rxa, n_hist) ----
    cur.execute("SELECT match_id, team_id, rolling_xg_for, rolling_xg_against, n_history FROM afb_team_rolling_xg")
    rxg = {(int(r[0]), int(r[1])): (float(r[2]), float(r[3]), int(r[4])) for r in cur.fetchall()}
    print(f"[xg] rolling rows: {len(rxg)}")

    # ---- DC frozen at boundary ----
    boundary = date.fromisoformat(str(sample_start)[:10]) - timedelta(days=1)
    print("[fit] DC frozen at", boundary)
    dc = fit_dc(
        to_match_records(train),
        asof=boundary,
        half_life_days=args.half_life,
        min_matches=args.min_matches,
        max_sweeps=args.max_sweeps,
        tol=args.tol,
    )

    # ---- league mean goals fallback (from train) ----
    gh = [m["home_goals"] for m in train if m.get("home_goals") is not None]
    ga = [m["away_goals"] for m in train if m.get("away_goals") is not None]
    lg_mean = (sum(gh) + sum(ga)) / (len(gh) + len(ga)) / 2.0 if gh else 1.35

    # ---- calib/test split (chronological halves of the sample) ----
    cut = len(sample) // 2
    calib, test = sample[:cut], sample[cut:]
    calib_ids = {r[0] for r in calib}
    print(f"[split] calib={len(calib)} test={len(test)}")

    # ---- walk forward through the WHOLE sample in date order ----
    print("[pi] walk-forward through sample ...")
    pi = PiRatingModel(params=PiParams(kappa=0.05, omega_home=0.6))
    for m in to_match_records(train):
        pi.update(m.home, m.away, m.home_goals, m.away_goals)
    mu_totals = league_mu_totals(to_match_records(train), asof=boundary, half_life_days=args.half_life)

    sources: Dict[str, Dict[str, List]] = {
        s: {"probs": {c: [] for c in ("calib", "test")}, "cons": {c: [] for c in ("calib", "test")},
            "out": {c: [] for c in ("calib", "test")}}
        for s in ("market", "dc", "pi", "xg")
    }
    xg_total = xg_cover = 0
    for row in sample:
        mid, pch, pcx, pca, md, home, away, hsc, asc, league, hid, aid = row
        d = str(md)[:10]
        part = "calib" if mid in calib_ids else "test"
        outcome = one_x_two_outcome(hsc, asc)
        cons = (float(pch), float(pcx), float(pca))
        sources["market"]["probs"][part].append({"Home": cons[0], "Draw": cons[1], "Away": cons[2]})
        sources["market"]["cons"][part].append(cons)
        sources["market"]["out"][part].append(outcome)
        # DC (frozen boundary)
        pdc = dc.probs_1x2(home, away, max_goals=args.max_goals)
        sources["dc"]["probs"][part].append(pdc)
        sources["dc"]["cons"][part].append(cons)
        sources["dc"]["out"][part].append(outcome)
        # pi (as-of; update AFTER collecting probs)
        mu = mu_totals.get(league or "", mu_totals[""])
        ppi = pi.probs_1x2(home, away, mu_total=mu, max_goals=args.max_goals)
        sources["pi"]["probs"][part].append(ppi)
        sources["pi"]["cons"][part].append(cons)
        sources["pi"]["out"][part].append(outcome)
        # xG-Poisson (strictly pre-match rolling values)
        xg_total += 1
        rx_h = rxg.get((int(mid), int(hid)))
        rx_a = rxg.get((int(mid), int(aid)))
        if rx_h and rx_a and rx_h[2] >= args.min_n_history and rx_a[2] >= args.min_n_history:
            xg_cover += 1
            lh = math.sqrt(max(rx_h[0], 0.05) * max(rx_a[1], 0.05))
            la_ = math.sqrt(max(rx_a[0], 0.05) * max(rx_h[1], 0.05))
            pxg = poisson_1x2(lh, la_, args.max_goals)
        else:
            pxg = poisson_1x2(lg_mean, lg_mean, args.max_goals)
        sources["xg"]["probs"][part].append(pxg)
        sources["xg"]["cons"][part].append(cons)
        sources["xg"]["out"][part].append(outcome)
        # update pi AFTER the match (as-of discipline)
        pi.update(home, away, int(hsc), int(asc))
    print(f"[xg] coverage: {xg_cover}/{xg_total} sample matches with n_history>={args.min_n_history}")

    # ---- calibrate temperature on CALIB half per source ----
    temps = {}
    for s in ("dc", "pi", "xg"):
        probs = sources[s]["probs"]["calib"]
        outs = list(sources[s]["out"]["calib"])
        t, _ = fit_temperature_1x2(probs, outs)
        temps[s] = t
        print(f"[temp] {s}={t:.4f}")
        for part in ("calib", "test"):
            sources[s]["probs"][part] = [apply_temperature(r, t) for r in sources[s]["probs"][part]]

    # ---- blend weight grid on CALIB half (RPS), evaluate on TEST half ----
    results = {}
    for s in ("market", "dc", "pi", "xg"):
        pr = sources[s]["probs"]["test"]
        ou = list(sources[s]["out"]["test"])
        co = sources[s]["cons"]["test"]
        results[s] = {"eval": evaluate(pr, ou), "clv": clv_kpi(pr, co, ou, args.ev_threshold)}
    for bname, (s1, s2) in {"dc_xg": ("dc", "xg"), "pi_xg": ("pi", "xg"), "dc_pi": ("dc", "pi")}.items():
        best_w, best_r = 0.5, math.inf
        for w in [i / 10 for i in range(0, 11)]:
            pr = [blend(sources[s1]["probs"]["calib"][i], sources[s2]["probs"]["calib"][i], w)
                  for i in range(len(calib))]
            r = mean_rps_1x2(pr, list(sources[s1]["out"]["calib"]))
            if r < best_r:
                best_r, best_w = r, w
        pr_test = [blend(sources[s1]["probs"]["test"][i], sources[s2]["probs"]["test"][i], best_w)
                   for i in range(len(test))]
        results[bname] = {
            "w": best_w,
            "eval": evaluate(pr_test, list(sources[s1]["out"]["test"])),
            "clv": clv_kpi(pr_test, sources[s1]["cons"]["test"], list(sources[s1]["out"]["test"]),
                           args.ev_threshold),
        }
        print(f"[blend] {bname}: w*={best_w} (calib rps={best_r:.5f})")

    # ---- report ----
    out = {
        "meta": {
            "sample_n": len(sample), "calib_n": len(calib), "test_n": len(test),
            "sample_start": str(sample_start)[:10], "sample_end": str(sample[-1][4])[:10],
            "boundary": str(boundary), "train_n": len(train),
            "xg_coverage": f"{xg_cover}/{xg_total}", "min_n_history": args.min_n_history,
            "ev_threshold": args.ev_threshold, "temps": {k: round(v, 4) for k, v in temps.items()},
        },
        "results": results,
    }
    Path(f"{args.out_prefix}.json").write_text(json.dumps(out, indent=1, default=str))
    lines = ["# T9b MODEL RE-EXAM ON THE CLV SAMPLE (afb-T9b)",
             f"meta: {json.dumps(out['meta'])}", "",
             "market baseline (de-vig closing consensus):",
             f"  market: rps={results['market']['eval']['rps']} ll={results['market']['eval']['logloss']} hit={results['market']['eval']['hit_rate']}", "",
             "sources (test half): rps | ll | hit | mean_edge_pp | bets | roi_fair"]
    for s, r in results.items():
        e, c = r["eval"], r["clv"]
        wtxt = f"|w={r['w']}" if "w" in r else ""
        lines.append(f"  {s}{wtxt}: rps={e['rps']} ll={e['logloss']} hit={e['hit_rate']} edge={c['mean_edge_pp']}pp bets={c['bets']} roi_fair={c['roi_fair']}")
    Path(f"{args.out_prefix}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
