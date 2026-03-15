from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from typing import List, Tuple

from v2.config import settings_v2
from v2.paper.constants import LEAGUE_UNIVERSE
from v2.paper.ledger import bankroll_before_day, open_unsettled_bets_for_day, settle_bet
from v2.paper.providers import EspnResultsProvider, match_key

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


def _resolve_profit(row, score: Tuple[int, int]) -> Tuple[str, float]:
    home_goals, away_goals = score
    market = str(row["market"] or "")
    selection = str(row["selection"] or "")
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


def run_settlement(db_path: Path, day: date) -> int:
    provider = EspnResultsProvider()
    score_map = provider.fetch_ft_scores(day=day, league_keys=LEAGUE_UNIVERSE)

    unsettled = open_unsettled_bets_for_day(db_path, day)
    if not unsettled:
        return 0

    bankroll = bankroll_before_day(db_path, day, settings_v2.initial_bankroll)
    settled_count = 0

    for row in unsettled:
        k = match_key(str(row["home"]), str(row["away"]))
        score = score_map.get(k)
        if not score:
            continue

        result, profit = _resolve_profit(row, score)
        bankroll = bankroll + float(profit)
        settle_bet(db_path, str(row["bet_id"]), result, float(profit), bankroll)
        settled_count += 1

    return settled_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Settle paper bets for a day using ESPN results")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--sqlite",
        default=str(Path(settings_v2.tracking_sqlite_path)),
        help="tracking sqlite path",
    )
    args = parser.parse_args()

    day = datetime.strptime(args.date, "%Y-%m-%d").date()
    n = run_settlement(Path(args.sqlite), day)
    print(f"[OK] settled rows: {n}")


if __name__ == "__main__":
    main()
