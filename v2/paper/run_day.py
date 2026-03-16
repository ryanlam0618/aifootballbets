from __future__ import annotations

import argparse
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


def _league_name_rank(matches: List[MatchInfo]) -> Dict[str, int]:
    # combined rank universe by league, but one global strategy pool
    order = {lk: i for i, lk in enumerate(LEAGUE_UNIVERSE)}
    return {m.match_id: order.get(m.league_key, 999) for m in matches}


def _synthetic_markets_for_match(match_id: str) -> Dict[Tuple[str, str, str], float]:
    # Synthetic odds used only when provider odds are unavailable.
    # Chosen to keep at least some positive-EV opportunities for dry-run selection.
    return {
        (match_id, "1X2", "Home"): 2.40,
        (match_id, "1X2", "Draw"): 3.60,
        (match_id, "1X2", "Away"): 2.40,
        (match_id, "Over/Under 2.5", "Over"): 2.20,
        (match_id, "Over/Under 2.5", "Under"): 2.20,
        (match_id, "Asian Handicap -0.5", "Home"): 2.35,
        (match_id, "Asian Handicap 0.5", "Away"): 2.35,
    }


def _with_results_only_odds(
    matches: List[MatchInfo],
    odds_map: Dict[Tuple[str, str, str], float],
    odds_meta: Dict[Tuple[str, str, str], Dict[str, Any]] | None = None,
) -> tuple[Dict[Tuple[str, str, str], float], Dict[Tuple[str, str, str], Dict[str, Any]], bool]:
    out = dict(odds_map)
    meta = dict(odds_meta or {})
    if not out:
        # Full results-only mode
        for m in matches:
            syn = _synthetic_markets_for_match(m.match_id)
            out.update(syn)
            for k in syn.keys():
                meta[k] = {"source": "synthetic", "is_real": False}
        return out, meta, True

    # Partial coverage mode: only patch matches with zero odds
    covered_match_ids = {mid for (mid, _market, _sel) in out.keys()}
    for m in matches:
        if m.match_id not in covered_match_ids:
            syn = _synthetic_markets_for_match(m.match_id)
            out.update(syn)
            for k in syn.keys():
                meta[k] = {"source": "synthetic", "is_real": False}

    for k in out.keys():
        meta.setdefault(k, {"source": "unknown", "is_real": True})

    return out, meta, False


def _key_for_candidate(c: CandidateBet) -> Tuple[str, str, str]:
    market_key = c.market if c.market == "1X2" else f"{c.market} {c.line}".strip()
    return (c.match_id, market_key, c.selection)


def run_for_day(
    day: date,
    db_path: Path,
    snapshot_db: Path,
    initial_bankroll: float,
    run_id: str,
    provider: OddsProvider | None = None,
) -> dict:
    provider = provider or OddsApiEspnPlaceholderProvider()

    matches = provider.fetch_matches(day=day, league_keys=LEAGUE_UNIVERSE)
    if not matches:
        return {
            "matches": 0,
            "candidates": 0,
            "selected": 0,
            "inserted": 0,
            "risk_stop": False,
            "results_only_mode": False,
        }

    odds_with_meta = getattr(provider, "fetch_market_odds_with_meta", None)
    if callable(odds_with_meta):
        odds_map_raw, odds_meta_raw = odds_with_meta(day=day, league_keys=LEAGUE_UNIVERSE, matches=matches)
    else:
        odds_map_raw = provider.fetch_market_odds(day=day, league_keys=LEAGUE_UNIVERSE, matches=matches)
        odds_meta_raw = {k: {"source": "unknown", "is_real": True} for k in odds_map_raw.keys()}

    odds_map, odds_meta, results_only_mode = _with_results_only_odds(matches, odds_map_raw, odds_meta_raw)

    all_candidates: List[CandidateBet] = []
    for m in matches:
        all_candidates.extend(generate_candidates_for_match(m, odds_map=odds_map))

    best_by_match = select_best_per_match(all_candidates)

    # When odds coverage is sparse, strict global cutoffs can produce no selections.
    # Fall back to per-match best positive-EV candidate so one-day pipeline still runs.
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
    max_bets_day = max(0, int(settings_v2.paper_max_bets_per_day))
    max_bets_league = max(0, int(settings_v2.paper_max_bets_per_league_per_day))

    for c in ranked:
        if not risk.can_place():
            break
        if max_bets_day and len(selected) >= max_bets_day:
            break
        if max_bets_league and league_counts[c.league_key] >= max_bets_league:
            continue

        meta = odds_meta.get(_key_for_candidate(c), {"source": "unknown", "is_real": True})
        source_quality = "real_odds" if bool(meta.get("is_real", True)) else "synthetic_odds"
        odds_source = str(meta.get("source", "unknown"))

        bet = make_selected_bet(
            c,
            sim_date=day,
            bankroll_before=bankroll_cursor,
            run_id=run_id,
            source_quality=source_quality,
            odds_source=odds_source,
        )
        if bet.stake <= 0:
            continue
        selected.append(bet)
        league_counts[c.league_key] += 1
        bankroll_cursor -= bet.stake

    inserted = append_selected_bets(db_path=db_path, bets=selected, source_book="paper_sim")

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
        "max_bets_per_day": max_bets_day,
        "max_bets_per_league_per_day": max_bets_league,
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
        help="optional local JSON fixture for deterministic mock provider",
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

    res = run_for_day(
        day=day,
        db_path=Path(args.sqlite),
        snapshot_db=Path(args.snapshot_db),
        initial_bankroll=settings_v2.initial_bankroll,
        run_id=run_id,
        provider=provider,
    )
    print(f"[OK] day={day.isoformat()} provider={args.odds_provider} -> {res}")


if __name__ == "__main__":
    main()
