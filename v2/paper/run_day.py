from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from v2.config import settings_v2
from v2.paper.constants import LEAGUE_UNIVERSE
from v2.paper.ledger import append_selected_bets, bankroll_before_day
from v2.paper.models import CandidateBet, MatchInfo
from v2.paper.providers import (
    JsonFileOddsProvider,
    OddsApiEspnPlaceholderProvider,
    OddsProvider,
    SofaScoreFixturesResultsProvider,
)
from v2.paper.staking import DailyRiskManager, make_selected_bet
from v2.paper.strategy import generate_candidates_for_match, select_best_per_match


def _synthetic_markets_for_match(match_id: str) -> Dict[Tuple[str, str, str], float]:
    # Synthetic odds used only when explicitly allowed.
    return {
        (match_id, "1X2", "Home"): 2.40,
        (match_id, "1X2", "Draw"): 3.60,
        (match_id, "1X2", "Away"): 2.40,
        (match_id, "Over/Under 2.5", "Over"): 2.20,
        (match_id, "Over/Under 2.5", "Under"): 2.20,
        (match_id, "Asian Handicap -0.5", "Home"): 2.35,
        (match_id, "Asian Handicap 0.5", "Away"): 2.35,
    }


def _with_optional_synthetic_odds(
    matches: List[MatchInfo],
    odds_map: Dict[Tuple[str, str, str], float],
    odds_meta: Dict[Tuple[str, str, str], Dict[str, Any]] | None = None,
    allow_synthetic: bool = False,
) -> tuple[
    Dict[Tuple[str, str, str], float],
    Dict[Tuple[str, str, str], Dict[str, Any]],
    bool,
    int,
]:
    out = dict(odds_map)
    meta = dict(odds_meta or {})
    synthetic_added = 0

    if not allow_synthetic:
        for k in out.keys():
            meta.setdefault(k, {"source": "unknown", "is_real": True})
        return out, meta, False, synthetic_added

    if not out:
        # Full results-only mode (explicitly enabled)
        for m in matches:
            syn = _synthetic_markets_for_match(m.match_id)
            out.update(syn)
            synthetic_added += len(syn)
            for k in syn.keys():
                meta[k] = {"source": "synthetic", "is_real": False}
        return out, meta, True, synthetic_added

    # Partial coverage mode: only patch matches with zero odds
    covered_match_ids = {mid for (mid, _market, _sel) in out.keys()}
    for m in matches:
        if m.match_id not in covered_match_ids:
            syn = _synthetic_markets_for_match(m.match_id)
            out.update(syn)
            synthetic_added += len(syn)
            for k in syn.keys():
                meta[k] = {"source": "synthetic", "is_real": False}

    for k in out.keys():
        meta.setdefault(k, {"source": "unknown", "is_real": True})

    return out, meta, False, synthetic_added


def _key_for_candidate(c: CandidateBet) -> Tuple[str, str, str]:
    market_key = c.market if c.market == "1X2" else f"{c.market} {c.line}".strip()
    return (c.match_id, market_key, c.selection)


def _decision_payload(c: CandidateBet, odds_source: str, source_quality: str) -> dict:
    return {
        "match_id": c.match_id,
        "match": f"{c.home_team} vs {c.away_team}",
        "league_key": c.league_key,
        "market": c.market,
        "line": c.line,
        "selection": c.selection,
        "odds": c.odds,
        "odds_source": odds_source,
        "source_quality": source_quality,
        "model_prob": c.model_probability,
        "edge": c.edge,
    }


