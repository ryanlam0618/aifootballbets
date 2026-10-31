#!/usr/bin/env python3
"""Layer-2 afb-T4: market blend — model probabilities vs de-vig market.

Question answered: does any blend weight w (p_blend = w*p_model + (1-w)*p_market)
beat the de-vigged market baseline (w=0)?

Probability sources: DC (T1 holdout fit) and Pi-Ratings (T2 tuned params,
sequential walk-forward). Both temperature-calibrated on the calibration
half of the validation window (as-of, zero leakage), evaluated on the
T1 market-odds subset (3,818 test-period matches).

Metrics per weight: RPS / log-loss / hit rate + flat-stake ROI simulation
(bet selections with p_blend * odds > 1 + threshold vs market average odds).

Also delivers the closing-odds accumulation SPEC (for afb-T10 CLV).

Outputs: reports/backtest_blend_report.json + .md
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402
from config import settings_v2  # noqa: E402
from models.calibration import (  # noqa: E402
    apply_temperature,
    fit_temperature_1x2,
    nll_1x2,
)
from models.dc_model import MatchRecord, fit_dc  # noqa: E402
from models.metrics import mean_brier_1x2, mean_rps_1x2  # noqa: E402
from models.pi_ratings import PiRatingModel, PiParams, league_mu_totals  # noqa: E402
from scripts.backtest_dc import (  # noqa: E402
    calibration_buckets,
    load_matches,
    one_x_two_outcome,
    time_split,
    to_match_records,
)
from scripts.backtest_t2 import collect_market_odds  # noqa: E402
from paper.pricing import devig_1x2  # noqa: E402

SELECTIONS = ("Home", "Draw", "Away")


def blend(p_model: Dict[str, float], p_market: Dict[str, float], w: float) -> Dict[str, float]:
    out = {sel: w * float(p_model[sel]) + (1.0 - w) * float(p_market[sel]) for sel in SELECTIONS}
    total = sum(out.values())
    return {sel: v / total for sel, v in out.items()} if total > 0 else out


def evaluate(prob_rows: List[Dict[str, float]], outcomes: List[str]) -> dict:
    pairs = [
        (row[sel], 1 if out == sel else 0)
        for row, out in zip(prob_rows, outcomes)
        for sel in SELECTIONS
    ]
    hits = sum(1 for row, out in zip(prob_rows, outcomes) if max(row, key=row.get) == out)
    return {
        "n": len(outcomes),
        "rps": round(mean_rps_1x2(prob_rows, outcomes), 5) if outcomes else None,
        "logloss": round(nll_1x2(prob_rows, outcomes), 5) if outcomes else None,
        "brier": round(mean_brier_1x2(prob_rows, outcomes), 5) if outcomes else None,
        "hit_rate": round(hits / len(outcomes), 4) if outcomes else None,
        "calibration": calibration_buckets(pairs),
    }


def roi_sim(
    prob_rows: List[Dict[str, float]],
    market_odds: List[Dict[str, float]],
    outcomes: List[str],
    ev_threshold: float = 0.02,
) -> dict:
    """Flat-stake 1-unit bets on selections with p_blend * odds - 1 >= threshold."""
    stakes = payouts = 0.0
    bets = hits = 0
    for row, odds, out in zip(prob_rows, market_odds, outcomes):
        best_sel, best_ev = None, -math.inf
        for sel in SELECTIONS:
            ev = float(row[sel]) * float(odds[sel]) - 1.0
            if ev > best_ev:
                best_sel, best_ev = sel, ev
        if best_sel is None or best_ev < ev_threshold:
            continue
        stakes += 1.0
        bets += 1
        win = out == best_sel
        hits += 1 if win else 0
        payouts += float(odds[best_sel]) if win else 0.0
    return {
        "bets": bets,
        "roi": round((payouts - stakes) / stakes, 4) if stakes else None,
        "hit_rate": round(hits / bets, 4) if bets else None,
    }


def closing_odds_spec() -> dict:
    """Design spec for closing-odds accumulation (prerequisite for afb-T10 CLV)."""
    return {
        "goal": "capture odds at multiple pre-kickoff timestamps per match so CLV "
        "(bet odds vs closing odds) becomes measurable for afb-T10",
        "mechanism": {
            "collector": "extend scripts/run_dc_predictions.py schedule: cron every 6h "
            "until kickoff (T-72h/T-48h/T-24h/T-6h/T-1h) plus one post-kickoff sample as closing proxy",
            "storage": "afb_odds_snapshots (Layer-1, already live) — one row per "
            "(match_id, market_key, selection, bookmaker, captured_at_utc)",
            "closing_definition": "latest snapshot with captured_at_utc <= kickoff - 60min; "
            "fallback to kickoff - 30min if no sample in window",
            "coverage_requirement": "afb-T10 needs >= 30 settled bets with closing odds on BOTH "
            "the bet market and the reference bookmaker",
        },
        "idempotency": "unique key (match_id, market_key, selection, bookmaker, captured_at_utc) "
        "already exists; re-runs are INSERT IGNORE",
        "retention": "none needed (small rows); aggregation via SQL on captured_at_utc",
        "effort": "spec only in this task; implementation lands with afb-T5 pipeline cron",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="T4 market blend backtest")
    p.add_argument("--train-frac", type=float, default=0.7)
    p.add_argument("--half-life", type=float, default=365.0)
    p.add_argument("--min-matches", type=int, default=10)
    p.add_argument("--max-sweeps", type=int, default=30)
    p.add_argument("--tol", type=float, default=1e-4)
    p.add_argument("--max-goals", type=int, default=10)
    p.add_argument("--out-prefix", type=str, default="reports/backtest_blend_report")
    args = p.parse_args()

    conn = afb_mysql_connect()
    matches = load_matches(conn, min_date=str(settings_v2.afb_history_min_date))
    print(f"[load] {len(matches)} finished matches")

    boundary, train, val = time_split(matches, args.train_frac)
    val_sorted = sorted(val, key=lambda m: m["match_date"])
    print(f"[split] boundary={boundary} train={len(train)} val={len(val_sorted)}")

    # ---- DC base model ----
    print("[fit] DC base ...")
    dc = fit_dc(
        to_match_records(train),
        asof=boundary,
        half_life_days=args.half_life,
        min_matches=args.min_matches,
        max_sweeps=args.max_sweeps,
        tol=args.tol,
    )

    # ---- market odds subset (odds coverage is sparse: 2015-16 era + 2024-12+) ----
    market_odds_all = collect_market_odds(conn, val_sorted)
    odds_matches = [m for m in val_sorted if str(m.get("match_id") or "") in market_odds_all]
    print(f"[market] val matches with odds: {len(odds_matches)}")
    if len(odds_matches) < 200:
        print("[WARN] too few odds matches; aborting")
        return 1
    # calib/test split WITHIN the odds subset (first half -> calibrators,
    # second half -> evaluation). Zero leakage: first half precedes second.
    cut = len(odds_matches) // 2
    calib_with = odds_matches[:cut]
    test_with = odds_matches[cut:]
    print(f"[market] calib-with={len(calib_with)} test-with={len(test_with)}")

    # ---- DC probs (frozen boundary model; as-of for both halves) ----
    dc_calib_probs = [dc.probs_1x2(m["home"], m["away"], max_goals=args.max_goals) for m in calib_with]
    dc_test_probs = [dc.probs_1x2(m["home"], m["away"], max_goals=args.max_goals) for m in test_with]
    dc_temp, _ = fit_temperature_1x2(
        dc_calib_probs, [one_x_two_outcome(m["home_goals"], m["away_goals"]) for m in calib_with]
    )
    dc_test_cal = [apply_temperature(r, dc_temp) for r in dc_test_probs]
    print(f"[dc] temperature={dc_temp:.4f}")

    # ---- PI probs (sequential walk through the WHOLE val in date order;
    #      subset probs collected as encountered — as-of per match) ----
    print("[pi] walk-forward ...")
    pi = PiRatingModel(params=PiParams(kappa=0.05, omega_home=0.6))
    train_records = to_match_records(train)
    for m in train_records:
        pi.update(m.home, m.away, m.home_goals, m.away_goals)
    mu_totals = league_mu_totals(train_records, asof=boundary, half_life_days=args.half_life)

    sub_ids = set()
    pi_probs_by_id: Dict[str, Dict[str, float]] = {}
    for m in val_sorted:
        mid = str(m.get("match_id") or "")
        mu = mu_totals.get(m.get("league") or "", mu_totals[""])
        if mid in market_odds_all:
            pi_probs_by_id[mid] = pi.probs_1x2(m["home"], m["away"], mu_total=mu, max_goals=args.max_goals)
            sub_ids.add(mid)
        pi.update(m["home"], m["away"], m["home_goals"], m["away_goals"])
    pi_calib_probs = [pi_probs_by_id[str(m["match_id"])] for m in calib_with]
    pi_test_probs = [pi_probs_by_id[str(m["match_id"])] for m in test_with]
    pi_temp, _ = fit_temperature_1x2(
        pi_calib_probs, [one_x_two_outcome(m["home_goals"], m["away_goals"]) for m in calib_with]
    )
    pi_test_cal = [apply_temperature(r, pi_temp) for r in pi_test_probs]
    print(f"[pi] temperature={pi_temp:.4f}")

    # ---- market de-vig probs + outcomes ----
    market_probs: List[Dict[str, float]] = []
    market_dec: List[Dict[str, float]] = []
    outcomes: List[str] = []
    subset_matches: List[dict] = []
    for m in test_with:
        odds = market_odds_all[str(m["match_id"])]
        try:
            ph, pd_, pa = devig_1x2(odds["Home"], odds["Draw"], odds["Away"])
        except Exception:
            continue
        if not all(math.isfinite(v) for v in (ph, pd_, pa)):
            continue
        market_probs.append({"Home": ph, "Draw": pd_, "Away": pa})
        market_dec.append(odds)
        outcomes.append(one_x_two_outcome(m["home_goals"], m["away_goals"]))
        subset_matches.append(m)
    print(f"[market] de-vig usable subset: {len(market_probs)}")

    # align model prob lists to the same subset
    sub_ids = {m["match_id"] for m in subset_matches}
    dc_test_cal_aligned = [p for p, m in zip(dc_test_cal, test_with) if str(m.get("match_id") or "") in sub_ids]
    dc_test_raw_aligned = [p for p, m in zip(dc_test_probs, test_with) if str(m.get("match_id") or "") in sub_ids]
    pi_test_cal_aligned = [p for p, m in zip(pi_test_cal, test_with) if str(m.get("match_id") or "") in sub_ids]
    pi_test_raw_aligned = [p for p, m in zip(pi_test_probs, test_with) if str(m.get("match_id") or "") in sub_ids]

    # ---- blend grid ----
    weights = [round(0.1 * i, 2) for i in range(11)]  # 0.0 .. 1.0
    sources = {
        "dc_temp": dc_test_cal_aligned,
        "dc_raw": dc_test_raw_aligned,
        "pi_temp": pi_test_cal_aligned,
        "pi_raw": pi_test_raw_aligned,
    }
    grid: Dict[str, dict] = {}
    for src_name, probs in sources.items():
        for w in weights:
            rows = [blend(pm, mk, w) for pm, mk in zip(probs, market_probs)]
            ev_rows = [
                (row, dec, out)
                for row, dec, out in zip(rows, market_dec, outcomes)
            ]
            sims = roi_sim([r for r, _, _ in ev_rows], [d for _, d, _ in ev_rows], [o for _, _, o in ev_rows])
            grid[f"{src_name}|w={w:g}"] = {
                "w_model": w,
                "w_market": round(1 - w, 2),
                **evaluate(rows, outcomes),
                "roi_sim": sims,
            }

    # market baseline (w=0 equivalent)
    market_baseline = evaluate(market_probs, outcomes)

    # best blend per source by RPS
    best = {}
    for src_name in sources:
        cands = [(v["rps"], k) for k, v in grid.items() if k.startswith(src_name + "|") and v["rps"] is not None]
        cands.sort()
        best[src_name] = {"key": cands[0][1], "rps": cands[0][0], "rel_vs_market": round((market_baseline["rps"] - cands[0][0]) / market_baseline["rps"], 5)}

    report = {
        "meta": {
            "boundary": boundary.isoformat(),
            "subset_n": len(market_probs),
            "calib_half_n": len(calib_with),
            "dc_temp": round(dc_temp, 4),
            "pi_temp": round(pi_temp, 4),
            "ev_threshold": 0.02,
            "note": "calibrators fitted on the first half of the odds subset, evaluated on the second half",
        },
        "market_baseline": market_baseline,
        "best_blend_per_source": best,
        "grid": grid,
        "closing_odds_spec": closing_odds_spec(),
    }

    out_json = Path(REPO_ROOT) / (args.out_prefix + ".json")
    out_md = Path(REPO_ROOT) / (args.out_prefix + ".md")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    lines = [
        "# MARKET BLEND BACKTEST (afb-T4)",
        f"meta: {json.dumps(report['meta'], ensure_ascii=False)}",
        f"market baseline: rps={market_baseline['rps']} ll={market_baseline['logloss']} hit={market_baseline['hit_rate']}",
        "",
        "best blend per source (by RPS):",
    ]
    for src, b in best.items():
        g = grid[b["key"]]
        lines.append(
            f"  {src}: {b['key']} rps={b['rps']} rel_vs_market={b['rel_vs_market']:+.5f} "
            f"ll={g['logloss']} hit={g['hit_rate']} roi={g['roi_sim']['roi']} bets={g['roi_sim']['bets']}"
        )
    lines.append("")
    lines.append("full grid (rps | roi):")
    for k in sorted(grid.keys()):
        g = grid[k]
        lines.append(f"  {k}: rps={g['rps']} ll={g['logloss']} roi={g['roi_sim']['roi']} bets={g['roi_sim']['bets']}")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] wrote {out_json}")
    print(f"[done] wrote {out_md}")
    for src, b in best.items():
        print(f"[BEST] {src}: {b['key']} rps={b['rps']} rel_vs_market={b['rel_vs_market']:+.5f}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
