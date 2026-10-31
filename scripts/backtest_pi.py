#!/usr/bin/env python3
"""Layer-2 afb-T2: Pi-Ratings walk-forward backtest vs DC baseline.

Walk-forward by construction: pi-ratings evolve sequentially; every match is
predicted with the ratings as they stand BEFORE it (zero leakage).

Pipeline:
1. Load finished matches (with league), chronological 70/30 split.
2. Tune (kappa, omega_home) on the TRAIN sequence by supremacy MAE
   (cheap proxy — no matrix builds; documented).
3. Warm-up: walk the train sequence with tuned params -> ratings at val start.
4. Walk the validation sequence: predict each match (Poisson from supremacy),
   collect probabilities, then update ratings with the result.
5. Temperature calibration on the first half of the validation predictions,
   applied to the second half (as-of, same discipline as T2 ①).
6. Compare vs the DC baseline (same holdout fit as T1): RPS (acceptance
   metric, relative improvement >= 1%), log-loss, hit rate; per-league.

Outputs: reports/backtest_pi_report.json + .md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
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
from models.pi_ratings import (  # noqa: E402
    PiRatingModel,
    league_mu_totals,
    tune_pi_params,
)
from scripts.backtest_dc import (  # noqa: E402
    calibration_buckets,
    load_matches,
    one_x_two_outcome,
    time_split,
    to_match_records,
)


def outcomes_of(matches: List[dict]) -> List[str]:
    return [one_x_two_outcome(m["home_goals"], m["away_goals"]) for m in matches]


def main() -> int:
    p = argparse.ArgumentParser(description="Pi-Ratings walk-forward backtest vs DC baseline")
    p.add_argument("--train-frac", type=float, default=0.7)
    p.add_argument("--half-life", type=float, default=365.0)
    p.add_argument("--min-matches", type=int, default=10)
    p.add_argument("--max-sweeps", type=int, default=30)
    p.add_argument("--tol", type=float, default=1e-4)
    p.add_argument("--max-goals", type=int, default=10)
    p.add_argument("--out-prefix", type=str, default="reports/backtest_pi_report")
    args = p.parse_args()

    conn = afb_mysql_connect()
    matches = load_matches(conn, min_date=str(settings_v2.afb_history_min_date))
    print(f"[load] {len(matches)} finished matches")

    boundary, train, val = time_split(matches, args.train_frac)
    print(f"[split] boundary={boundary} train={len(train)} val={len(val)}")

    # ---- 1) tune pi params on train sequence (supremacy MAE proxy) ----
    train_records = to_match_records(train)
    params, tune_report = tune_pi_params(train_records)
    print(f"[tune] best params: kappa={params.kappa:g} omega={params.omega_home:g} "
          f"mae={tune_report['best_mae']:.4f}")

    # ---- 2) DC baseline (same holdout fit as T1) ----
    print("[fit] DC baseline ...")
    dc = fit_dc(
        train_records,
        asof=boundary,
        half_life_days=args.half_life,
        min_matches=args.min_matches,
        max_sweeps=args.max_sweeps,
        tol=args.tol,
    )
    print(f"[fit] DC done: rho={dc.rho:+.3f} home_adv={dc.home_adv:+.4f}")

    # ---- 3) league mu_totals as-of val start ----
    mu_totals = league_mu_totals(train_records, asof=boundary, half_life_days=args.half_life)
    print(f"[mu] global mu_total={mu_totals['']:.3f} ({len(mu_totals) - 1} leagues)")

    # ---- 4) walk-forward through validation with pi-ratings ----
    pi = PiRatingModel(params=params)
    # warm-up: ratings through the whole train sequence
    for m in train_records:
        pi.update(m.home, m.away, m.home_goals, m.away_goals)
    print(f"[warmup] ratings through train: {pi.n_matches} matches, {len(pi.home_r)} teams")

    pi_probs_val: List[Dict[str, float]] = []
    for m in val:
        lg = m.get("league") or ""
        mu = mu_totals.get(lg, mu_totals[""])
        pi_probs_val.append(pi.probs_1x2(m["home"], m["away"], mu_total=mu, max_goals=args.max_goals))
        pi.update(m["home"], m["away"], m["home_goals"], m["away_goals"])  # update AFTER predicting
    print(f"[walk] validation walked: {len(pi_probs_val)} predictions (sequential, zero leakage)")

    dc_probs_val = [
        dc.probs_1x2(m["home"], m["away"], max_goals=args.max_goals)
        for m in val
    ]
    outcomes = outcomes_of(val)

    # ---- 5) temperature calibration (first half of val -> second half) ----
    cut = len(val) // 2
    calib_probs, calib_out = pi_probs_val[:cut], outcomes[:cut]
    test_probs, test_out = pi_probs_val[cut:], outcomes[cut:]
    temp, temp_ll = fit_temperature_1x2(calib_probs, calib_out)
    pi_probs_cal = [apply_temperature(r, temp) for r in test_probs]
    print(f"[calib] temperature={temp:.4f} (calib ll {temp_ll:.4f})")

    dc_calib_probs = dc_probs_val[:cut]
    dc_temp, dc_temp_ll = fit_temperature_1x2(dc_calib_probs, calib_out)
    dc_probs_cal = [apply_temperature(r, dc_temp) for r in dc_probs_val[cut:]]

    # ---- 6) metrics ----
    def metrics(probs: List[Dict[str, float]], outs: List[str]) -> dict:
        pairs = [(row[sel], 1 if out == sel else 0) for row, out in zip(probs, outs) for sel in ("Home", "Draw", "Away")]
        hits = sum(1 for row, out in zip(probs, outs) if max(row, key=row.get) == out)
        return {
            "n": len(outs),
            "rps": round(mean_rps_1x2(probs, outs), 5),
            "logloss": round(nll_1x2(probs, outs), 5),
            "brier": round(mean_brier_1x2(probs, outs), 5),
            "hit_rate": round(hits / len(outs), 4) if outs else None,
            "calibration": calibration_buckets(pairs),
        }

    report: dict = {
        "meta": {
            "boundary": boundary.isoformat(),
            "train_n": len(train),
            "val_n": len(val),
            "pi_params": {"kappa": params.kappa, "omega_home": params.omega_home},
            "dc_fit": {"rho": dc.rho, "home_adv": round(dc.home_adv, 4)},
        },
        "tuning": tune_report,
        "val_full": {
            "dc_raw": metrics(dc_probs_val, outcomes),
            "pi_raw": metrics(pi_probs_val, outcomes),
        },
        "test_half": {
            "dc_raw": metrics(dc_probs_val[cut:], outcomes[cut:]),
            "dc_temp": metrics(dc_probs_cal, outcomes[cut:]),
            "pi_raw": metrics(test_probs, test_out),
            "pi_temp": metrics(pi_probs_cal, test_out),
        },
    }

    # acceptance metric: RPS relative improvement (pi vs DC, walk-forward)
    dc_rps = report["val_full"]["dc_raw"]["rps"]
    pi_rps = report["val_full"]["pi_raw"]["rps"]
    rel = (dc_rps - pi_rps) / dc_rps if dc_rps else 0.0
    report["acceptance"] = {
        "metric": "walk-forward RPS relative improvement (pi vs DC, full val)",
        "dc_rps": dc_rps,
        "pi_rps": pi_rps,
        "relative_improvement": round(rel, 5),
        "target": ">= 0.01",
        "pass": bool(rel >= 0.01),
    }
    dc_rps_t = report["test_half"]["dc_temp"]["rps"]
    pi_rps_t = report["test_half"]["pi_temp"]["rps"]
    rel_t = (dc_rps_t - pi_rps_t) / dc_rps_t if dc_rps_t else 0.0
    report["acceptance"]["relative_improvement_calibrated_test_half"] = round(rel_t, 5)

    # per-league RPS breakdown
    per_league: Dict[str, dict] = {}
    for lg in sorted({m.get("league") or "" for m in val}):
        idx = [i for i, m in enumerate(val) if (m.get("league") or "") == lg]
        if len(idx) < 50:
            continue
        sub_out = [outcomes[i] for i in idx]
        d_rps = mean_rps_1x2([dc_probs_val[i] for i in idx], sub_out)
        p_rps = mean_rps_1x2([pi_probs_val[i] for i in idx], sub_out)
        per_league[lg] = {
            "n": len(idx),
            "dc_rps": round(d_rps, 5),
            "pi_rps": round(p_rps, 5),
            "rel_improvement": round((d_rps - p_rps) / d_rps, 5) if d_rps else None,
        }
    report["per_league"] = per_league

    # ---- write ----
    out_json = Path(REPO_ROOT) / (args.out_prefix + ".json")
    out_md = Path(REPO_ROOT) / (args.out_prefix + ".md")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = [
        "# PI-RATINGS WALK-FORWARD BACKTEST (afb-T2)",
        f"meta: {json.dumps(report['meta'], ensure_ascii=False)}",
        "",
        f"ACCEPTANCE: RPS rel improvement = {rel:+.5f} (target >= 1%) -> "
        + ("PASS" if report["acceptance"]["pass"] else "FAIL"),
        f"  DC  raw RPS={dc_rps:.5f} ll={report['val_full']['dc_raw']['logloss']} hit={report['val_full']['dc_raw']['hit_rate']}",
        f"  PI  raw RPS={pi_rps:.5f} ll={report['val_full']['pi_raw']['logloss']} hit={report['val_full']['pi_raw']['hit_rate']}",
        f"  calibrated test-half: DC temp RPS={dc_rps_t:.5f} vs PI temp RPS={pi_rps_t:.5f} (rel {rel_t:+.5f})",
        f"  temperature: PI T={temp:.4f}, DC T={dc_temp:.4f}",
        "",
        "per-league (n>=50):",
    ]
    for lg, s in per_league.items():
        lines.append(f"  {lg}: n={s['n']} dc={s['dc_rps']} pi={s['pi_rps']} rel={s['rel_improvement']}")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] wrote {out_json}")
    print(f"[done] wrote {out_md}")
    print(f"[ACCEPTANCE] RPS rel improvement {rel:+.5f} -> {'PASS' if report['acceptance']['pass'] else 'FAIL'}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
