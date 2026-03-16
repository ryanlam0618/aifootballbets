from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from v2.config import settings_v2
from v2.paper.models import CandidateBet, SelectedBet
from v2.paper.strategy import kelly_full

HKT = timezone(timedelta(hours=8))


@dataclass
class DailyRiskState:
    starting_bankroll: float
    bankroll: float
    pnl: float
    stop_triggered: bool


class DailyRiskManager:
    """
    Stop placing new bets when cumulative day pnl <= -20% of day start bankroll.
    """

    def __init__(self, day_start_bankroll: float, stop_loss_pct: float = 0.20) -> None:
        self.state = DailyRiskState(
            starting_bankroll=day_start_bankroll,
            bankroll=day_start_bankroll,
            pnl=0.0,
            stop_triggered=False,
        )
        self.stop_loss_pct = stop_loss_pct

    def can_place(self) -> bool:
        return not self.state.stop_triggered

    def register_settlement(self, profit: float) -> None:
        self.state.pnl += float(profit)
        self.state.bankroll += float(profit)
        if self.state.pnl <= (-self.stop_loss_pct * self.state.starting_bankroll):
            self.state.stop_triggered = True


def make_selected_bet(
    candidate: CandidateBet,
    sim_date,
    bankroll_before: float,
    run_id: str,
    kelly_fraction: Optional[float] = None,
    source_quality: str = "real_odds",
    odds_source: str = "unknown",
) -> SelectedBet:
    k_frac = settings_v2.kelly_fraction if kelly_fraction is None else kelly_fraction
    k_full = kelly_full(candidate.model_probability, candidate.odds)
    k_used = max(0.0, k_full * k_frac)
    stake = bankroll_before * k_used

    material = "|".join(
        [
            str(sim_date),
            candidate.match_id,
            candidate.market,
            candidate.line,
            candidate.selection,
            f"{candidate.odds:.6f}",
            run_id,
        ]
    )
    import hashlib

    bet_id = hashlib.sha1(material.encode("utf-8")).hexdigest()[:16]

    return SelectedBet(
        bet_id=bet_id,
        sim_date=sim_date,
        match_id=candidate.match_id,
        league_key=candidate.league_key,
        league_name=candidate.league_name,
        kickoff_utc=candidate.kickoff_utc,
        home_team=candidate.home_team,
        away_team=candidate.away_team,
        market=candidate.market,
        line=candidate.line,
        selection=candidate.selection,
        odds=candidate.odds,
        model_probability=candidate.model_probability,
        implied_probability=candidate.implied_probability,
        edge=candidate.edge,
        ev=candidate.ev,
        kelly_full=k_full,
        kelly_used=k_used,
        stake=stake,
        bankroll_before=bankroll_before,
        run_id=run_id,
        source_quality=source_quality,
        odds_source=odds_source,
    )


def utc_to_hkt_iso(iso_utc: str) -> str:
    dt = datetime.fromisoformat(str(iso_utc).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(HKT).replace(microsecond=0).isoformat(timespec="seconds")


def market_type(market: str) -> str:
    s = (market or "").strip().lower()
    if s == "1x2":
        return "1X2"
    if s.startswith("over/under"):
        return "Over/Under"
    if s.startswith("asian handicap"):
        return "Asian Handicap"
    return market
