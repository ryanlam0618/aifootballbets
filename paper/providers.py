from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from v2.config import settings_v2
from v2.paper.constants import LEAGUE_UNIVERSE, SOFASCORE_LEAGUE_MAP
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


DEFAULT_LEAGUES = LEAGUE_UNIVERSE
