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


def _parse_number(x) -> float | None:
    if x is None:
        return None
    s = str(x).strip().lower()
    if not s:
        return None
    s = s.replace("o", "").replace("u", "")
    try:
        return float(s)
    except Exception:
        return None


def _american_to_decimal(american) -> float | None:
    if american is None:
        return None
    s = str(american).strip()
    if not s:
        return None
    if s[0] not in "+-":
        # might already be decimal
        try:
            v = float(s)
            return v if v > 1.0 else None
        except Exception:
            return None
    try:
        a = int(s)
    except Exception:
        return None
    if a > 0:
        return 1.0 + (a / 100.0)
    return 1.0 + (100.0 / abs(a))


def _extract_close_odds(node) -> float | None:
    if not isinstance(node, dict):
        return None
    close = node.get("close") or {}
    v = close.get("odds")
    if v is None:
        v = node.get("odds")
    return _american_to_decimal(v)


class EspnOddsFixturesProvider(OddsProvider):
    """
    Primary stdlib-only provider:
    - Fixtures: ESPN scoreboard
    - Odds: ESPN scoreboard competition odds (if available)
    - Optional fallback odds: The Odds API (only when ODDS_API_KEY configured)
    """

    def __init__(self, timeout: int = 25) -> None:
        self.timeout = timeout
        self._event_cache: Dict[Tuple[str, str], List[dict]] = {}

    def _fetch_league_events(self, day: date, league_key: str) -> List[dict]:
        sport_league = ESPN_LEAGUE_MAP.get(league_key)
        if not sport_league:
            return []
        ymd = day.strftime("%Y%m%d")
        ck = (league_key, ymd)
        if ck in self._event_cache:
            return self._event_cache[ck]

        sport, league = sport_league
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
        params = {"dates": ymd}
        try:
            data = _http_get_json(url, params=params, timeout=self.timeout)
        except Exception:
            data = None
        events = (data or {}).get("events") or [] if isinstance(data, dict) else []
        self._event_cache[ck] = events
        return events

    @staticmethod
    def _event_to_match(league_key: str, event: dict) -> MatchInfo | None:
        event_id = str(event.get("id", "")).strip()
        comps = event.get("competitions") or []
        comp = comps[0] if comps else {}
        competitors = comp.get("competitors") or []

        home_name = ""
        away_name = ""
        for c in competitors:
            t = (c.get("team") or {}).get("displayName") or ""
            side = str(c.get("homeAway", "")).lower()
            if side == "home":
                home_name = str(t)
            elif side == "away":
                away_name = str(t)

        if not (event_id and home_name and away_name):
            return None

        kickoff = str(comp.get("date") or event.get("date") or "")
        league_name = str((event.get("league") or {}).get("name") or league_key)
        return MatchInfo(
            match_id=f"{league_key}:{event_id}",
            league_key=league_key,
            league_name=league_name,
            kickoff_utc=kickoff,
            home_team=home_name,
            away_team=away_name,
        )

    def fetch_matches(self, day: date, league_keys: List[str]) -> List[MatchInfo]:
        out: List[MatchInfo] = []
        for lk in league_keys:
            events = self._fetch_league_events(day, lk)
            for ev in events:
                m = self._event_to_match(lk, ev)
                if m:
                    out.append(m)
        return out

    @staticmethod
    def _extract_espn_market_odds(match: MatchInfo, event: dict) -> Dict[Tuple[str, str, str], float]:
        out: Dict[Tuple[str, str, str], float] = {}
        comp = ((event.get("competitions") or [{}])[0]) or {}
        odds_list = comp.get("odds") or []
        if not odds_list:
            return out

        node = odds_list[0] or {}

        # 1X2 from moneyline
        moneyline = node.get("moneyline") or {}
        home_ml = _extract_close_odds(moneyline.get("home") or {})
        away_ml = _extract_close_odds(moneyline.get("away") or {})

        draw_ml = None
        draw_node = moneyline.get("draw") or {}
        draw_ml = _extract_close_odds(draw_node)
        if draw_ml is None:
            draw_odds = node.get("drawOdds") or {}
            draw_ml = _american_to_decimal(draw_odds.get("moneyLine"))

        if home_ml:
            out[(match.match_id, "1X2", "Home")] = float(home_ml)
        if draw_ml:
            out[(match.match_id, "1X2", "Draw")] = float(draw_ml)
        if away_ml:
            out[(match.match_id, "1X2", "Away")] = float(away_ml)

        # Asian handicap from spread
        spread = node.get("pointSpread") or {}
        h_sp = spread.get("home") or {}
        a_sp = spread.get("away") or {}

        h_line = _parse_number((h_sp.get("close") or {}).get("line") or h_sp.get("line"))
        a_line = _parse_number((a_sp.get("close") or {}).get("line") or a_sp.get("line"))
        h_odd = _extract_close_odds(h_sp)
        a_odd = _extract_close_odds(a_sp)

        if h_line is not None and h_odd:
            out[(match.match_id, f"Asian Handicap {h_line}", "Home")] = float(h_odd)
        if a_line is not None and a_odd:
            out[(match.match_id, f"Asian Handicap {a_line}", "Away")] = float(a_odd)

        # Totals from total.over/under
        total = node.get("total") or {}
        over = total.get("over") or {}
        under = total.get("under") or {}
        o_line = _parse_number((over.get("close") or {}).get("line") or over.get("line") or node.get("overUnder"))
        u_line = _parse_number((under.get("close") or {}).get("line") or under.get("line") or node.get("overUnder"))
        o_odd = _extract_close_odds(over)
        u_odd = _extract_close_odds(under)

        if o_line is not None and o_odd:
            out[(match.match_id, f"Over/Under {o_line}", "Over")] = float(o_odd)
        if u_line is not None and u_odd:
            out[(match.match_id, f"Over/Under {u_line}", "Under")] = float(u_odd)

        return out

    @staticmethod
    def _oddsapi_events(league_key: str) -> List[dict]:
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

    @staticmethod
    def _map_oddsapi_for_match(match: MatchInfo, event: dict) -> Dict[Tuple[str, str, str], float]:
        out: Dict[Tuple[str, str, str], float] = {}
        home = str(event.get("home_team", ""))
        away = str(event.get("away_team", ""))
        if match_key(home, away) != match_key(match.home_team, match.away_team):
            return out

        sums: Dict[Tuple[str, str], float] = {}
        counts: Dict[Tuple[str, str], int] = {}

        for bk in (event.get("bookmakers") or []):
            for mk in (bk.get("markets") or []):
                mkey = str(mk.get("key", ""))
                for o in (mk.get("outcomes") or []):
                    sel = str(o.get("name", ""))
                    line = o.get("point")
                    try:
                        odd = float(o.get("price"))
                    except Exception:
                        continue

                    market_key = ""
                    selection = ""
                    if mkey == "h2h":
                        market_key = "1X2"
                        if sel == home:
                            selection = "Home"
                        elif sel == away:
                            selection = "Away"
                        else:
                            selection = "Draw"
                    elif mkey == "spreads":
                        if line is None:
                            continue
                        market_key = f"Asian Handicap {line}"
                        if sel == home:
                            selection = "Home"
                        elif sel == away:
                            selection = "Away"
                        else:
                            continue
                    elif mkey == "totals":
                        if line is None:
                            continue
                        market_key = f"Over/Under {line}"
                        sl = sel.lower()
                        if sl.startswith("over"):
                            selection = "Over"
                        elif sl.startswith("under"):
                            selection = "Under"
                        else:
                            continue
                    else:
                        continue

                    k2 = (market_key, selection)
                    sums[k2] = sums.get(k2, 0.0) + odd
                    counts[k2] = counts.get(k2, 0) + 1

        for k2, total in sums.items():
            c = counts.get(k2, 0)
            if c > 0:
                mk, sel = k2
                out[(match.match_id, mk, sel)] = total / c

        return out

    def fetch_market_odds(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Dict[Tuple[str, str, str], float]:
        out: Dict[Tuple[str, str, str], float] = {}
        match_by_key = {match_key(m.home_team, m.away_team): m for m in matches}

        # ESPN first
        for lk in league_keys:
            events = self._fetch_league_events(day, lk)
            for ev in events:
                m = self._event_to_match(lk, ev)
                if not m:
                    continue
                real_match = match_by_key.get(match_key(m.home_team, m.away_team))
                if not real_match:
                    continue
                out.update(self._extract_espn_market_odds(real_match, ev))

        # The Odds API fallback for missing tuples (only if key exists)
        if settings_v2.odds_api_key:
            for lk in league_keys:
                events = self._oddsapi_events(lk)
                for ev in events:
                    h = str(ev.get("home_team", ""))
                    a = str(ev.get("away_team", ""))
                    m = match_by_key.get(match_key(h, a))
                    if not m:
                        continue
                    mapped = self._map_oddsapi_for_match(m, ev)
                    for k, v in mapped.items():
                        out.setdefault(k, v)

        return out


class OddsApiEspnPlaceholderProvider(EspnOddsFixturesProvider):
    """Backward-compatible alias for older call sites."""


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

    def fetch_ft_scores_with_ids(
        self,
        day: date,
        league_keys: List[str],
    ) -> Tuple[Dict[str, Tuple[int, int]], Dict[str, Tuple[int, int]]]:
        by_names: Dict[str, Tuple[int, int]] = {}
        by_ids: Dict[str, Tuple[int, int]] = {}
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
                name = str(status.get("name", "")).lower()
                if not (completed or state == "post" or name in {"status_final", "final", "full time"}):
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

                score = (int(home[1]), int(away[1]))
                by_names[match_key(home[0], away[0])] = score
                event_id = str(ev.get("id", "")).strip()
                if event_id:
                    by_ids[event_id] = score
                    by_ids[f"{lk}:{event_id}"] = score

        return by_names, by_ids

    def fetch_ft_scores(self, day: date, league_keys: List[str]) -> Dict[str, Tuple[int, int]]:
        names, _ = self.fetch_ft_scores_with_ids(day, league_keys)
        return names


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
