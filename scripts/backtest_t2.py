#!/usr/bin/env python3
"""Layer-2 T2: calibration + betting logic + per-league HA + small-sample
downweight — before/after comparison on the T1 holdout framework.

① Calibration  (isotonic / temperature / grouped temperature), fitted on the
   first half of the validation window, applied to the second half — as-of,
   zero leakage (T1 discipline).
② Betting      edge vs de-vig market (flat-stake ROI before/after) on the
   subset with 1x2 market odds, test period only.
③ Per-league home advantage (shrunk toward pooled; ha_shrink_matches).
④ Small-sample cup downweight/exclusion — overall log-loss impact.

Outputs: reports/backtest_dc_t2_report.json + .md
Read-only on sofascore-backfill tables; writes nothing to the DB.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402
from config import settings_v2  # noqa: E402
from models.calibration import (  # noqa: E402
    apply_grouped_temperature,
    apply_isotonic_1x2,
    apply_temperature,
    cup_vs_league_group,
    fit_grouped_temperature_1x2,
    fit_isotonic_1x2,
    fit_temperature_1x2,
    nll_1x2,
)
from models.dc_model import DCModel, MatchRecord, fit_dc  # noqa: E402
from paper.pricing import devig_1x2  # noqa: E402
from scripts.backtest_dc import (  # noqa: E402
    _fractional_to_decimal,
    calibration_buckets,
    load_matches,
    one_x_two_outcome,
    per_league,
    time_split,
    to_match_records,
)

CUP_LEAGUES = {
    "FA Cup", "Copa del Rey", "Coppa Italia", "Coupe de France", "DFB Pokal",
    "EFL Cup", "Emperor's Cup", "J.League Cup", "Australia Cup", "Chinese FA Cup",
}


# ------------------------------------------------------------ market odds


def collect_market_odds(conn, matches: List[dict]) -> Dict[str, Dict[str, float]]:
    """Average full-time 1x2 decimal odds per match (from fractional values)."""
    ids = [str(m["match_id"]) for m in matches if m.get("match_id")]
    by_id = {str(m["match_id"]): m for m in matches if m.get("match_id")}
    collected: Dict[str, Dict[str, List[float]]] = {}
    cur = conn.cursor()
    chunk = 500
    choice_map = {"1": "Home", "X": "Draw", "2": "Away"}
    for i in range(0, len(ids), chunk):
        part = ids[i : i + chunk]
        if not part:
            continue
        cur.execute(
            """
            SELECT o.match_id, o.choice_name, o.fractional_value
            FROM match_odds o
            WHERE o.odds_type='1x2' AND o.market_name='Full time'
              AND o.choice_name IN ('1','X','2')
              AND o.match_id IN (%s)
            """
            % ",".join(["%s"] * len(part)),
            tuple(part),
        )
        for mid, choice, frac in cur.fetchall():
            dec = _fractional_to_decimal(frac)
            if dec is None:
                continue
            collected.setdefault(str(mid), {}).setdefault(choice_map.get(str(choice), ""), []).append(dec)
    out: Dict[str, Dict[str, float]] = {}
    for mid, choices in collected.items():
        if mid not in by_id:
            continue
        if all(choices.get(sel) for sel in ("Home", "Draw", "Away")):
            out[mid] = {
                "Home": sum(choices["Home"]) / len(choices["Home"]),
                "Draw": sum(choices["Draw"]) / len(choices["Draw"]),
                "Away": sum(choices["Away"]) / len(choices["Away"]),
            }
    return out


# ------------------------------------------------------------- betting sim


def simulate_flat_stake(
    rows: List[dict],
    threshold: float,
) -> dict:
    """Flat-stake 1-unit bets where calibrated-or-raw edge >= threshold.

    Each row: {p_model per selection, p_market per selection, odds per
    selection, outcome}. Edge = p_model - p_market_devig. Payout at market
    average decimal odds.
    """
    stakes = payouts = 0.0
    bets = hits = 0
    buckets = {"0.03-0.05": [0, 0], "0.05-0.10": [0, 0], "0.10-0.20": [0, 0], "0.20+": [0, 0]}
    for r in rows:
        best_sel, best_edge = None, -1.0
        for sel in ("Home", "Draw", "Away"):
            edge = r["p_model"][sel] - r["p_market"][sel]
            if edge > best_edge:
                best_sel, best_edge = sel, edge
        if best_sel is None or best_edge < threshold:
            continue
        best_edge_q = round(best_edge, 6)  # guard fp noise (0.60-0.50 = 0.0999...)
        stakes += 1.0
        bets += 1
        win = r["outcome"] == best_sel
        hits += 1 if win else 0
        payouts += r["odds"][best_sel] if win else 0.0
        for bkey, (lo_hi) in {
            "0.03-0.05": (0.03, 0.05),
            "0.05-0.10": (0.05, 0.10),
            "0.10-0.20": (0.10, 0.20),
            "0.20+": (0.20, math.inf),
        }.items():
            lo, hi = lo_hi
            if lo <= best_edge_q < hi or (hi == math.inf and best_edge_q >= lo):
                buckets[bkey][0] += 1
                buckets[bkey][1] += 1 if win else 0
                break
    roi = (payouts - stakes) / stakes if stakes else None
    return {
        "bets": bets,
        "staked": round(stakes, 2),
        "roi": round(roi, 4) if roi is not None else None,
        "hit_rate": round(hits / bets, 4) if bets else None,
        "edge_buckets": {
            k: {"bets": v[0], "hit_rate": round(v[1] / v[0], 4) if v[0] else None}
            for k, v in buckets.items()
        },
    }


def build_bet_rows(
    model_probs: List[Dict[str, Dict[str, float]]],
    market_odds: Dict[str, Dict[str, float]],
    matches: List[dict],
) -> List[dict]:
    rows: List[dict] = []
    for i, m in enumerate(matches):
        mid = str(m.get("match_id") or "")
        odds = market_odds.get(mid)
        if not odds:
            continue
        try:
            ph, pd_, pa = devig_1x2(odds["Home"], odds["Draw"], odds["Away"])
        except Exception:
            continue
        p_market = {"Home": ph, "Draw": pd_, "Away": pa}
        if not all(math.isfinite(v) for v in p_market.values()):
            continue
        rows.append(
            {
                "p_model": model_probs[i],
                "p_market": p_market,
                "odds": odds,
                "outcome": one_x_two_outcome(m["home_goals"], m["away_goals"]),
            }
        )
    return rows


# ------------------------------------------------------------- 1X2 scoring


def score_probs(prob_rows: List[Dict[str, float]], matches: List[dict]) -> dict:
    outcomes = [one_x_two_outcome(m["home_goals"], m["away_goals"]) for m in matches]
    ll = nll_1x2(prob_rows, outcomes)
    hits = sum(
        1
        for row, out in zip(prob_rows, outcomes)
        if max(row, key=row.get) == out
    )
    pairs: List[Tuple[float, int]] = []
    for row, out in zip(prob_rows, outcomes):
        for sel in ("Home", "Draw", "Away"):
            pairs.append((row[sel], 1 if out == sel else 0))
    return {
        "n": len(matches),
        "hit_rate": round(hits / len(matches), 4) if matches else None,
        "logloss": round(ll, 4) if matches else None,
        "calibration": calibration_buckets(pairs),
    }


def model_probs_for(model: DCModel, matches: List[dict], max_goals: int, use_league: bool) -> List[Dict[str, Dict[str, float]]]:
    out: List[Dict[str, Dict[str, float]]] = []
    for m in matches:
        lg = m["league"] if use_league else None
        out.append(model.probs_1x2(m["home"], m["away"], max_goals=max_goals, league=lg))
    return out


# --------------------------------------------------------------------- main


def main() -> int:
    p = argparse.ArgumentParser(description="T2 calibration/betting/HA/downweight before-after")
    p.add_argument("--train-frac", type=float, default=0.7)
    p.add_argument("--calib-frac", type=float, default=0.5, help="fraction of validation used to fit calibrators")
    p.add_argument("--half-life", type=float, default=365.0)
    p.add_argument("--min-matches", type=int, default=10)
    p.add_argument("--max-sweeps", type=int, default=30)
    p.add_argument("--tol", type=float, default=1e-4)
    p.add_argument("--max-goals", type=int, default=10)
    p.add_argument("--ha-shrink", type=float, default=200.0)
    p.add_argument("--thresholds", type=str, default="0.03,0.05,0.10")
    p.add_argument("--out-prefix", type=str, default="reports/backtest_dc_t2_report")
    args = p.parse_args()

    thresholds = [float(x) for x in args.thresholds.split(",") if x.strip()]
    conn = afb_mysql_connect()
    matches = load_matches(conn, min_date=str(settings_v2.afb_history_min_date))
    print(f"[load] {len(matches)} finished matches")

    boundary, train, val = time_split(matches, args.train_frac)
    print(f"[split] boundary={boundary} train={len(train)} val={len(val)}")
    val_sorted = sorted(val, key=lambda m: m["match_date"])
    cut_idx = int(len(val_sorted) * args.calib_frac)
    calib_matches = val_sorted[:cut_idx]
    test_matches = val_sorted[cut_idx:]
    calib_cut = test_matches[0]["match_date"] if test_matches else None
    print(f"[split] calib={len(calib_matches)} (-> {calib_matches[-1]['match_date']}) test={len(test_matches)} (from {calib_cut})")

    print("[fit] base model ...")
    base = fit_dc(
        to_match_records(train),
        asof=boundary,
        half_life_days=args.half_life,
        min_matches=args.min_matches,
        max_sweeps=args.max_sweeps,
        tol=args.tol,
    )
    print(f"[fit] base done: rho={base.rho:+.3f} home_adv={base.home_adv:+.4f}")

    report: dict = {"meta": {"boundary": boundary.isoformat(), "train_n": len(train), "val_n": len(val),
                             "calib_n": len(calib_matches), "test_n": len(test_matches),
                             "calib_cut": str(calib_cut)}}

    # -------------------------------------------------- ① calibration
    print("[T2-1] calibration ...")
    calib_probs = model_probs_for(base, calib_matches, args.max_goals, use_league=False)
    calib_outcomes = [one_x_two_outcome(m["home_goals"], m["away_goals"]) for m in calib_matches]
    test_probs_raw = model_probs_for(base, test_matches, args.max_goals, use_league=False)
    test_outcomes = [one_x_two_outcome(m["home_goals"], m["away_goals"]) for m in test_matches]

    iso_maps = fit_isotonic_1x2(calib_probs, calib_outcomes)
    temp, temp_ll = fit_temperature_1x2(calib_probs, calib_outcomes)
    groups_calib = [cup_vs_league_group(m["league"]) for m in calib_matches]
    grouped = fit_grouped_temperature_1x2(calib_probs, calib_outcomes, groups_calib)

    test_iso = [apply_isotonic_1x2(iso_maps, r) for r in test_probs_raw]
    test_temp = [apply_temperature(r, temp) for r in test_probs_raw]
    groups_test = [cup_vs_league_group(m["league"]) for m in test_matches]
    test_gtemp = apply_grouped_temperature(test_probs_raw, groups_test, grouped)

    sec1 = {
        "calibrator_fit": {"temperature": round(temp, 4), "temperature_calib_ll": round(temp_ll, 4),
                           "grouped": {g: {"T": round(t, 4)} for g, (t, _) in grouped.items()}},
        "before": score_probs(test_probs_raw, test_matches),
        "after_isotonic": score_probs(test_iso, test_matches),
        "after_temperature": score_probs(test_temp, test_matches),
        "after_grouped_temperature": score_probs(test_gtemp, test_matches),
    }
    report["T2_1_calibration"] = sec1
    print(f"[T2-1] test ll: before={sec1['before']['logloss']} iso={sec1['after_isotonic']['logloss']} "
          f"temp={sec1['after_temperature']['logloss']} grouped={sec1['after_grouped_temperature']['logloss']}")

    # -------------------------------------------------- ② betting sim
    print("[T2-2] betting simulation (test period, market odds subset) ...")
    market_odds = collect_market_odds(conn, test_matches)
    print(f"[T2-2] test matches with market odds: {len(market_odds)}")
    test_with_odds = [m for m in test_matches if str(m.get("match_id") or "") in market_odds]
    idx_with_odds = [i for i, m in enumerate(test_matches) if str(m.get("match_id") or "") in market_odds]
    raw_rows = build_bet_rows([test_probs_raw[i] for i in idx_with_odds], market_odds, test_with_odds)
    temp_rows = build_bet_rows([test_temp[i] for i in idx_with_odds], market_odds, test_with_odds)
    sim = {"n_subset": len(test_with_odds), "thresholds": {}}
    for th in thresholds:
        sim["thresholds"][f"{th:g}"] = {
            "before_raw": simulate_flat_stake(raw_rows, th),
            "after_temperature": simulate_flat_stake(temp_rows, th),
        }
    report["T2_2_betting"] = sim
    for th in thresholds:
        b = sim["thresholds"][f"{th:g}"]
        print(f"[T2-2] th={th:g}: raw bets={b['before_raw']['bets']} roi={b['before_raw']['roi']} | "
              f"temp bets={b['after_temperature']['bets']} roi={b['after_temperature']['roi']}")

    # -------------------------------------------------- ③ per-league HA
    print("[T2-3] per-league home advantage fit ...")
    plha = fit_dc(
        to_match_records(train),
        asof=boundary,
        half_life_days=args.half_life,
        min_matches=args.min_matches,
        max_sweeps=args.max_sweeps,
        tol=args.tol,
        per_league_home_adv=True,
        ha_shrink_matches=args.ha_shrink,
    )
    ha_top = sorted(plha.home_adv_by_league.items(), key=lambda kv: -kv[1])[:5]
    print(f"[T2-3] per-league HA fitted ({len(plha.home_adv_by_league)} leagues); top: "
          + ", ".join(f"{lg}={v:+.3f}" for lg, v in ha_top))
    base_probs_val = model_probs_for(base, val, args.max_goals, use_league=False)
    plha_probs_val = model_probs_for(plha, val, args.max_goals, use_league=True)
    focus = {"A-League Men", "J1 League", "K League 1", "AFC Champions League Two", "Chinese Super League"}
    per_league_out = {}
    for lg in sorted({m["league"] for m in val}):
        sub_idx = [i for i, m in enumerate(val) if m["league"] == lg]
        sub_matches = [val[i] for i in sub_idx]
        before = score_probs([base_probs_val[i] for i in sub_idx], sub_matches)
        after = score_probs([plha_probs_val[i] for i in sub_idx], sub_matches)
        per_league_out[lg] = {
            "n": before["n"],
            "before": {"hit_rate": before["hit_rate"], "logloss": before["logloss"]},
            "after": {"hit_rate": after["hit_rate"], "logloss": after["logloss"]},
        }
    report["T2_3_per_league_ha"] = {
        "meta": {"ha_shrink_matches": args.ha_shrink,
                 "home_adv_global": round(base.home_adv, 4),
                 "leagues_fitted": len(plha.home_adv_by_league),
                 "top_home_adv": {lg: round(v, 4) for lg, v in ha_top}},
        "overall": {
            "before": score_probs(base_probs_val, val)["logloss"],
            "after": score_probs(plha_probs_val, val)["logloss"],
        },
        "per_league": per_league_out,
        "focus": {lg: per_league_out.get(lg) for lg in sorted(focus)},
    }
    print(f"[T2-3] overall ll: before={report['T2_3_per_league_ha']['overall']['before']} "
          f"after={report['T2_3_per_league_ha']['overall']['after']}")

    # -------------------------------------------------- ④ cup downweight
    print("[T2-4] small-sample cup downweight ...")
    variants = {}
    train_cup_names = {m.league for m in to_match_records(train) if m.league in CUP_LEAGUES}
    half_weights = {lg: 0.5 for lg in train_cup_names}
    excl = fit_dc(
        to_match_records([m for m in train if m["league"] not in CUP_LEAGUES]),
        asof=boundary, half_life_days=args.half_life, min_matches=args.min_matches,
        max_sweeps=args.max_sweeps, tol=args.tol,
    )
    half = fit_dc(
        to_match_records(train),
        asof=boundary, half_life_days=args.half_life, min_matches=args.min_matches,
        max_sweeps=args.max_sweeps, tol=args.tol,
        league_weights=half_weights,
    )
    base_ll = nll_1x2(base_probs_val, [one_x_two_outcome(m["home_goals"], m["away_goals"]) for m in val])
    excl_ll = nll_1x2(model_probs_for(excl, val, args.max_goals, use_league=False),
                      [one_x_two_outcome(m["home_goals"], m["away_goals"]) for m in val])
    half_ll = nll_1x2(model_probs_for(half, val, args.max_goals, use_league=False),
                      [one_x_two_outcome(m["home_goals"], m["away_goals"]) for m in val])
    variants = {
        "baseline": round(base_ll, 4),
        "cups_excluded": round(excl_ll, 4),
        "cups_weight_0_5": round(half_ll, 4),
    }
    report["T2_4_downweight"] = {
        "cup_leagues": sorted(train_cup_names),
        "val_logloss": variants,
        "delta_vs_baseline": {k: round(v - variants["baseline"], 4) for k, v in variants.items() if k != "baseline"},
    }
    print(f"[T2-4] val logloss: {variants}")

    # -------------------------------------------------- write reports
    out_json = Path(REPO_ROOT) / (args.out_prefix + ".json")
    out_md = Path(REPO_ROOT) / (args.out_prefix + ".md")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    out_md.write_text(render_md(report), encoding="utf-8")
    print(f"[done] wrote {out_json}")
    print(f"[done] wrote {out_md}")
    conn.close()
    return 0


def render_md(report: dict) -> str:
    s1 = report.get("T2_1_calibration", {})
    s2 = report.get("T2_2_betting", {})
    s3 = report.get("T2_3_per_league_ha", {})
    s4 = report.get("T2_4_downweight", {})
    lines: List[str] = []
    lines.append("# DC T2 — calibration / betting / per-league HA / downweight 對比報告")
    lines.append("")
    lines.append(f"meta: {json.dumps(report.get('meta', {}), ensure_ascii=False)}")
    lines.append("")
    lines.append("## ① 校準（test period）")
    for key, label in (("before", "before (raw)"), ("after_isotonic", "after isotonic"),
                       ("after_temperature", "after temperature"), ("after_grouped_temperature", "after grouped T")):
        s = s1.get(key, {})
        lines.append(f"- {label}: n={s.get('n')} hit={s.get('hit_rate')} ll={s.get('logloss')}")
    lines.append(f"- calibrator: {json.dumps(s1.get('calibrator_fit', {}), ensure_ascii=False)}")
    lines.append("")
    lines.append("## ② flat-stake ROI（test period 市場子集）")
    lines.append(f"subset n={s2.get('n_subset')}")
    for th, b in (s2.get("thresholds") or {}).items():
        br = b.get("before_raw", {})
        af = b.get("after_temperature", {})
        lines.append(f"- threshold {th}: raw bets={br.get('bets')} roi={br.get('roi')} hit={br.get('hit_rate')} | "
                     f"temp bets={af.get('bets')} roi={af.get('roi')} hit={af.get('hit_rate')}")
        for bk, bv in (af.get("edge_buckets") or {}).items():
            lines.append(f"    - bucket {bk}: bets={bv.get('bets')} hit={bv.get('hit_rate')}")
    lines.append("")
    lines.append("## ③ per-league home advantage（full val）")
    lines.append(f"overall ll: before={s3.get('overall', {}).get('before')} after={s3.get('overall', {}).get('after')}")
    for lg, v in (s3.get("focus") or {}).items():
        if v:
            lines.append(f"- {lg}: n={v['n']} hit {v['before']['hit_rate']}->{v['after']['hit_rate']} "
                         f"ll {v['before']['logloss']}->{v['after']['logloss']}")
    lines.append("")
    lines.append("## ④ cup downweight（full val log-loss）")
    lines.append(f"- variants: {json.dumps(s4.get('val_logloss', {}), ensure_ascii=False)}")
    lines.append(f"- delta vs baseline: {json.dumps(s4.get('delta_vs_baseline', {}), ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
