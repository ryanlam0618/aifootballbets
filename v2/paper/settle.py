from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from typing import List, Tuple

from v2.config import settings_v2
from v2.paper.closing_odds import load_tracker_closing_odds_by_bet_id
from v2.paper.constants import LEAGUE_UNIVERSE
from v2.paper.clv import compute_clv
from v2.paper.ledger import bankroll_before_day, open_unsettled_bets_for_day, settle_bet
from v2.paper.models import MatchInfo
from v2.paper.providers import (
    JsonFileResultsProvider,
    ResultsProvider,
    SofaScoreFixturesResultsProvider,
    match_key,
)

_EPS = 1e-9


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= _EPS


def _split_quarter_line(line: float) -> List[float]:
    """
    Asian quarter line decomposition:
    x.25 -> [x.0, x.5]
    x.75 -> [x.5, x.0+1]
    same for negatives via +/- 0.25
    """
    frac = abs(line - math_floor(line))
    if _close(frac, 0.25) or _close(frac, 0.75):
        a = round(line - 0.25, 2)
        b = round(line + 0.25, 2)
        return [a, b]
    return [line]


def math_floor(x: float) -> float:
    import math

    return float(math.floor(x))


def _single_ah_profit(stake: float, odds: float, home_goals: int, away_goals: int, selection: str, line: float) -> Tuple[str, float]:
    diff = home_goals - away_goals
    base = diff if selection == "Home" else -diff
    adj = base + line
    if adj > _EPS:
        return "win", stake * (odds - 1.0)
    if _close(adj, 0.0):
        return "push", 0.0
    return "loss", -stake


def _single_ou_profit(stake: float, odds: float, total_goals: int, selection: str, line: float) -> Tuple[str, float]:
    if selection == "Over":
        val = total_goals - line
    else:
        val = line - total_goals

    if val > _EPS:
        return "win", stake * (odds - 1.0)
    if _close(val, 0.0):
        return "push", 0.0
    return "loss", -stake


def _aggregate_half_results(results: List[Tuple[str, float]]) -> Tuple[str, float]:
    profit = sum(p for _, p in results)
    labels = [r for r, _ in results]

    if all(r == "win" for r in labels):
        return "win", profit
    if all(r == "loss" for r in labels):
        return "loss", profit
    if all(r == "push" for r in labels):
        return "push", profit

    if "win" in labels and "push" in labels:
        return "half_win", profit
    if "loss" in labels and "push" in labels:
        return "half_loss", profit
    if "win" in labels and "loss" in labels:
        # rare edge case with malformed mixed split; keep neutral wording
        return "split", profit

    return "void", profit


def _normalize_market(market: str) -> str:
    raw = str(market or "").strip().lower()
    compact = "".join(ch for ch in raw if ch.isalnum())

    if raw in {"ou", "o/u", "over_under", "over-under"} or compact in {"ou", "overunder"}:
        return "Over/Under"
    if raw in {"ah", "asian", "asian handicap", "asian_handicap"} or compact in {"ah", "asianhandicap"}:
        return "Asian Handicap"
    if raw in {"1x2", "hda", "moneyline"} or compact in {"1x2", "hda", "moneyline"}:
        return "1X2"

    if compact.startswith("overunder"):
        return "Over/Under"
    if compact.startswith("asianhandicap"):
        return "Asian Handicap"

    return str(market or "")


def _normalize_selection(market: str, selection: str) -> str:
    s = str(selection or "").strip().lower()
    m = _normalize_market(market)
    if m == "1X2":
        if s in {"h", "home", "1"} or s.startswith("home"):
            return "Home"
        if s in {"a", "away", "2"} or s.startswith("away"):
            return "Away"
        if s in {"d", "draw", "x"} or s.startswith("draw"):
            return "Draw"
        return str(selection or "")
    if m == "Over/Under":
        if s in {"o", "over"} or s.startswith("over"):
            return "Over"
        if s in {"u", "under"} or s.startswith("under"):
            return "Under"
        return str(selection or "")
    if m == "Asian Handicap":
        if s in {"h", "home", "1"} or s.startswith("home"):
            return "Home"
        if s in {"a", "away", "2"} or s.startswith("away"):
            return "Away"
        return str(selection or "")
    return str(selection or "")


