from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from v2.config import settings_v2
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


def _http_get_json(url: str, params: Dict[str, str] | None = None, timeout: int = 25):
    q = urlencode(params or {})
    full_url = f"{url}?{q}" if q else url
    req = Request(full_url, headers={"User-Agent": "aifootballbets-paper/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", 200)
        if status != 200:
            return None
        body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body)


def normalize_team(name: str) -> str:
    return " ".join((name or "").lower().replace("'", "").replace(".", " ").split())


def match_key(home: str, away: str) -> str:
    return f"{normalize_team(home)}|{normalize_team(away)}"


class OddsApiEspnPlaceholderProvider(OddsProvider):
    """
    Stdlib-only provider:
    - Match/odds source: The Odds API
    - Keeps same interface but avoids pandas/requests dependencies
    """

    def __init__(self, snapshot_db: Path | None = None) -> None:
        self.snapshot_db = snapshot_db

    def fetch_matches(self, day: date, league_keys: List[str]) -> List[MatchInfo]:
        fixtures = self._fetch_fixtures(league_keys)
        out: List[MatchInfo] = []
        for ev in fixtures:
            out.append(
                MatchInfo(
                    match_id=str(ev.get("id", "")),
                    league_key=str(ev.get("league_key", "")),
                    league_name=str(ev.get("sport_title", ev.get("league_key", ""))),
                    kickoff_utc=str(ev.get("commence_time", "")),
                    home_team=str(ev.get("home_team", "")),
                    away_team=str(ev.get("away_team", "")),
                )
            )
        return [m for m in out if m.match_id and m.home_team and m.away_team]

    def fetch_market_odds(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Dict[Tuple[str, str, str], float]:
        match_ids = {m.match_id for m in matches}
        sums: Dict[Tuple[str, str, str], float] = {}
        counts: Dict[Tuple[str, str, str], int] = {}

        for lk in league_keys:
            events = self._fetch_league_events(lk)
            for ev in events:
                mid = str(ev.get("id", ""))
                if mid not in match_ids:
                    continue
                home = str(ev.get("home_team", ""))
                away = str(ev.get("away_team", ""))

                for bk in (ev.get("bookmakers") or []):
                    for mk in (bk.get("markets") or []):
                        mkey = str(mk.get("key", ""))
                        for out in (mk.get("outcomes") or []):
                            selection = str(out.get("name", ""))
                            point = out.get("point")
                            line_str = "" if point is None else str(point)
                            try:
                                odd = float(out.get("price"))
                            except Exception:
                                continue

                            market_key = ""
                            if mkey == "h2h":
                                market_key = "1X2"
                                if selection == home:
                                    selection = "Home"
                                elif selection == away:
                                    selection = "Away"
                                else:
                                    selection = "Draw"
                            elif mkey == "spreads":
                                market_key = f"Asian Handicap {line_str}".strip()
                                if selection == home:
                                    selection = "Home"
                                elif selection == away:
                                    selection = "Away"
                            elif mkey == "totals":
                                market_key = f"Over/Under {line_str}".strip()
                                s = selection.lower()
                                if s.startswith("over"):
                                    selection = "Over"
                                elif s.startswith("under"):
                                    selection = "Under"
                            else:
                                continue

                            key = (mid, market_key, selection)
                            sums[key] = sums.get(key, 0.0) + odd
                            counts[key] = counts.get(key, 0) + 1

        out_map: Dict[Tuple[str, str, str], float] = {}
        for key, total in sums.items():
            c = counts.get(key, 0)
            if c > 0:
                out_map[key] = total / c
        return out_map

    def _fetch_league_events(self, league_key: str) -> List[dict]:
        if not settings_v2.odds_api_key:
            return []

        url = f"https://api.the-odds-api.com/v4/sports/{league_key}/odds"
        params = {
            "apiKey": settings_v2.odds_api_key,
            "regions": "eu,uk",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "decimal",
        }
        try:
            data = _http_get_json(url, params=params, timeout=25)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _fetch_fixtures(self, league_keys: List[str]) -> List[dict]:
        out: List[dict] = []
        for lk in league_keys:
            for ev in self._fetch_league_events(lk):
                ev = dict(ev)
                ev["league_key"] = lk
                out.append(ev)
        return out


class JsonFileOddsProvider(OddsProvider):
    """Deterministic mock provider from local JSON fixture."""

    def __init__(self, json_path: Path) -> None:
        self.json_path = json_path

    def _load(self) -> dict:
        try:
            return json.loads(self.json_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def fetch_matches(self, day: date, league_keys: List[str]) -> List[MatchInfo]:
        obj = self._load()
        out: List[MatchInfo] = []
        for m in (obj.get("matches") or []):
            out.append(
                MatchInfo(
                    match_id=str(m.get("match_id", "")),
                    league_key=str(m.get("league_key", "")),
                    league_name=str(m.get("league_name", m.get("league_key", ""))),
                    kickoff_utc=str(m.get("kickoff_utc", "")),
                    home_team=str(m.get("home_team", "")),
                    away_team=str(m.get("away_team", "")),
                )
            )
        return [m for m in out if m.match_id and m.home_team and m.away_team]

    def fetch_market_odds(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Dict[Tuple[str, str, str], float]:
        obj = self._load()
        out: Dict[Tuple[str, str, str], float] = {}
        for row in (obj.get("odds") or []):
            try:
                odd = float(row.get("odds"))
            except Exception:
                continue
            key = (
                str(row.get("match_id", "")),
                str(row.get("market", "")),
                str(row.get("selection", "")),
            )
            out[key] = odd
        return out


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
                data = _http_get_json(url, params=params, timeout=self.timeout)
                if not isinstance(data, dict):
                    continue
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
