from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class MatchInfo:
    match_id: str
    league_key: str
    league_name: str
    kickoff_utc: str
    home_team: str
    away_team: str


@dataclass
class CandidateBet:
    match_id: str
    league_key: str
    league_name: str
    kickoff_utc: str
    home_team: str
    away_team: str
    market: str
    line: str
    selection: str
    odds: float
    model_probability: float
    implied_probability: float
    edge: float
    ev: float
    expected_log_growth: float


@dataclass
class SelectedBet:
    bet_id: str
    sim_date: date
    match_id: str
    league_key: str
    league_name: str
    kickoff_utc: str
    home_team: str
    away_team: str
    market: str
    line: str
    selection: str
    odds: float
    model_probability: float
    implied_probability: float
    edge: float
    ev: float
    kelly_full: float
    kelly_used: float
    stake: float
    bankroll_before: float
    run_id: str


@dataclass
class SettledBet:
    bet_id: str
    result: str
    profit: float
    bankroll_after: Optional[float]