def _resolve_profit(row, score: Tuple[int, int]) -> Tuple[str, float]:
    home_goals, away_goals = score
    market = _normalize_market(str(row["market"] or ""))
    selection = _normalize_selection(market, str(row["selection"] or ""))
    odds = float(row["odds_bet"] or 0)
    stake = float(row["stake"] or 0)
    line_raw = row["line"]

    line = None
    try:
        if line_raw is not None and str(line_raw).strip() != "":
            line = float(line_raw)
    except Exception:
        line = None

    def win_profit() -> float:
        return stake * (odds - 1.0)

    if market == "1X2":
        if selection == "Home":
            won = home_goals > away_goals
        elif selection == "Away":
            won = away_goals > home_goals
        else:
            won = home_goals == away_goals
        return ("win", win_profit()) if won else ("loss", -stake)

    if market.startswith("Over/Under"):
        target = float(line if line is not None else 2.5)
        splits = _split_quarter_line(target)
        half_stake = stake / len(splits)
        total = home_goals + away_goals
        results = [_single_ou_profit(half_stake, odds, total, selection, s) for s in splits]
        return _aggregate_half_results(results)

    if market.startswith("Asian Handicap"):
        target = float(line if line is not None else 0.0)
        splits = _split_quarter_line(target)
        half_stake = stake / len(splits)
        results = [
            _single_ah_profit(half_stake, odds, home_goals, away_goals, selection, s)
            for s in splits
        ]
        return _aggregate_half_results(results)

    return "void", 0.0


def _scores_with_ids(provider: ResultsProvider, day: date, league_keys: List[str]) -> Tuple[dict, dict]:
    fetch_with_ids = getattr(provider, "fetch_ft_scores_with_ids", None)
    if callable(fetch_with_ids):
        try:
            names, ids = fetch_with_ids(day=day, league_keys=league_keys)
            if isinstance(names, dict) and isinstance(ids, dict):
                return names, ids
        except Exception:
            pass
    names = provider.fetch_ft_scores(day=day, league_keys=league_keys) or {}
    return names, {}


def _build_match_from_row(row) -> MatchInfo | None:
    notes = str(row["notes"] or "")
    match_id = ""
    if "match_id=" in notes:
        try:
            fragment = notes.split("match_id=", 1)[1]
            match_id = fragment.split()[0].strip().strip(",")
        except Exception:
            match_id = ""

    home = str(row["home"] or "").strip()
    away = str(row["away"] or "").strip()
    kickoff = str(row["kickoff_time_hkt"] or "").strip()
    if not (match_id and home and away):
        return None

    lk = match_id.split(":", 1)[0] if ":" in match_id else ""
    return MatchInfo(
        match_id=match_id,
        league_key=lk,
        league_name=str(row["league"] or lk),
        kickoff_utc=kickoff,
        home_team=home,
        away_team=away,
    )


def _fetch_closing_odds_map(day: date, unsettled_rows: list, league_keys: List[str]) -> dict:
    matches = []
    seen = set()
    for row in unsettled_rows:
        m = _build_match_from_row(row)
        if not m or m.match_id in seen:
            continue
        matches.append(m)
        seen.add(m.match_id)

    if not matches:
        return {}

    odds_provider = SofaScoreFixturesResultsProvider()
    fetch_meta = getattr(odds_provider, "fetch_market_odds_with_meta", None)
    if not callable(fetch_meta):
        return {}
    odds_map, _meta = fetch_meta(day=day, league_keys=league_keys, matches=matches)
    return odds_map or {}


