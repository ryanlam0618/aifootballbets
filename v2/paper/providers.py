from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from v2.ingest.fixtures import Fixture
from v2.ingest.odds import collect_and_store_snapshot, current_market_snapshot
from v2.paper.constants import ESPN_LEAGUE_MAP, LEAGUE_UNIVERSE
from v2.paper.models import MatchInfo


class OddsProvider(ABC):
    @abstractmethod
    def fetch_matches(self, day: date, league_keys: List[str]) -> List[MatchInfo]:
        raise NotImplementedError

    @abstractmethod
    def fetch_market_odds(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Dict[Tuple[str, str, str], float]:
        raise NotImplementedError


class ResultsProvider(ABC):
    @abstractmethod
    def fetch_ft_scores(self, day: date, league_keys: List[str]) -> Dict[str, Tuple[int, int]]:
        """
        Returns dict key: normalized 'home|away' -> (home_goals, away_goals)
        Only finished/FT games should be returned.
        """
        raise NotImplementedError


def normalize_team(name: str) -> str:
    return " ".join((name or "").lower().replace("'", "").replace(".", " ").split())


def match_key(home: str, away: str) -> str:
    return f"{normalize_team(home)}|{normalize_team(away)}"


class OddsApiEspnPlaceholderProvider(OddsProvider):
    """
    Primary: The Odds API for fixtures+odds.
    Placeholder extension point: ESPN odds ingest can be added in this class later.
    """

    def __init__(self, snapshot_db: Path) -> None:
        self.snapshot_db = snapshot_db

    def fetch_matches(self, day: date, league_keys: List[str]) -> List[MatchInfo]:
        # Reuse existing The Odds API fixture resolver with synthetic fixture objects.
        fixtures = self._fetch_fixtures(league_keys)
        out: List[MatchInfo] = []
        for f in fixtures:
            out.append(
                MatchInfo(
                    match_id=f.match_id,
                    league_key=f.league_key,
                    league_name=f.league_name,
                    kickoff_utc=f.commence_time_utc,
                    home_team=f.home_team,
                    away_team=f.away_team,
                )
            )
        return out

    def fetch_market_odds(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Dict[Tuple[str, str, str], float]:
        import pandas as pd

        fixtures_df = pd.DataFrame(
            [
                {
                    "match_id": m.match_id,
                    "league_key": m.league_key,
                    "home_team": m.home_team,
                    "away_team": m.away_team,
                }
                for m in matches
            ]
        )
        collect_and_store_snapshot(league_keys, self.snapshot_db, fixtures_df=fixtures_df)
        return current_market_snapshot([m.match_id for m in matches], self.snapshot_db)

    def _fetch_fixtures(self, league_keys: List[str]) -> List[Fixture]:
        from v2.ingest.fixtures import _fetch_league_events  # existing internal util

        fixtures: List[Fixture] = []
        for lk in league_keys:
            events = _fetch_league_events(lk)
            for ev in events:
                fixtures.append(
                    Fixture(
                        match_id=str(ev.get("id", "")),
                        league_key=lk,
                        league_name=str(ev.get("sport_title", lk)),
                        match_date=str(ev.get("commence_time", ""))[:10],
                        match_time=str(ev.get("commence_time", ""))[11:16],
                        commence_time_utc=str(ev.get("commence_time", "")),
                        home_team=str(ev.get("home_team", "")),
                        away_team=str(ev.get("away_team", "")),
                        source="the_odds_api",
                    )
                )
        return fixtures


class EspnResultsProvider(ResultsProvider):
    def __init__(self, timeout: int = 25) -> None:
        self.timeout = timeout

    def fetch_ft_scores(self, day: date, league_keys: List[str]) -> Dict[str, Tuple[int, int]]:
        out: Dict[str, Tuple[int, int]] = {}
        ymd = day.strftime("%Y%m%d")

        for lk in league_keys:
            sport_league = ESPN_LEAGUE_MAP.get(lk)
            if not sport_league:
                continue
            sport, league = sport_league
            url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
            params = {"dates": ymd}
            try:
                r = requests.get(url, params=params, timeout=self.timeout)
                if r.status_code != 200:
                    continue
                data = r.json()
            except Exception:
                continue

            for ev in (data.get("events") or []):
                comp = ((ev.get("competitions") or [{}])[0]) or {}
                status = ((comp.get("status") or {}).get("type") or {})
                state = str(status.get("state", "")).lower()
                completed = bool(status.get("completed", False))
                if not (completed or state == "post"):
                    continue

                competitors = comp.get("competitors") or []
                home = None
                away = None
                for c in competitors:
                    team = (c.get("team") or {}).get("displayName", "")
                    score = c.get("score")
                    try:
                        score_i = int(score)
                    except Exception:
                        score_i = None
                    if str(c.get("homeAway", "")).lower() == "home":
                        home = (team, score_i)
                    elif str(c.get("homeAway", "")).lower() == "away":
                        away = (team, score_i)

                if not home or not away:
                    continue
                if home[1] is None or away[1] is None:
                    continue
                out[match_key(home[0], away[0])] = (home[1], away[1])

        return out


class Pp88OddsProviderStub(OddsProvider):
    """
    Stub provider for future browser automation integration.
    """

    def fetch_matches(self, day: date, league_keys: List[str]) -> List[MatchInfo]:
        return []

    def fetch_market_odds(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Dict[Tuple[str, str, str], float]:
        return {}


DEFAULT_LEAGUES = LEAGUE_UNIVERSE
