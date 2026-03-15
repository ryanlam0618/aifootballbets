from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Tuple

from v2.config import settings_v2
from v2.paper.constants import LEAGUE_UNIVERSE
from v2.paper.ledger import bankroll_before_day, open_unsettled_bets_for_day, settle_bet
from v2.paper.providers import EspnResultsProvider, match_key


def _resolve_profit(row, score: Tuple[int, int]) -> Tuple[str, float]:
    home_goals, away_goals = score
    market = str(row["market"] or "")
    selection = str(row["selection"] or "")
    odds = float(row["odds_bet"] or 0)
    stake = float(row["stake"] or 0)
    line_raw = row["line"]

    # Conservative settlement for quarter lines: treat as full-line approximation.
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
        total = home_goals + away_goals
        if selection == "Over":
            if total > target:
                return "win", win_profit()
            if total == target:
                return "push", 0.0
            return "loss", -stake
        else:
            if total < target:
                return "win", win_profit()
            if total == target:
                return "push", 0.0
            return "loss", -stake

    if market.startswith("Asian Handicap"):
        target = float(line if line is not None else 0.0)
        diff = home_goals - away_goals
        if selection == "Home":
            adj = diff + target
        else:
            adj = (-diff) - target
        if adj > 0:
            return "win", win_profit()
        if adj == 0:
            return "push", 0.0
        return "loss", -stake

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