def run_settlement(
    db_path: Path,
    day: date,
    provider: ResultsProvider | None = None,
    closing_odds_tracker_sqlite: Path | None = None,
) -> int:
    provider = provider or SofaScoreFixturesResultsProvider()
    score_map, score_map_ids = _scores_with_ids(provider=provider, day=day, league_keys=LEAGUE_UNIVERSE)

    unsettled = open_unsettled_bets_for_day(db_path, day)
    if not unsettled:
        return 0

    close_odds_map = _fetch_closing_odds_map(day=day, unsettled_rows=unsettled, league_keys=LEAGUE_UNIVERSE)

    tracker_map = {}
    tracker_db = closing_odds_tracker_sqlite
    if tracker_db is None and str(settings_v2.paper_closing_odds_tracker_sqlite).strip():
        tracker_db = Path(settings_v2.paper_closing_odds_tracker_sqlite)
    if tracker_db is not None:
        tracker_map = load_tracker_closing_odds_by_bet_id(Path(tracker_db), unsettled)

    bankroll = bankroll_before_day(db_path, day, settings_v2.initial_bankroll)
    settled_count = 0

    for row in unsettled:
        mid = str(row["bet_id"] or "")
        # bet_id is hashed and not usable as event id; recover from notes if needed in future.
        _ = mid

        row_match_id = str(row["notes"] or "")
        score = None
        candidate_id = ""

        # Preferred: by match_id stored in notes (if present with match_id=...)
        if "match_id=" in row_match_id:
            try:
                fragment = row_match_id.split("match_id=", 1)[1]
                candidate_id = fragment.split()[0].strip().strip(",")
                if candidate_id:
                    score = score_map_ids.get(candidate_id)
            except Exception:
                score = None

        # Fallback: by normalized home/away names
        if not score:
            k = match_key(str(row["home"]), str(row["away"]))
            score = score_map.get(k)
        if not score:
            continue

        result, profit = _resolve_profit(row, score)
        bankroll = bankroll + float(profit)

        odds_close = None
        clv_abs = None
        clv_pct = None
        close_odds_source = None

        # 1) Prefer tracker-derived closing odds hook (OddsPortal snapshots), keyed by bet_id.
        tracker_close = tracker_map.get(str(row["bet_id"]))
        if tracker_close is not None:
            try:
                odds_close = float(tracker_close)
                odds_bet = float(row["odds_bet"] or 0.0)
                clv_abs, clv_pct = compute_clv(odds_bet=odds_bet, odds_close=odds_close)
                close_odds_source = "tracker"
            except Exception:
                odds_close = None
                clv_abs = None
                clv_pct = None
                close_odds_source = None

        # 2) Fallback to provider-based close odds map.
        if odds_close is None and candidate_id:
            market = str(row["market"] or "")
            line = str(row["line"] or "").strip()
            selection = str(row["selection"] or "")
            market_key = market if market == "1X2" else f"{market} {line}".strip()
            k_close = (candidate_id, market_key, selection)
            oc = close_odds_map.get(k_close)
            if oc is not None:
                try:
                    odds_close = float(oc)
                    odds_bet = float(row["odds_bet"] or 0.0)
                    clv_abs, clv_pct = compute_clv(odds_bet=odds_bet, odds_close=odds_close)
                    close_odds_source = "provider"
                except Exception:
                    odds_close = None
                    clv_abs = None
                    clv_pct = None
                    close_odds_source = None

        settle_bet(
            db_path,
            str(row["bet_id"]),
            result,
            float(profit),
            bankroll,
            odds_close=odds_close,
            clv_abs=clv_abs,
            clv_pct=clv_pct,
            close_odds_source=close_odds_source,
        )
        settled_count += 1

    return settled_count


def _build_results_provider(name: str | None, provider_json: str | None = None) -> ResultsProvider:
    pjson = str(provider_json or "").strip()
    if pjson:
        return JsonFileResultsProvider(Path(pjson))

    provider_name = str(name or "sofascore").strip().lower()
    if provider_name == "sofascore":
        return SofaScoreFixturesResultsProvider()
    raise ValueError(f"Unsupported results provider: {provider_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Settle paper bets for a day using results provider")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--sqlite",
        default=str(Path(settings_v2.tracking_sqlite_path)),
        help="tracking sqlite path",
    )
    parser.add_argument(
        "--results-provider",
        choices=["sofascore"],
        default="sofascore",
        help="results provider to use (default: sofascore)",
    )
    parser.add_argument(
        "--provider-json",
        default="",
        help="optional local JSON fixture for deterministic settlement results",
    )
    parser.add_argument(
        "--closing-odds-tracker-sqlite",
        default="",
        help="optional OddsPortal tracker sqlite for closing-odds hook",
    )
    args = parser.parse_args()

    day = datetime.strptime(args.date, "%Y-%m-%d").date()
    provider = _build_results_provider(args.results_provider, provider_json=args.provider_json)
    n = run_settlement(
        Path(args.sqlite),
        day,
        provider=provider,
        closing_odds_tracker_sqlite=(Path(args.closing_odds_tracker_sqlite) if str(args.closing_odds_tracker_sqlite).strip() else None),
    )
    print(f"[OK] settled rows: {n} (provider={args.results_provider})")


if __name__ == "__main__":
    main()
