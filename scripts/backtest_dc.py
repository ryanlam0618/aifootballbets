#!/usr/bin/env python3
"""Layer-2 T1 backtest framework for the Dixon-Coles model (dc_tau_v1).

Modes
-----
- holdout:      time-ordered 70/30 split (first 70% of match dates -> train,
                last 30% -> validation). Strictly chronological — random
                splits are forbidden (time-series leakage).
- walkforward:  rolling windows over the validation period; each window is
                fit as-of its start date (strictly earlier matches only),
                then predicts the matches inside the window. Step size is
                configurable (default quarterly = 91 days).

Metrics
-------
- 1X2: hit rate (argmax), multi-class log-loss, calibration buckets
- AH:  per line (0/0.25/0.5/0.75/1) home-side predicted eff vs realised eff,
       pick expected-points and strict hit rate (settlement semantics mirror
       models/dc_model.py exactly)
- Market: for validation matches with 1x2 odds in match_odds, de-vigged
       market probabilities (paper.pricing.devig_1x2) vs model probabilities
       -> mean edge per selection + market-favourite baseline hit rate

Outputs
-------
- reports/backtest_dc_report.txt  (human-readable)
- reports/backtest_dc_report.json (machine-readable, overall + per league)

Read-only on sofascore-backfill tables; writes nothing to the DB.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402
from afbdb.history import fetch_history_rows  # noqa: E402
from config import settings_v2  # noqa: E402
from models.dc_model import DCModel, MatchRecord, fit_dc  # noqa: E402
from paper.pricing import devig_1x2  # noqa: E402


# ------------------------------------------------------------ data loading


def load_matches(conn, min_date: str) -> List[dict]:
    """Finished matches with league labels from the DB history provider."""
    rows = fetch_history_rows(conn, min_date=min_date)
    out: List[dict] = []
    for r in rows:
        try:
            out.append(
                {
                    "match_id": r.get("match_id"),
                    "match_date": datetime.strptime(r["match_date"], "%Y-%m-%d").date(),
                    "home": r["home_team"],
                    "away": r["away_team"],
                    "league": r["league"],
                    "home_goals": int(r["home_goals"]),
                    "away_goals": int(r["away_goals"]),
                }
            )
        except (TypeError, ValueError, KeyError):
            continue
    out.sort(key=lambda m: m["match_date"])
    return out


def to_match_records(matches: Sequence[dict]) -> List[MatchRecord]:
    return [MatchRecord(m["match_date"], m["home"], m["away"], m["home_goals"], m["away_goals"]) for m in matches]


# ------------------------------------------------------------- split logic


def time_split(matches: Sequence[dict], train_frac: float = 0.7) -> Tuple[date, List[dict], List[dict]]:
    """Chronological split by the sorted-date index at `train_frac`.

    The boundary date itself belongs to validation; training is strictly
    `match_date < boundary` so there is no same-day leakage.
    """
    if not matches:
        raise ValueError("no matches")
    dates = sorted(m["match_date"] for m in matches)
    idx = int(len(dates) * train_frac)
    idx = max(1, min(idx, len(dates) - 1))
    boundary = dates[idx]
    train = [m for m in matches if m["match_date"] < boundary]
    val = [m for m in matches if m["match_date"] >= boundary]
    return boundary, train, val


def walkforward_windows(val_start: date, val_end: date, step_days: int) -> List[Tuple[date, date, date]]:
    """(asof, win_start, win_end) windows tiling [val_start, val_end].

    Each window is fit as-of its start (strictly earlier matches only) and
    predicts matches with win_start <= date <= win_end. No gaps, no overlap
    in predicted matches.
    """
    if step_days <= 0:
        raise ValueError("step_days must be positive")
    windows: List[Tuple[date, date, date]] = []
    start = val_start
    while start <= val_end:
        end = min(start + timedelta(days=step_days - 1), val_end)
        windows.append((start, start, end))
        start = end + timedelta(days=1)
    return windows


# ----------------------------------------------------------------- metrics


def one_x_two_outcome(home_goals: int, away_goals: int) -> str:
    return "Home" if home_goals > away_goals else ("Draw" if home_goals == away_goals else "Away")


def logloss_1x2(prob_map: Dict[str, Dict[str, float]], outcomes: Sequence[str], eps: float = 1e-12) -> float:
    """Mean multi-class log-loss; prob_map values must include all outcomes."""
    if not outcomes:
        return float("nan")
    total = 0.0
    for i, out in enumerate(outcomes):
        p = float(prob_map[i][out])
        total -= math.log(max(p, eps))
    return total / len(outcomes)


def hit_rate_1x2(prob_map: Dict[int, Dict[str, float]], outcomes: Sequence[str]) -> float:
    if not outcomes:
        return float("nan")
    hits = 0
    for i, out in enumerate(outcomes):
        pred = max(prob_map[i], key=prob_map[i].get)
        if pred == out:
            hits += 1
    return hits / len(outcomes)


def calibration_buckets(pairs: Sequence[Tuple[float, int]], n_buckets: int = 10) -> List[dict]:
    """Bucket (predicted_prob, realised_indicator) pairs into equal-width bins."""
    buckets: List[dict] = []
    width = 1.0 / n_buckets
    for b in range(n_buckets):
        lo, hi = b * width, (b + 1) * width
        members = [(p, r) for p, r in pairs if (lo <= p < hi) or (b == n_buckets - 1 and p == 1.0)]
        buckets.append(
            {
                "lo": round(lo, 3),
                "hi": round(hi, 3),
                "n": len(members),
                "mean_pred": round(sum(p for p, _ in members) / len(members), 4) if members else None,
                "realised": round(sum(r for _, r in members) / len(members), 4) if members else None,
            }
        )
    return buckets


def ah_realised_eff(home_goals: int, away_goals: int, home_line: float) -> float:
    """Home-side expected points (win=1, push=0.5, lose=0) for home + line.

    Settlement semantics mirror models/dc_model.py: integer lines can push,
    half lines cannot, quarter lines are equal splits of adjacent lines.
    """
    def _single(line: float) -> float:
        d = home_goals + line - away_goals
        if d > 1e-9:
            return 1.0
        if abs(d) <= 1e-9:
            return 0.5
        return 0.0

    q = round(home_line * 4)
    if abs(home_line * 4 - q) > 1e-9:
        raise ValueError(f"unsupported AH line: {home_line}")
    if q % 2 == 0:
        return _single(home_line)
    if q > 0:
        l1, l2 = (q - 1) / 4.0, (q + 1) / 4.0
    else:
        l1, l2 = (q + 1) / 4.0, (q - 1) / 4.0
    return 0.5 * (_single(l1) + _single(l2))


AH_LINES = (0.0, 0.25, 0.5, 0.75, 1.0)


def score_1x2(model: DCModel, matches: Sequence[dict], max_goals: int) -> dict:
    prob_map: Dict[int, Dict[str, float]] = {}
    outcomes = []
    for i, m in enumerate(matches):
        prob_map[i] = model.probs_1x2(m["home"], m["away"], max_goals=max_goals)
        outcomes.append(one_x_two_outcome(m["home_goals"], m["away_goals"]))
    pairs: List[Tuple[float, int]] = []
    for i in range(len(matches)):
        for sel in ("Home", "Draw", "Away"):
            realised = 1 if outcomes[i] == sel else 0
            pairs.append((prob_map[i][sel], realised))
    return {
        "n": len(matches),
        "hit_rate": round(hit_rate_1x2(prob_map, outcomes), 4),
        "logloss": round(logloss_1x2(prob_map, outcomes), 4),
        "calibration": calibration_buckets(pairs),
    }


def score_ah(model: DCModel, matches: Sequence[dict], max_goals: int) -> dict:
    per_line: Dict[float, dict] = {}
    for line in AH_LINES:
        pred_effs: List[float] = []
        real_effs: List[float] = []
        picks_strict = picks_pts = 0
        for m in matches:
            mat = model.score_matrix(m["home"], m["away"], max_goals=max_goals)
            res = ah_probs_home(mat, line)
            home_eff = res["eff"]
            # pick the side with the higher expected rate
            pick_home = home_eff >= 0.5
            pick_pred = home_eff if pick_home else 1.0 - home_eff
            real_home = ah_realised_eff(m["home_goals"], m["away_goals"], line)
            pick_real = real_home if pick_home else 1.0 - real_home
            pred_effs.append(home_eff)
            real_effs.append(real_home)
            if pick_pred > 0.5:
                picks_pts += pick_real
                picks_strict += 1 if pick_real == 1.0 else 0
        n = len(matches)
        per_line[line] = {
            "n": n,
            "mean_pred_eff": round(sum(pred_effs) / n, 4) if n else None,
            "mean_real_eff": round(sum(real_effs) / n, 4) if n else None,
            "pick_n": sum(1 for e in pred_effs if max(e, 1 - e) > 0.5),
            "pick_hit_rate": round(picks_strict / n, 4) if n else None,
            "pick_pts_per_bet": round(picks_pts / n, 4) if n else None,
        }
    return per_line


def ah_probs_home(mat, home_line: float) -> dict:
    """Home side of the AH market (thin wrapper over dc_model.ah_probs)."""
    from models.dc_model import ah_probs

    return ah_probs(mat, home_line)["home"]


def _fractional_to_decimal(text: object) -> Optional[float]:
    """Convert fractional odds ('5/4') to decimal (2.25); whole '3' -> 3.0.

    Non-parsable / non-positive-value tokens return None (caller skips).
    """
    s = str(text or "").strip()
    if not s:
        return None
    try:
        if "/" in s:
            a_s, b_s = s.split("/", 1)
            a, b = float(a_s), float(b_s)
            if b <= 0 or a < 0:
                return None
            return 1.0 + a / b
        v = float(s)
        return v if v > 1.0 else None
    except ValueError:
        return None


def market_comparison(conn, matches: Sequence[dict], model: DCModel, max_goals: int) -> dict:
    """Model vs de-vigged market on validation matches with 1x2 odds.

    appdb stores 1x2 prices per choice (choice_name '1'/'X'/'2') as fractional
    odds in `fractional_value` with market_name='Full time' — the
    home_odds/draw_odds/away_odds columns are NULL in the current backfill.
    """
    ids = [m.get("match_id") for m in matches if m.get("match_id")]
    if not ids:
        return {"n": 0}
    by_id = {str(m["match_id"]): m for m in matches if m.get("match_id")}
    choice_map = {"1": "Home", "X": "Draw", "2": "Away"}
    # per (match_id, choice) -> list of decimal odds across bookmakers
    collected: Dict[str, Dict[str, List[float]]] = {}
    cur = conn.cursor()
    chunk = 500
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

    edges = {"Home": [], "Draw": [], "Away": []}
    market_hit = model_hit = both_hit = n = 0
    for mid, choices in collected.items():
        m = by_id.get(mid)
        if m is None:
            continue
        if not all(choices.get(sel) for sel in ("Home", "Draw", "Away")):
            continue
        ho = sum(choices["Home"]) / len(choices["Home"])
        dr = sum(choices["Draw"]) / len(choices["Draw"])
        ao = sum(choices["Away"]) / len(choices["Away"])
        try:
            probs = model.probs_1x2(m["home"], m["away"], max_goals=max_goals)
        except Exception:
            continue
        try:
            ph, pd_, pa = devig_1x2(ho, dr, ao)
        except Exception:
            continue
        outcome = one_x_two_outcome(m["home_goals"], m["away_goals"])
        for sel, mp, mk in (("Home", probs["Home"], ph), ("Draw", probs["Draw"], pd_), ("Away", probs["Away"], pa)):
            if not (math.isfinite(mp) and math.isfinite(mk)):
                continue
            edges[sel].append(mp - mk)
        n += 1
        market_probs = {"Home": ph, "Draw": pd_, "Away": pa}
        m_fav = max(market_probs, key=market_probs.get)
        m_model = max(probs, key=probs.get)
        mh = m_fav == outcome
        dh = m_model == outcome
        market_hit += mh
        model_hit += dh
        both_hit += mh and dh
    out = {
        "n_matches_with_odds": n,
        "mean_edge": {
            sel: (
                round(sum(v) / len(v), 4)
                if v and all(math.isfinite(x) for x in v)
                else None
            )
            for sel, v in edges.items()
        },
        "market_fav_hit_rate": round(market_hit / n, 4) if n else None,
        "model_hit_rate_same_subset": round(model_hit / n, 4) if n else None,
        "agree_rate": round(both_hit / n, 4) if n else None,
    }
    return out


# ---------------------------------------------------------------- reporting


def per_league(matches: Sequence[dict]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for m in matches:
        out[m["league"]] = out.get(m["league"], 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def run_mode(mode: str, matches: List[dict], args, conn) -> dict:
    """Holdout or walkforward evaluation; returns a report dict section."""
    max_goals = args.max_goals
    sections: Dict[str, dict] = {}
    all_val: List[dict] = []

    if mode == "holdout":
        boundary, train, val = time_split(matches, args.train_frac)
        print(f"[holdout] boundary={boundary} train={len(train)} val={len(val)}")
        model = fit_dc(
            to_match_records(train),
            asof=boundary,
            half_life_days=args.half_life,
            min_matches=args.min_matches,
            max_sweeps=args.max_sweeps,
            tol=args.tol,
        )
        sections["_meta"] = {
            "boundary": boundary.isoformat(),
            "train_n": len(train),
            "val_n": len(val),
            "rho": model.rho,
            "home_adv": round(model.home_adv, 4),
            "loglik_per_match": round(model.loglik_per_match, 4),
        }
        sections["overall"] = score_1x2(model, val, max_goals)
        sections["ah_by_line"] = score_ah(model, val, max_goals)
        all_val = val

    else:  # walkforward
        dates = [m["match_date"] for m in matches]
        boundary, train, val = time_split(matches, args.train_frac)
        val_start, val_end = val[0]["match_date"], val[-1]["match_date"]
        windows = walkforward_windows(val_start, val_end, args.step_days)
        print(f"[walkforward] {len(windows)} windows ({val_start} -> {val_end}), step={args.step_days}d")
        wf_summary = []
        for wi, (asof, ws, we) in enumerate(windows):
            window_matches = [m for m in matches if ws <= m["match_date"] <= we]
            if not window_matches:
                continue
            model = fit_dc(
                to_match_records(matches),
                asof=asof,
                half_life_days=args.half_life,
                min_matches=args.min_matches,
                max_sweeps=args.max_sweeps,
                tol=args.tol,
            )
            s = score_1x2(model, window_matches, max_goals)
            print(
                f"  window {wi + 1}/{len(windows)} asof={asof} n={len(window_matches)} "
                f"hit={s['hit_rate']} ll={s['logloss']}"
            )
            wf_summary.append({"asof": asof.isoformat(), "from": ws.isoformat(), "to": we.isoformat(), **s})
            all_val.extend(window_matches)
        sections["_meta"] = {
            "windows": len(windows),
            "step_days": args.step_days,
            "val_start": val_start.isoformat(),
            "val_end": val_end.isoformat(),
        }
        sections["windows"] = wf_summary
        # aggregate across all walked matches: re-score once on pooled picks is
        # approximated by averaging window metrics weighted by n
        tot = sum(w["n"] for w in wf_summary) or 1
        sections["overall"] = {
            "n": tot,
            "hit_rate": round(sum(w["hit_rate"] * w["n"] for w in wf_summary) / tot, 4),
            "logloss": round(sum(w["logloss"] * w["n"] for w in wf_summary) / tot, 4),
        }

    sections["val_leagues"] = per_league(all_val)

    # per-league breakdown (1X2 only; AH per-league needs refits per window —
    # pooled per-league AH reported for holdout mode only)
    if mode == "holdout" and all_val:
        league_sections = {}
        for lg in sorted({m["league"] for m in all_val}):
            sub = [m for m in all_val if m["league"] == lg]
            league_sections[lg] = score_1x2(model, sub, max_goals)
        sections["per_league"] = league_sections
        sections["ah_by_line_overall"] = sections["ah_by_line"]
        sections.pop("ah_by_line", None)

    if all_val and not args.skip_market:
        try:
            sections["market"] = market_comparison(conn, all_val, model, max_goals)
        except Exception as exc:
            print(f"[WARN] market comparison failed: {exc}")
            sections["market"] = {"error": str(exc)}
    return sections


def render_txt(report: dict) -> str:
    lines: List[str] = []
    lines.append("DIXON-COLES BACKTEST REPORT (dc_tau_v1)")
    lines.append(f"generated: {datetime.utcnow().isoformat(timespec='seconds')}Z")
    lines.append(f"data: appdb finished matches >= {report.get('meta', {}).get('min_date', 'n/a')}")
    lines.append("")
    for mode in ("holdout", "walkforward"):
        sec = report.get(mode)
        if not sec:
            continue
        lines.append("=" * 60)
        lines.append(f"MODE: {mode.upper()}")
        lines.append("=" * 60)
        lines.append(f"meta: {json.dumps(sec.get('_meta', {}), ensure_ascii=False)}")
        ov = sec.get("overall", {})
        lines.append(f"1X2 overall: n={ov.get('n')} hit_rate={ov.get('hit_rate')} logloss={ov.get('logloss')}")
        ah = sec.get("ah_by_line_overall") or {}
        for line, s in ah.items():
            lines.append(
                f"AH {line}: n={s['n']} pred={s['mean_pred_eff']} real={s['mean_real_eff']} "
                f"pick_hit={s['pick_hit_rate']} pts/bet={s['pick_pts_per_bet']}"
            )
        mk = sec.get("market") or {}
        if mk:
            lines.append(f"market: n={mk.get('n_matches_with_odds')} edges={mk.get('mean_edge')}")
            lines.append(
                f"market: fav_hit={mk.get('market_fav_hit_rate')} model_hit={mk.get('model_hit_rate_same_subset')} "
                f"agree={mk.get('agree_rate')}"
            )
        pl = sec.get("per_league") or {}
        for lg, s in pl.items():
            lines.append(f"league {lg}: n={s['n']} hit={s['hit_rate']} ll={s['logloss']}")
        wf = sec.get("windows") or []
        for w in wf:
            lines.append(f"wf {w['asof']}: n={w['n']} hit={w['hit_rate']} ll={w['logloss']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Dixon-Coles backtest (holdout + walkforward)")
    p.add_argument("--mode", choices=["holdout", "walkforward", "both"], default="both")
    p.add_argument("--train-frac", type=float, default=0.7)
    p.add_argument("--step-days", type=int, default=91, help="walkforward window step (default quarterly)")
    p.add_argument("--half-life", type=float, default=365.0)
    p.add_argument("--min-matches", type=int, default=10)
    p.add_argument("--max-sweeps", type=int, default=40)
    p.add_argument("--tol", type=float, default=1e-5)
    p.add_argument("--max-goals", type=int, default=10)
    p.add_argument("--min-date", type=str, default=None, help="history lower bound (default from settings)")
    p.add_argument("--leagues", type=str, default=None, help="comma list to restrict validation matches")
    p.add_argument("--skip-market", action="store_true")
    p.add_argument("--out-prefix", type=str, default="reports/backtest_dc_report")
    args = p.parse_args()

    conn = afb_mysql_connect()
    min_date = args.min_date or str(settings_v2.afb_history_min_date)
    matches = load_matches(conn, min_date=min_date)
    print(f"[load] {len(matches)} finished matches (min_date={min_date})")
    if args.leagues:
        keep = {s.strip() for s in args.leagues.split(",") if s.strip()}
        matches = [m for m in matches if m["league"] in keep]
        print(f"[load] league filter -> {len(matches)}")

    report: dict = {"meta": {"min_date": min_date, "generated": datetime.utcnow().isoformat(timespec="seconds") + "Z"}}
    if args.mode in ("holdout", "both"):
        print("=== HOLDOUT ===")
        report["holdout"] = run_mode("holdout", matches, args, conn)
    if args.mode in ("walkforward", "both"):
        print("=== WALKFORWARD ===")
        report["walkforward"] = run_mode("walkforward", matches, args, conn)

    out_json = Path(REPO_ROOT) / (args.out_prefix + ".json")
    out_txt = Path(REPO_ROOT) / (args.out_prefix + ".txt")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    out_txt.write_text(render_txt(report), encoding="utf-8")
    print(f"[done] wrote {out_json}")
    print(f"[done] wrote {out_txt}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
