#!/usr/bin/env python3
"""Layer-2 afb-T1.3: cup round HA adjustment (平玩版) — Brier/ECE before/after.

Pipeline:
1. Load finished matches (league + round_name), chronological 70/30 split.
2. Fit the base DC model WITH per-league home advantage on train (T2 ③).
3. Fit the cup round-bucket home-goal adjustment on train cup matches only
   (as-of the boundary — zero leakage).
4. Evaluate CUP matches in validation: Brier / ECE (and log-loss) before
   (base per-league HA) vs after (round-adjusted), plus per-bucket table.

Outputs: reports/backtest_t13_report.json + .md
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
from models.cup_round import fit_cup_round_adjustment, round_bucket  # noqa: E402
from models.dc_model import fit_dc  # noqa: E402
from models.metrics import brier_1x2, ece_1x2  # noqa: E402
from models.calibration import nll_1x2  # noqa: E402
from scripts.backtest_dc import (  # noqa: E402
    calibration_buckets,
    load_matches,
    one_x_two_outcome,
    time_split,
    to_match_records,
)
from scripts.backtest_t2 import CUP_LEAGUES  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Cup round HA adjustment backtest (afb-T1.3)")
    p.add_argument("--train-frac", type=float, default=0.7)
    p.add_argument("--half-life", type=float, default=365.0)
    p.add_argument("--min-matches", type=int, default=10)
    p.add_argument("--max-sweeps", type=int, default=30)
    p.add_argument("--tol", type=float, default=1e-4)
    p.add_argument("--max-goals", type=int, default=10)
    p.add_argument("--ha-shrink", type=float, default=200.0)
    p.add_argument("--round-shrink", type=float, default=300.0)
    p.add_argument("--out-prefix", type=str, default="reports/backtest_t13_report")
    args = p.parse_args()

    conn = afb_mysql_connect()
    matches = load_matches(conn, min_date=str(settings_v2.afb_history_min_date))
    print(f"[load] {len(matches)} finished matches")

    boundary, train, val = time_split(matches, args.train_frac)
    cup_val = [m for m in val if (m.get("league") or "") in CUP_LEAGUES and m.get("round_name")]
    print(f"[split] boundary={boundary} train={len(train)} val={len(val)} cup_val(with round)={len(cup_val)}")
    if not cup_val:
        print("[WARN] no cup matches with round_name in validation; nothing to evaluate")
        return 0

    print("[fit] base model (per-league home advantage) ...")
    base = fit_dc(
        to_match_records(train),
        asof=boundary,
        half_life_days=args.half_life,
        min_matches=args.min_matches,
        max_sweeps=args.max_sweeps,
        tol=args.tol,
        per_league_home_adv=True,
        ha_shrink_matches=args.ha_shrink,
    )
    print(f"[fit] base done: {len(base.home_adv_by_league)} leagues; "
          f"rho={base.rho:+.3f} pooled_ha={base.home_adv:+.4f}")

    print("[fit] cup round adjustment (train cup matches only) ...")
    wrapped, fit_detail = fit_cup_round_adjustment(
        base,
        train,
        CUP_LEAGUES,
        half_life_days=args.half_life,
        shrink_matches=args.round_shrink,
        asof=boundary,
    )
    print(f"[fit] adjustment: {json.dumps(fit_detail, ensure_ascii=False)}")

    # ---- evaluate cup validation matches: before vs after ----
    def eval_set(matches_sub: List[dict], adjusted: bool) -> dict:
        prob_rows: List[Dict[str, float]] = []
        outcomes: List[str] = []
        for m in matches_sub:
            if adjusted:
                probs = wrapped.probs_1x2(
                    m["home"], m["away"], max_goals=args.max_goals,
                    league=m.get("league"), round_name=m.get("round_name"),
                )
            else:
                probs = base.probs_1x2(
                    m["home"], m["away"], max_goals=args.max_goals, league=m.get("league")
                )
            prob_rows.append(probs)
            outcomes.append(one_x_two_outcome(m["home_goals"], m["away_goals"]))
        pairs = [
            (row[sel], 1 if out == sel else 0)
            for row, out in zip(prob_rows, outcomes)
            for sel in ("Home", "Draw", "Away")
        ]
        hits = sum(1 for row, out in zip(prob_rows, outcomes) if max(row, key=row.get) == out)
        return {
            "n": len(matches_sub),
            "brier": round(sum(brier_1x2(r, o) for r, o in zip(prob_rows, outcomes)) / len(matches_sub), 5) if matches_sub else None,
            "ece": round(ece_1x2(pairs), 5) if matches_sub else None,
            "logloss": round(nll_1x2(prob_rows, outcomes), 5) if matches_sub else None,
            "hit_rate": round(hits / len(matches_sub), 4) if matches_sub else None,
            "calibration": calibration_buckets(pairs),
        }

    before = eval_set(cup_val, adjusted=False)
    after = eval_set(cup_val, adjusted=True)
    print(f"[eval] cup val: before brier={before['brier']} ece={before['ece']} | "
          f"after brier={after['brier']} ece={after['ece']}")

    # per-bucket breakdown
    per_bucket: Dict[str, dict] = {}
    for b in ("early", "middle", "late", "final"):
        sub = [m for m in cup_val if round_bucket(m.get("round_name")) == b]
        if not sub:
            continue
        per_bucket[b] = {
            "adjustment_delta": fit_detail["buckets"].get(b, {}).get("delta", 0.0),
            "n": len(sub),
            "before": eval_set(sub, adjusted=False),
            "after": eval_set(sub, adjusted=True),
        }

    # per cup competition breakdown
    per_cup: Dict[str, dict] = {}
    for lg in sorted({m.get("league") for m in cup_val}):
        sub = [m for m in cup_val if m.get("league") == lg]
        if len(sub) < 30:
            continue
        per_cup[lg] = {
            "n": len(sub),
            "before": eval_set(sub, adjusted=False),
            "after": eval_set(sub, adjusted=True),
        }

    brier_delta = round((after["brier"] or 0) - (before["brier"] or 0), 5)
    ece_delta = round((after["ece"] or 0) - (before["ece"] or 0), 5)
    report = {
        "meta": {"boundary": boundary.isoformat(), "train_n": len(train), "val_n": len(val),
                 "cup_val_n": len(cup_val), "round_shrink": args.round_shrink,
                 "ha_shrink": args.ha_shrink},
        "fit_detail": fit_detail,
        "acceptance": {
            "metric": "cup matches calibration error (Brier/ECE) decrease after round adjustment",
            "brier_before": before["brier"],
            "brier_after": after["brier"],
            "brier_delta": brier_delta,
            "ece_before": before["ece"],
            "ece_after": after["ece"],
            "ece_delta": ece_delta,
            "pass": bool(brier_delta < 0 or ece_delta < 0),
        },
        "before": {k: v for k, v in before.items() if k != "calibration"},
        "after": {k: v for k, v in after.items() if k != "calibration"},
        "per_bucket": per_bucket,
        "per_cup": per_cup,
    }

    out_json = Path(REPO_ROOT) / (args.out_prefix + ".json")
    out_md = Path(REPO_ROOT) / (args.out_prefix + ".md")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = [
        "# CUP ROUND HA ADJUSTMENT BACKTEST (afb-T1.3 平玩版)",
        f"meta: {json.dumps(report['meta'], ensure_ascii=False)}",
        f"fit: {json.dumps(fit_detail, ensure_ascii=False)}",
        "",
        f"ACCEPTANCE: cup Brier {before['brier']} -> {after['brier']} (delta {brier_delta:+.5f}); "
        f"ECE {before['ece']} -> {after['ece']} (delta {ece_delta:+.5f}) -> "
        + ("PASS" if report["acceptance"]["pass"] else "FAIL"),
        "",
        "per bucket:",
    ]
    for b, v in per_bucket.items():
        lines.append(
            f"  {b}: delta={v['adjustment_delta']:+.4f} n={v['n']} "
            f"brier {v['before']['brier']}->{v['after']['brier']} ece {v['before']['ece']}->{v['after']['ece']}"
        )
    lines.append("per cup:")
    for lg, v in per_cup.items():
        lines.append(
            f"  {lg}: n={v['n']} brier {v['before']['brier']}->{v['after']['brier']} "
            f"ece {v['before']['ece']}->{v['after']['ece']}"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] wrote {out_json}")
    print(f"[done] wrote {out_md}")
    print(f"[ACCEPTANCE] brier delta {brier_delta:+.5f} / ece delta {ece_delta:+.5f} -> "
          f"{'PASS' if report['acceptance']['pass'] else 'FAIL'}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
