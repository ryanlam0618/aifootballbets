from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from v2.config import settings_v2
from v2.paper.constants import ESPN_LEAGUE_MAP, LEAGUE_UNIVERSE, SOFASCORE_LEAGUE_MAP
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

    def fetch_market_odds_with_meta(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Tuple[Dict[Tuple[str, str, str], float], Dict[Tuple[str, str, str], Dict[str, Any]]]:
        odds = self.fetch_market_odds(day=day, league_keys=league_keys, matches=matches)
        meta: Dict[Tuple[str, str, str], Dict[str, Any]] = {
            k: {"source": "unknown", "is_real": True} for k in odds.keys()
        }
        return odds, meta


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


def _frac_to_decimal(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if "/" in s:
        try:
            a, b = s.split("/", 1)
            return 1.0 + (float(a) / float(b))
        except Exception:
            return None
    try:
        x = float(s)
        return x if x > 1.0 else None
    except Exception:
        return None


def _parse_ah_choice(name: str, home: str, away: str) -> tuple[str, str] | None:
    s = str(name or "").strip()
    if not s:
        return None

    import re

    m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*$", s)
    if not m:
        return None
    line = m.group(1)

    low = normalize_team(s)
    home_n = normalize_team(home)
    away_n = normalize_team(away)

    sel = None
    if home_n and home_n in low:
        sel = "Home"
    elif away_n and away_n in low:
        sel = "Away"
    elif low.startswith("home") or low.startswith("1"):
        sel = "Home"
    elif low.startswith("away") or low.startswith("2"):
        sel = "Away"

    if not sel:
        return None
    return line, sel


class EspnOddsFixturesProvider(OddsProvider):
    """
    Primary stdlib-only provider:
    - Fixtures: ESPN scoreboard
    - Odds: SofaScore-first for the 3 supported market families (1X2 / OU / AH)
    - ESPN odds used when available
    - Optional fallback odds: The Odds API (only when ODDS_API_KEY configured)
    """

    def __init__(self, timeout: int = 25) -> None:
        self.timeout = timeout
        self._event_cache: Dict[Tuple[str, str], List[dict]] = {}
        self._last_meta: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

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

    def _sofascore_events_for_day(self, day: date) -> List[dict]:
        out: List[dict] = []
        for d in (day - timedelta(days=1), day, day + timedelta(days=1)):
            url = f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{d.isoformat()}"
            try:
                data = _http_get_json(url, timeout=self.timeout)
            except Exception:
                data = None
            events = (data or {}).get("events") or [] if isinstance(data, dict) else []
            out.extend(events)
        return out

    def _sofascore_odds_event(self, event_id: str, provider_id: int = 1) -> dict:
        url = f"https://www.sofascore.com/api/v1/event/{event_id}/odds/{provider_id}/all"
        try:
            data = _http_get_json(url, timeout=self.timeout)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _sofascore_map_odds_for_match(self, match: MatchInfo, event_id: str) -> Dict[Tuple[str, str, str], float]:
        payload = self._sofascore_odds_event(event_id, provider_id=1)
        markets = payload.get("markets") or []
        out: Dict[Tuple[str, str, str], float] = {}

        for m in markets:
            name = str(m.get("marketName") or "").strip()
            choices = m.get("choices") or []

            if name == "Full time":
                for c in choices:
                    nm = str(c.get("name") or "").strip()
                    if nm == "1":
                        sel = "Home"
                    elif nm in {"X", "x"}:
                        sel = "Draw"
                    elif nm == "2":
                        sel = "Away"
                    else:
                        continue
                    odd = _frac_to_decimal(c.get("fractionalValue"))
                    if odd and odd > 1.0:
                        out[(match.match_id, "1X2", sel)] = float(odd)

            elif name == "Match goals":
                line = _parse_number(m.get("choiceGroup"))
                if line is None:
                    continue
                for c in choices:
                    sel_raw = str(c.get("name") or "").strip().lower()
                    if sel_raw == "over":
                        sel = "Over"
                    elif sel_raw == "under":
                        sel = "Under"
                    else:
                        continue
                    odd = _frac_to_decimal(c.get("fractionalValue"))
                    if odd and odd > 1.0:
                        out[(match.match_id, f"Over/Under {line}", sel)] = float(odd)

            elif name == "Asian handicap":
                for c in choices:
                    parsed = _parse_ah_choice(str(c.get("name") or ""), match.home_team, match.away_team)
                    if not parsed:
                        continue
                    line_s, sel = parsed
                    odd = _frac_to_decimal(c.get("fractionalValue"))
                    if odd and odd > 1.0:
                        out[(match.match_id, f"Asian Handicap {line_s}", sel)] = float(odd)

        return out

    def fetch_market_odds_with_meta(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Tuple[Dict[Tuple[str, str, str], float], Dict[Tuple[str, str, str], Dict[str, Any]]]:
        out: Dict[Tuple[str, str, str], float] = {}
        meta: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
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
                mapped = self._extract_espn_market_odds(real_match, ev)
                for k, v in mapped.items():
                    out[k] = v
                    meta[k] = {"source": "espn", "is_real": True}

        # SofaScore primary source for missing or unmatched tuples inside the
        # supported market families (1X2 / Over/Under / Asian Handicap)
        sofa_events = self._sofascore_events_for_day(day)
        sofa_match_to_event: Dict[str, str] = {}
        for ev in sofa_events:
            event_id = str(ev.get("id", "")).strip()
            if not event_id:
                continue
            home = str((ev.get("homeTeam") or {}).get("name") or "")
            away = str((ev.get("awayTeam") or {}).get("name") or "")
            k = match_key(home, away)
            if k and (k not in sofa_match_to_event):
                sofa_match_to_event[k] = event_id

        for m in matches:
            event_id = sofa_match_to_event.get(match_key(m.home_team, m.away_team))
            if not event_id:
                continue
            mapped = self._sofascore_map_odds_for_match(m, event_id)
            for k, v in mapped.items():
                if k not in out:
                    out[k] = v
                    meta[k] = {"source": "sofascore", "is_real": True}

        # Optional The Odds API fallback for still-missing tuples (only if key exists)
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
                        if k not in out:
                            out[k] = v
                            meta[k] = {"source": "odds_api", "is_real": True}

        self._last_meta = meta
        return out, meta

    def fetch_market_odds(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Dict[Tuple[str, str, str], float]:
        out, _meta = self.fetch_market_odds_with_meta(day=day, league_keys=league_keys, matches=matches)
        return out


class OddsApiEspnPlaceholderProvider(EspnOddsFixturesProvider):
    """Backward-compatible alias for older call sites."""


class SofaScoreFixturesResultsProvider(OddsProvider, ResultsProvider):
    """
    SofaScore fixtures + results + odds provider (stdlib-only urllib JSON fetches).

    Endpoints:
    - /sport/football/scheduled-events/{date}
    - /event/{event_id}
    - /event/{event_id}/odds/{provider_id}/all

    Notes:
    - date input is interpreted in Asia/Shanghai day context.
    - 09:00->09:00 Asia/Shanghai window is enforced by fetching adjacent dates and filtering by timestamp.
    - This repo currently normalizes only 3 market families from SofaScore odds:
      1X2 / Over-Under / Asian Handicap.
    """

    BASE_URL = "https://www.sofascore.com/api/v1"

    def __init__(self, timeout: int = 25) -> None:
        self.timeout = timeout
        self._scheduled_cache: Dict[str, List[dict]] = {}
        self._event_cache: Dict[str, dict] = {}
        self._tz_cst = timezone(timedelta(hours=8))

    @staticmethod
    def _norm(s: str) -> str:
        return " ".join((s or "").strip().lower().split())

    def _fetch_scheduled_events_for_date(self, day_iso: str) -> List[dict]:
        if day_iso in self._scheduled_cache:
            return self._scheduled_cache[day_iso]
        url = f"{self.BASE_URL}/sport/football/scheduled-events/{day_iso}"
        try:
            data = _http_get_json(url, timeout=self.timeout)
        except Exception:
            data = None
        events = (data or {}).get("events") or [] if isinstance(data, dict) else []
        self._scheduled_cache[day_iso] = events
        return events

    def _fetch_event(self, event_id: str) -> dict:
        if event_id in self._event_cache:
            return self._event_cache[event_id]
        url = f"{self.BASE_URL}/event/{event_id}"
        try:
            data = _http_get_json(url, timeout=self.timeout)
        except Exception:
            data = None
        event_obj = (data or {}).get("event") or {} if isinstance(data, dict) else {}
        self._event_cache[event_id] = event_obj
        return event_obj

    def _league_key_for_event(self, event: dict, league_keys: List[str]) -> str | None:
        uniq = (((event.get("tournament") or {}).get("uniqueTournament") or {}).get("id"))
        try:
            uniq_id = int(uniq) if uniq is not None else None
        except Exception:
            uniq_id = None

        tname = self._norm(str((event.get("tournament") or {}).get("name") or ""))
        cname = self._norm(str(((event.get("tournament") or {}).get("category") or {}).get("name") or ""))

        for lk in league_keys:
            cfg = SOFASCORE_LEAGUE_MAP.get(lk) or {}
            tids = cfg.get("tournament_ids") or []
            if uniq_id is not None and uniq_id in tids:
                return lk

        for lk in league_keys:
            cfg = SOFASCORE_LEAGUE_MAP.get(lk) or {}
            c_alias = {self._norm(str(x)) for x in (cfg.get("category_aliases") or [])}
            t_alias = {self._norm(str(x)) for x in (cfg.get("tournament_aliases") or [])}
            if tname in t_alias and (not c_alias or cname in c_alias):
                return lk

        return None

    def _window_bounds_utc(self, day: date) -> Tuple[datetime, datetime]:
        start_local = datetime(day.year, day.month, day.day, 9, 0, 0, tzinfo=self._tz_cst)
        end_local = start_local + timedelta(days=1)
        return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

    def _candidate_fetch_dates(self, day: date) -> List[str]:
        # Fetch adjacent dates to avoid missing matches around timezone boundaries.
        return [
            (day - timedelta(days=1)).isoformat(),
            day.isoformat(),
            (day + timedelta(days=1)).isoformat(),
        ]

    def _event_start_utc(self, event: dict) -> datetime | None:
        ts = event.get("startTimestamp")
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except Exception:
            return None

    @staticmethod
    def _event_to_match(league_key: str, event: dict) -> MatchInfo | None:
        event_id = str(event.get("id", "")).strip()
        home = str((event.get("homeTeam") or {}).get("name") or "").strip()
        away = str((event.get("awayTeam") or {}).get("name") or "").strip()
        if not (event_id and home and away):
            return None

        start_ts = event.get("startTimestamp")
        kickoff = ""
        try:
            kickoff = datetime.fromtimestamp(int(start_ts), tz=timezone.utc).replace(microsecond=0).isoformat()
        except Exception:
            kickoff = ""

        league_name = str((event.get("tournament") or {}).get("name") or league_key)
        return MatchInfo(
            match_id=f"{league_key}:{event_id}",
            league_key=league_key,
            league_name=league_name,
            kickoff_utc=kickoff,
            home_team=home,
            away_team=away,
        )

    def fetch_matches(self, day: date, league_keys: List[str]) -> List[MatchInfo]:
        start_utc, end_utc = self._window_bounds_utc(day)
        out: List[MatchInfo] = []
        seen_ids = set()

        for day_iso in self._candidate_fetch_dates(day):
            events = self._fetch_scheduled_events_for_date(day_iso)
            for ev in events:
                event_id = str(ev.get("id", "")).strip()
                if not event_id or event_id in seen_ids:
                    continue

                start = self._event_start_utc(ev)
                if start is None or not (start_utc <= start < end_utc):
                    continue

                lk = self._league_key_for_event(ev, league_keys)
                if not lk:
                    continue

                m = self._event_to_match(lk, ev)
                if not m:
                    continue
                out.append(m)
                seen_ids.add(event_id)

        return out

    def fetch_market_odds(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Dict[Tuple[str, str, str], float]:
        # Keep run_day compatible; synthetic fallback will patch markets when this is empty.
        _ = (day, league_keys, matches)
        return {}

    def fetch_market_odds_with_meta(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Tuple[Dict[Tuple[str, str, str], float], Dict[Tuple[str, str, str], Dict[str, Any]]]:
        odds = self.fetch_market_odds(day=day, league_keys=league_keys, matches=matches)
        meta: Dict[Tuple[str, str, str], Dict[str, Any]] = {
            k: {"source": "sofascore", "is_real": True} for k in odds.keys()
        }
        return odds, meta

    def fetch_ft_scores_with_ids(
        self,
        day: date,
        league_keys: List[str],
    ) -> Tuple[Dict[str, Tuple[int, int]], Dict[str, Tuple[int, int]]]:
        by_names: Dict[str, Tuple[int, int]] = {}
        by_ids: Dict[str, Tuple[int, int]] = {}
        start_utc, end_utc = self._window_bounds_utc(day)

        for day_iso in self._candidate_fetch_dates(day):
            events = self._fetch_scheduled_events_for_date(day_iso)
            for ev in events:
                event_id = str(ev.get("id", "")).strip()
                if not event_id:
                    continue

                lk = self._league_key_for_event(ev, league_keys)
                if not lk:
                    continue

                start = self._event_start_utc(ev)
                if start is None or not (start_utc <= start < end_utc):
                    continue

                detail = self._fetch_event(event_id)
                status_type = ((detail.get("status") or {}).get("type") or "")
                if str(status_type).lower() != "finished":
                    continue

                home_score = ((detail.get("homeScore") or {}).get("current"))
                away_score = ((detail.get("awayScore") or {}).get("current"))
                try:
                    h = int(home_score)
                    a = int(away_score)
                except Exception:
                    continue

                home_name = str((detail.get("homeTeam") or {}).get("name") or (ev.get("homeTeam") or {}).get("name") or "")
                away_name = str((detail.get("awayTeam") or {}).get("name") or (ev.get("awayTeam") or {}).get("name") or "")
                if not (home_name and away_name):
                    continue

                score = (h, a)
                by_names[match_key(home_name, away_name)] = score
                by_ids[event_id] = score
                by_ids[f"{lk}:{event_id}"] = score

        return by_names, by_ids

    def fetch_ft_scores(self, day: date, league_keys: List[str]) -> Dict[str, Tuple[int, int]]:
        names, _ = self.fetch_ft_scores_with_ids(day=day, league_keys=league_keys)
        return names


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

    def fetch_market_odds_with_meta(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Tuple[Dict[Tuple[str, str, str], float], Dict[Tuple[str, str, str], Dict[str, Any]]]:
        _ = (day, league_keys, matches)
        obj = self._load()
        out: Dict[Tuple[str, str, str], float] = {}
        meta: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
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
            is_real = str(row.get("source_quality", "real_odds")).strip().lower() == "real_odds"
            meta[key] = {
                "source": str(row.get("source", "json_fixture")),
                "is_real": is_real,
            }
        return out, meta

    def fetch_market_odds(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Dict[Tuple[str, str, str], float]:
        out, _meta = self.fetch_market_odds_with_meta(day=day, league_keys=league_keys, matches=matches)
        return out


class JsonFileResultsProvider(ResultsProvider):
    """Deterministic mock results provider from local JSON fixture."""

    def __init__(self, json_path: Path) -> None:
        self.json_path = json_path

    def _load(self) -> dict:
        try:
            return json.loads(self.json_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def fetch_ft_scores_with_ids(
        self,
        day: date,
        league_keys: List[str],
    ) -> Tuple[Dict[str, Tuple[int, int]], Dict[str, Tuple[int, int]]]:
        _ = (day, league_keys)
        obj = self._load()
        by_names: Dict[str, Tuple[int, int]] = {}
        by_ids: Dict[str, Tuple[int, int]] = {}

        for row in (obj.get("results") or []):
            try:
                home_goals = int(row.get("home_goals"))
                away_goals = int(row.get("away_goals"))
            except Exception:
                continue

            home = str(row.get("home_team", "")).strip()
            away = str(row.get("away_team", "")).strip()
            match_id = str(row.get("match_id", "")).strip()
            league_key = str(row.get("league_key", "")).strip()

            if home and away:
                by_names[match_key(home, away)] = (home_goals, away_goals)
            if match_id:
                by_ids[match_id] = (home_goals, away_goals)
                if league_key and ":" not in match_id:
                    by_ids[f"{league_key}:{match_id}"] = (home_goals, away_goals)

        return by_names, by_ids

    def fetch_ft_scores(self, day: date, league_keys: List[str]) -> Dict[str, Tuple[int, int]]:
        names, _ = self.fetch_ft_scores_with_ids(day=day, league_keys=league_keys)
        return names


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