def run_for_day(
    day: date,
    db_path: Path,
    snapshot_db: Path,
    initial_bankroll: float,
    run_id: str,
    provider: OddsProvider | None = None,
    allow_synthetic_odds: bool | None = None,
    decision_log_path: Path | None = None,
) -> dict:
    _ = snapshot_db  # reserved for future optional snapshot integration
    provider = provider or OddsApiEspnPlaceholderProvider()
    allow_synthetic = settings_v2.paper_allow_synthetic_odds if allow_synthetic_odds is None else bool(allow_synthetic_odds)

    matches = provider.fetch_matches(day=day, league_keys=LEAGUE_UNIVERSE)
    if not matches:
        return {
            "matches": 0,
            "candidates": 0,
            "selected": 0,
            "inserted": 0,
            "risk_stop": False,
            "results_only_mode": False,
            "allow_synthetic_odds": allow_synthetic,
            "decision_log_path": str(decision_log_path) if decision_log_path else "",
        }

    odds_with_meta = getattr(provider, "fetch_market_odds_with_meta", None)
    if callable(odds_with_meta):
        odds_map_raw, odds_meta_raw = odds_with_meta(day=day, league_keys=LEAGUE_UNIVERSE, matches=matches)
    else:
        odds_map_raw = provider.fetch_market_odds(day=day, league_keys=LEAGUE_UNIVERSE, matches=matches)
        odds_meta_raw = {k: {"source": "unknown", "is_real": True} for k in odds_map_raw.keys()}

    odds_map, odds_meta, results_only_mode, synthetic_added = _with_optional_synthetic_odds(
        matches,
        odds_map_raw,
        odds_meta_raw,
        allow_synthetic=allow_synthetic,
    )

    all_candidates: List[CandidateBet] = []
    for m in matches:
        all_candidates.extend(generate_candidates_for_match(m, odds_map=odds_map))

    best_by_match = select_best_per_match(all_candidates)

    # Sparse coverage fallback: keep one positive-EV candidate per match (still filtered by constraints later).
    if not best_by_match and all_candidates:
        by_match: Dict[str, CandidateBet] = {}
        for c in all_candidates:
            if c.ev <= 0:
                continue
            old = by_match.get(c.match_id)
            if old is None or (c.expected_log_growth, c.ev, c.edge) > (old.expected_log_growth, old.ev, old.edge):
                by_match[c.match_id] = c
        best_by_match = by_match

    # combined ranking across all leagues by expected_log_growth then edge
    ranked = sorted(
        best_by_match.values(),
        key=lambda x: (x.expected_log_growth, x.edge),
        reverse=True,
    )

    day_start = bankroll_before_day(db_path, day, initial_bankroll)
    risk = DailyRiskManager(day_start_bankroll=day_start, stop_loss_pct=0.20)

    # guard using already-settled same-day pnl if rerun mid-day
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        r = conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN profit IS NULL THEN 0 ELSE profit END), 0)
            FROM bet_log
            WHERE substr(kickoff_time_hkt, 1, 10) = ?
            """,
            (day.isoformat(),),
        ).fetchone()
        day_pnl_now = float(r[0] or 0.0)
    finally:
        conn.close()

    if day_pnl_now <= (-0.20 * day_start):
        risk.state.stop_triggered = True

    selected = []
    bankroll_cursor = day_start
    league_counts: Dict[str, int] = defaultdict(int)
    league_stake: Dict[str, float] = defaultdict(float)
    max_bets_day = max(0, int(settings_v2.paper_max_bets_per_day))
    max_bets_league = max(0, int(settings_v2.paper_max_bets_per_league_per_day))
    max_league_exposure_frac = max(0.0, float(settings_v2.paper_max_league_exposure_fraction_per_day))

    decision_rows: List[dict] = []
    for c in ranked:
        meta = odds_meta.get(_key_for_candidate(c), {"source": "unknown", "is_real": True})
        source_quality = "real_odds" if bool(meta.get("is_real", True)) else "synthetic_odds"
        odds_source = str(meta.get("source", "unknown"))
        payload = _decision_payload(c, odds_source=odds_source, source_quality=source_quality)

        rejection_reasons: List[str] = []
        if not risk.can_place():
            rejection_reasons.append("daily_drawdown_stop")
        if max_bets_day and len(selected) >= max_bets_day:
            rejection_reasons.append("max_bets_per_day")
        if max_bets_league and league_counts[c.league_key] >= max_bets_league:
            rejection_reasons.append("max_bets_per_league_per_day")
        if source_quality == "synthetic_odds" and not allow_synthetic:
            rejection_reasons.append("synthetic_odds_not_allowed")

        if rejection_reasons:
            payload.update({"decision": "rejected", "constraints_triggered": "|".join(rejection_reasons), "kelly_stake": 0.0})
            decision_rows.append(payload)
            continue

        bet = make_selected_bet(
            c,
            sim_date=day,
            bankroll_before=bankroll_cursor,
            run_id=run_id,
            source_quality=source_quality,
            odds_source=odds_source,
            constraints_triggered="",
        )
        if bet.stake <= 0:
            payload.update({"decision": "rejected", "constraints_triggered": "non_positive_stake", "kelly_stake": 0.0})
            decision_rows.append(payload)
            continue

        constraint_hits: List[str] = []
        max_stake_frac = max(0.0, float(settings_v2.paper_max_stake_fraction_per_bet))
        if max_stake_frac > 0 and day_start > 0 and (bet.stake / day_start) >= (max_stake_frac - 1e-12):
            constraint_hits.append("max_stake_fraction_per_bet")

        if max_league_exposure_frac > 0 and day_start > 0:
            current = league_stake[c.league_key]
            cap = day_start * max_league_exposure_frac
            if (current + bet.stake) > (cap + 1e-9):
                payload.update(
                    {
                        "decision": "rejected",
                        "constraints_triggered": "league_exposure_cap",
                        "kelly_stake": 0.0,
                    }
                )
                decision_rows.append(payload)
                continue
            if (current + bet.stake) >= (cap - 1e-12):
                constraint_hits.append("league_exposure_cap_reached")

        bet.constraints_triggered = "|".join(constraint_hits)
        selected.append(bet)
        league_counts[c.league_key] += 1
        league_stake[c.league_key] += bet.stake
        bankroll_cursor -= bet.stake

        payload.update(
            {
                "decision": "selected",
                "constraints_triggered": bet.constraints_triggered,
                "kelly_stake": bet.stake,
            }
        )
        decision_rows.append(payload)

    inserted = append_selected_bets(db_path=db_path, bets=selected, source_book="paper_sim")

    if decision_log_path:
        decision_log_path.parent.mkdir(parents=True, exist_ok=True)
        with decision_log_path.open("w", encoding="utf-8") as f:
            for row in decision_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    real_selected = sum(1 for b in selected if b.source_quality == "real_odds")
    synthetic_selected = sum(1 for b in selected if b.source_quality == "synthetic_odds")

    return {
        "matches": len(matches),
        "candidates": len(all_candidates),
        "selected": len(selected),
        "inserted": inserted,
        "risk_stop": risk.state.stop_triggered,
        "day_start_bankroll": day_start,
        "results_only_mode": results_only_mode,
        "selected_real_odds": real_selected,
        "selected_synthetic_odds": synthetic_selected,
        "synthetic_added_markets": synthetic_added,
        "allow_synthetic_odds": allow_synthetic,
        "max_bets_per_day": max_bets_day,
        "max_bets_per_league_per_day": max_bets_league,
        "max_league_exposure_fraction_per_day": max_league_exposure_frac,
        "max_stake_fraction_per_bet": float(settings_v2.paper_max_stake_fraction_per_bet),
        "decision_log_path": str(decision_log_path) if decision_log_path else "",
    }


def _build_odds_provider(name: str | None, provider_json: str | None) -> OddsProvider | None:
    pjson = str(provider_json or "").strip()
    if pjson:
        return JsonFileOddsProvider(Path(pjson))

    pname = str(name or "espn").strip().lower()
    if pname == "sofascore":
        return SofaScoreFixturesResultsProvider()
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one-day paper bet selection and append to tracking sqlite")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--sqlite",
        default=str(Path(settings_v2.tracking_sqlite_path)),
        help="tracking sqlite path",
    )
    parser.add_argument(
        "--snapshot-db",
        default="data/v2/odds_snapshots.sqlite",
        help="odds snapshot sqlite path",
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--provider-json",
        default="",
        help="optional local JSON fixture for deterministic mock provider (fixtures+odds)",
    )
    parser.add_argument(
        "--allow-synthetic-odds",
        action="store_true",
        help="allow synthetic odds fallback when real odds are missing (default: disabled)",
    )
    parser.add_argument(
        "--decision-log",
        default="",
        help="optional output JSONL path for per-candidate decision logs",
    )
    parser.add_argument(
        "--odds-provider",
        choices=["espn", "sofascore"],
        default="espn",
        help="fixtures/odds provider (default: espn; fallback chain inside espn: ESPN -> SofaScore -> Odds API)",
    )
    args = parser.parse_args()

    day = datetime.strptime(args.date, "%Y-%m-%d").date()
    run_id = args.run_id or f"paper_day_{day.isoformat()}"

    provider = _build_odds_provider(args.odds_provider, args.provider_json)

    decision_log_path = Path(args.decision_log) if str(args.decision_log).strip() else None

    res = run_for_day(
        day=day,
        db_path=Path(args.sqlite),
        snapshot_db=Path(args.snapshot_db),
        initial_bankroll=settings_v2.initial_bankroll,
        run_id=run_id,
        provider=provider,
        allow_synthetic_odds=args.allow_synthetic_odds,
        decision_log_path=decision_log_path,
    )
    print(f"[OK] day={day.isoformat()} provider={args.odds_provider} -> {res}")


if __name__ == "__main__":
    main()
