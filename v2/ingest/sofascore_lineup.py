from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover - exercised in envs without httpx
    httpx = None


SOFASCORE_BASE_URL = "https://www.sofascore.com"


def _norm(x: str) -> str:
    x = (x or "").lower().strip()
    x = x.replace("&", " and ")
    x = re.sub(r"[^a-z0-9\u4e00-\u9fff\s]", " ", x)
    x = re.sub(r"\s+", " ", x).strip()

    # remove common football-club suffix/prefix tokens to improve matching robustness
    stop = {
        "fc",
        "cf",
        "sc",
        "ac",
        "afc",
        "fk",
        "if",
        "bk",
        "club",
        "de",
        "the",
    }
    alias = {
        "utd": "united",
        "man": "manchester",
        "st": "saint",
    }
    tokens = []
    for t in x.split():
        if not t or t in stop:
            continue
        tokens.append(alias.get(t, t))
    return " ".join(tokens).strip()


def _token_similarity(a: str, b: str) -> float:
    sa = set((a or "").split())
    sb = set((b or "").split())
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _str_ratio(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio()


def _team_name_score(a: str, b: str) -> float:
    na = _norm(a)
    nb = _norm(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    # weighted blend: robust to token noise while still rewarding close full-string match
    return (0.65 * _str_ratio(na, nb)) + (0.35 * _token_similarity(na, nb))


def _parse_kickoff_ts(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)

    s = str(value).strip()
    if not s:
        return None

    if s.isdigit():
        # already timestamp-like
        return int(s)

    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _retry_after_seconds(headers: Any) -> Optional[float]:
    try:
        if headers is None:
            return None
        val = headers.get("Retry-After")
        if val is None:
            return None
        return max(0.0, float(str(val).strip()))
    except Exception:
        return None


def _default_headers() -> Dict[str, str]:
    # SofaScore tends to be stricter for some client stacks.
    # httpx works reliably in our runtime; keep headers browser-like.
    return {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.sofascore.com/",
    }


@dataclass
class ResolvedEvent:
    event_id: int
    home_name: str
    away_name: str
    start_timestamp: Optional[int] = None
    source: str = "sofascore"
    confidence: float = 0.0


@dataclass
class _CandidateEvent:
    event: dict
    confidence: float
    min_pair_score: float


class EventIdCache:
    """Simple JSON cache: {match_id: {event_id, confidence, updated_at, ...}}."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def get_event_id(self, match_id: Optional[str]) -> Optional[int]:
        if not match_id:
            return None
        rec = self._load().get(str(match_id))
        if not isinstance(rec, dict):
            return None
        eid = rec.get("event_id")
        try:
            return int(eid)
        except Exception:
            return None

    def set_event(
        self,
        *,
        match_id: Optional[str],
        event_id: int,
        confidence: float,
        home_team: str,
        away_team: str,
        match_date: str,
        kickoff_time_utc: Optional[str] = None,
    ) -> None:
        if not match_id:
            return

        data = self._load()
        data[str(match_id)] = {
            "event_id": int(event_id),
            "confidence": float(confidence),
            "home_team": home_team,
            "away_team": away_team,
            "match_date": (match_date or "")[:10],
            "kickoff_time_utc": kickoff_time_utc,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _score_event_candidate(
    home_team: str,
    away_team: str,
    event: dict,
    *,
    kickoff_ts: Optional[int],
    kickoff_tolerance_minutes: int,
) -> _CandidateEvent:
    ht = (event.get("homeTeam") or {}).get("name", "")
    at = (event.get("awayTeam") or {}).get("name", "")

    d_h = _team_name_score(home_team, ht)
    d_a = _team_name_score(away_team, at)
    r_h = _team_name_score(home_team, at)
    r_a = _team_name_score(away_team, ht)

    direct_score = (d_h + d_a) / 2
    reverse_score = (r_h + r_a) / 2

    if direct_score >= reverse_score:
        team_score = direct_score
        min_pair = min(d_h, d_a)
    else:
        team_score = reverse_score
        min_pair = min(r_h, r_a)

    # kickoff-time compatibility (optional): down-weight likely wrong match on same day
    time_score: Optional[float] = None
    event_ts = event.get("startTimestamp")
    try:
        event_ts_int = int(event_ts) if event_ts is not None else None
    except Exception:
        event_ts_int = None

    if kickoff_ts is not None and event_ts_int is not None:
        tolerance = max(60, int(kickoff_tolerance_minutes) * 60)
        diff = abs(event_ts_int - kickoff_ts)
        # linearly decay within tolerance, hard floor outside tolerance
        if diff <= tolerance:
            time_score = max(0.0, 1.0 - (diff / tolerance))
        else:
            time_score = 0.0

    if time_score is None:
        confidence = team_score
    else:
        confidence = (0.8 * team_score) + (0.2 * time_score)

    return _CandidateEvent(event=event, confidence=confidence, min_pair_score=min_pair)


def _best_event_by_fuzzy(
    home_team: str,
    away_team: str,
    events: list[dict],
    *,
    kickoff_time_utc: Optional[str] = None,
    kickoff_tolerance_minutes: int = 240,
    min_confidence: float = 0.55,
    min_pair_score: float = 0.45,
) -> Optional[_CandidateEvent]:
    best: Optional[_CandidateEvent] = None
    kickoff_ts = _parse_kickoff_ts(kickoff_time_utc)

    for e in events:
        if not isinstance(e, dict):
            continue
        cand = _score_event_candidate(
            home_team,
            away_team,
            e,
            kickoff_ts=kickoff_ts,
            kickoff_tolerance_minutes=kickoff_tolerance_minutes,
        )
        if best is None or cand.confidence > best.confidence:
            best = cand

    if best is None:
        return None

    # avoid false positives when only one team matches or confidence too low
    if best.confidence < min_confidence or best.min_pair_score < min_pair_score:
        return None
    return best


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _dump_json(obj: Any, path: Path) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


class SofaScoreClient:
    def __init__(
        self,
        base_url: str = SOFASCORE_BASE_URL,
        raw_dir: Optional[Path] = None,
        sleep_s: float = 0.2,
        timeout_s: float = 20.0,
        max_retries: int = 3,
        retry_backoff_s: float = 0.5,
    ):
        self.base_url = base_url.rstrip("/")
        self.raw_dir = raw_dir
        self.sleep_s = sleep_s
        self.timeout_s = timeout_s
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_s = max(0.0, float(retry_backoff_s))

        self._client = None
        self._requests = None

        if httpx is not None:
            self._client = httpx.Client(
                headers=_default_headers(),
                timeout=httpx.Timeout(timeout_s),
                follow_redirects=True,
            )
        else:
            # Fallback path for lean test/runtime envs where httpx is absent.
            import requests  # local import to avoid hard dependency at module import time

            sess = requests.Session()
            sess.headers.update(_default_headers())
            self._requests = sess

    def close(self) -> None:
        try:
            if self._client is not None:
                self._client.close()
            if self._requests is not None:
                self._requests.close()
        except Exception:
            pass

    def _sleep_rate_limit(self) -> None:
        if self.sleep_s:
            time.sleep(self.sleep_s)

    def _is_retryable_http_status(self, status: Optional[int]) -> bool:
        return status == 429 or (status is not None and status >= 500)

    def _get_json(self, path: str, *, dump_name: Optional[str] = None) -> Any:
        url = f"{self.base_url}{path}"
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            if self._client is not None:
                try:
                    r = self._client.get(url)
                    r.raise_for_status()
                    data = r.json()
                    if self.raw_dir and dump_name:
                        _dump_json(data, self.raw_dir / dump_name)
                    self._sleep_rate_limit()
                    return data
                except Exception as e:
                    last_exc = e
                    status = None
                    headers = None
                    if httpx is not None and isinstance(e, httpx.HTTPStatusError):
                        status = e.response.status_code
                        headers = e.response.headers
                    elif httpx is not None and isinstance(e, httpx.RequestError):
                        status = None

                    if not self._is_retryable_http_status(status) and status is not None:
                        raise
                    if status is None and httpx is not None and not isinstance(e, httpx.RequestError):
                        raise

                    if attempt >= self.max_retries:
                        raise
                    retry_after = _retry_after_seconds(headers)
                    sleep_for = max(retry_after or 0.0, self.retry_backoff_s * (2**attempt))
                    time.sleep(min(30.0, sleep_for))
            else:
                assert self._requests is not None
                try:
                    r = self._requests.get(url, timeout=self.timeout_s, allow_redirects=True)
                    r.raise_for_status()
                    data = r.json()
                    if self.raw_dir and dump_name:
                        _dump_json(data, self.raw_dir / dump_name)
                    self._sleep_rate_limit()
                    return data
                except Exception as e:
                    last_exc = e
                    status = getattr(getattr(e, "response", None), "status_code", None)
                    headers = getattr(getattr(e, "response", None), "headers", None)

                    # requests retry for network errors OR 429/5xx status
                    retryable = status is None or self._is_retryable_http_status(status)
                    if not retryable:
                        raise

                    if attempt >= self.max_retries:
                        raise
                    retry_after = _retry_after_seconds(headers)
                    sleep_for = max(retry_after or 0.0, self.retry_backoff_s * (2**attempt))
                    time.sleep(min(30.0, sleep_for))

        # defensive, should have returned/raised above
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Unexpected SofaScore client state")

    def scheduled_events(self, date_yyyy_mm_dd: str) -> dict:
        date_str = (date_yyyy_mm_dd or "").strip()[:10]
        return self._get_json(
            f"/api/v1/sport/football/scheduled-events/{date_str}",
            dump_name=f"scheduled-events_{date_str}.json" if self.raw_dir else None,
        )

    def event(self, event_id: int) -> dict:
        return self._get_json(
            f"/api/v1/event/{int(event_id)}",
            dump_name=f"event_{int(event_id)}.json" if self.raw_dir else None,
        )

    def lineups(self, event_id: int) -> dict:
        return self._get_json(
            f"/api/v1/event/{int(event_id)}/lineups",
            dump_name=f"lineups_{int(event_id)}.json" if self.raw_dir else None,
        )


def resolve_event(
    home_team: str,
    away_team: str,
    match_date: str,
    *,
    client: SofaScoreClient,
    kickoff_time_utc: Optional[str] = None,
) -> Optional[ResolvedEvent]:
    date_str = (match_date or "").strip()[:10]
    if not date_str:
        return None

    data = client.scheduled_events(date_str)
    events = data.get("events", []) if isinstance(data, dict) else []
    if not events:
        return None

    best = _best_event_by_fuzzy(
        home_team,
        away_team,
        events,
        kickoff_time_utc=kickoff_time_utc,
    )
    if not best:
        return None

    event = best.event
    event_id = int(event.get("id"))
    home_name = (event.get("homeTeam") or {}).get("name") or home_team
    away_name = (event.get("awayTeam") or {}).get("name") or away_team
    start_ts = event.get("startTimestamp")

    return ResolvedEvent(
        event_id=event_id,
        home_name=home_name,
        away_name=away_name,
        start_timestamp=start_ts,
        confidence=best.confidence,
    )


def _parse_missing_players(items: Any) -> Tuple[list[dict], list[dict]]:
    """Return (injuries, suspensions)."""
    injuries: list[dict] = []
    suspensions: list[dict] = []

    if not isinstance(items, list):
        return injuries, suspensions

    for mp in items:
        if not isinstance(mp, dict):
            continue
        player = mp.get("player") or {}
        name = (player.get("name") or player.get("shortName") or "Unknown")

        rec = {
            "name": name,
            "player_id": player.get("id"),
            "position": player.get("position"),
            "type": mp.get("type"),  # missing / doubtful
            "description": mp.get("description"),
            "expected_end_date": mp.get("expectedEndDate"),
        }

        desc = str(mp.get("description") or "").lower()
        # heuristic only; keep conservative
        if "suspend" in desc or "red card" in desc or "yellow" in desc:
            suspensions.append(rec)
        else:
            injuries.append(rec)

    return injuries, suspensions


def _parse_players(items: Any) -> Tuple[list[dict], list[dict]]:
    starters: list[dict] = []
    subs: list[dict] = []

    if not isinstance(items, list):
        return starters, subs

    for it in items:
        if not isinstance(it, dict):
            continue

        p = it.get("player") or {}
        rec = {
            "id": p.get("id"),
            "name": p.get("name") or p.get("shortName") or "Unknown",
            "number": it.get("shirtNumber"),
            "position": it.get("position") or p.get("position"),
            "rating": it.get("avgRating"),
        }
        if it.get("substitute"):
            subs.append(rec)
        else:
            starters.append(rec)

    return starters, subs


def _missing_features(items: Any) -> Dict[str, Any]:
    out = {
        "missing_count": 0,
        "doubtful_count": 0,
        "missing_by_position": {},
    }
    if not isinstance(items, list):
        return out

    by_pos: Dict[str, int] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        typ = str(it.get("type") or "").strip().lower()
        if typ == "doubtful":
            out["doubtful_count"] += 1
        else:
            out["missing_count"] += 1

        player = it.get("player") or {}
        pos = (player.get("position") or "UNKNOWN")
        pos = str(pos).strip().upper() or "UNKNOWN"
        by_pos[pos] = by_pos.get(pos, 0) + 1

    out["missing_by_position"] = by_pos
    return out


def parse_lineups_to_schema(
    raw_lineups: dict,
    *,
    home_team_name: str,
    away_team_name: str,
    source: str = "sofascore",
) -> Dict[str, Any]:
    """Parse SofaScore lineups JSON into v2 stable schema.

    Returns {"lineup": ..., "injury": ..., "sofascore_features": ...}
    """

    lineup = {
        "home_team": {"name": home_team_name, "formation": "Unknown", "starters": [], "substitutes": []},
        "away_team": {"name": away_team_name, "formation": "Unknown", "starters": [], "substitutes": []},
        "source": source,
    }
    injury = {
        "home": {"injuries": [], "suspensions": [], "total_impact": 0.0},
        "away": {"injuries": [], "suspensions": [], "total_impact": 0.0},
        "source": source,
    }
    features = {
        "lineup_confirmed": None,
        "home": {"missing_count": 0, "doubtful_count": 0, "missing_by_position": {}},
        "away": {"missing_count": 0, "doubtful_count": 0, "missing_by_position": {}},
    }

    if not isinstance(raw_lineups, dict) or ("error" in raw_lineups):
        return {"lineup": lineup, "injury": injury, "sofascore_features": features}

    # New format: {confirmed: bool, home:{players:[...],missingPlayers:[...],formation:""}, away:{...}}
    if "home" in raw_lineups and "away" in raw_lineups:
        home = raw_lineups.get("home") or {}
        away = raw_lineups.get("away") or {}

        if "confirmed" in raw_lineups:
            features["lineup_confirmed"] = bool(raw_lineups.get("confirmed"))

        lineup["home_team"]["formation"] = home.get("formation") or "Unknown"
        lineup["away_team"]["formation"] = away.get("formation") or "Unknown"

        h_st, h_sb = _parse_players(home.get("players"))
        a_st, a_sb = _parse_players(away.get("players"))
        lineup["home_team"]["starters"] = h_st
        lineup["home_team"]["substitutes"] = h_sb
        lineup["away_team"]["starters"] = a_st
        lineup["away_team"]["substitutes"] = a_sb

        h_missing = home.get("missingPlayers")
        a_missing = away.get("missingPlayers")

        h_inj, h_sus = _parse_missing_players(h_missing)
        a_inj, a_sus = _parse_missing_players(a_missing)
        injury["home"]["injuries"] = h_inj
        injury["home"]["suspensions"] = h_sus
        injury["away"]["injuries"] = a_inj
        injury["away"]["suspensions"] = a_sus

        features["home"] = _missing_features(h_missing)
        features["away"] = _missing_features(a_missing)

        return {"lineup": lineup, "injury": injury, "sofascore_features": features}

    # Old format: {lineups:[{isHome:bool, formation:{name:""}, starters:[...], substitutes:[...], missingPlayers:[]?}]}
    if "lineups" in raw_lineups and isinstance(raw_lineups.get("lineups"), list):
        for tl in raw_lineups.get("lineups") or []:
            if not isinstance(tl, dict):
                continue
            is_home = bool(tl.get("isHome"))

            formation = ((tl.get("formation") or {}).get("name")) or "Unknown"

            starters = []
            subs = []
            for p in (tl.get("starters") or []):
                if not isinstance(p, dict):
                    continue
                pi = p.get("player") or {}
                starters.append(
                    {
                        "id": pi.get("id"),
                        "name": pi.get("name") or pi.get("shortName") or "Unknown",
                        "number": p.get("shirtNumber"),
                        "position": p.get("position") or pi.get("position"),
                        "rating": p.get("rating"),
                    }
                )
            for p in (tl.get("substitutes") or []):
                if not isinstance(p, dict):
                    continue
                pi = p.get("player") or {}
                subs.append(
                    {
                        "id": pi.get("id"),
                        "name": pi.get("name") or pi.get("shortName") or "Unknown",
                        "number": p.get("shirtNumber"),
                        "position": p.get("position") or pi.get("position"),
                        "rating": p.get("rating"),
                    }
                )

            missing = tl.get("missingPlayers")
            # Some old payloads might include missingPlayers, keep best-effort
            inj, sus = _parse_missing_players(missing)
            side_features = _missing_features(missing)

            if is_home:
                lineup["home_team"]["formation"] = formation
                lineup["home_team"]["starters"] = starters
                lineup["home_team"]["substitutes"] = subs
                injury["home"]["injuries"] = inj
                injury["home"]["suspensions"] = sus
                features["home"] = side_features
            else:
                lineup["away_team"]["formation"] = formation
                lineup["away_team"]["starters"] = starters
                lineup["away_team"]["substitutes"] = subs
                injury["away"]["injuries"] = inj
                injury["away"]["suspensions"] = sus
                features["away"] = side_features

        return {"lineup": lineup, "injury": injury, "sofascore_features": features}

    return {"lineup": lineup, "injury": injury, "sofascore_features": features}


def fetch_lineup_and_injury(
    home_team: str,
    away_team: str,
    match_date: str,
    *,
    match_id: Optional[str] = None,
    kickoff_time_utc: Optional[str] = None,
    raw_dir: Optional[Path] = None,
    sleep_s: float = 0.2,
    event_cache_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Resolve event (by date+teams) and fetch lineups. Best-effort; never raises."""
    client = SofaScoreClient(raw_dir=raw_dir, sleep_s=sleep_s)
    cache_path = event_cache_path or Path(os.getenv("SOFASCORE_EVENT_CACHE_PATH", "data/v2/sofascore_event_cache.json"))
    cache = EventIdCache(cache_path)

    try:
        cached_event_id = cache.get_event_id(match_id)
        if cached_event_id is not None:
            raw = client.lineups(cached_event_id)
            return parse_lineups_to_schema(
                raw,
                home_team_name=home_team,
                away_team_name=away_team,
                source="sofascore",
            )

        resolved = resolve_event(
            home_team,
            away_team,
            match_date,
            client=client,
            kickoff_time_utc=kickoff_time_utc,
        )
        if not resolved:
            return {
                "lineup": {
                    "home_team": {"name": home_team, "formation": "Unknown", "starters": [], "substitutes": []},
                    "away_team": {"name": away_team, "formation": "Unknown", "starters": [], "substitutes": []},
                    "source": "sofascore:not_resolved",
                },
                "injury": {
                    "home": {"injuries": [], "suspensions": [], "total_impact": 0.0},
                    "away": {"injuries": [], "suspensions": [], "total_impact": 0.0},
                    "source": "sofascore:not_resolved",
                },
                "sofascore_features": {
                    "lineup_confirmed": None,
                    "home": {"missing_count": 0, "doubtful_count": 0, "missing_by_position": {}},
                    "away": {"missing_count": 0, "doubtful_count": 0, "missing_by_position": {}},
                },
            }

        cache.set_event(
            match_id=match_id,
            event_id=resolved.event_id,
            confidence=resolved.confidence,
            home_team=resolved.home_name,
            away_team=resolved.away_name,
            match_date=match_date,
            kickoff_time_utc=kickoff_time_utc,
        )

        raw = client.lineups(resolved.event_id)
        return parse_lineups_to_schema(
            raw,
            home_team_name=resolved.home_name,
            away_team_name=resolved.away_name,
            source="sofascore",
        )
    except Exception as e:
        return {
            "lineup": {
                "home_team": {"name": home_team, "formation": "Unknown", "starters": [], "substitutes": []},
                "away_team": {"name": away_team, "formation": "Unknown", "starters": [], "substitutes": []},
                "source": f"sofascore:error:{type(e).__name__}",
            },
            "injury": {
                "home": {"injuries": [], "suspensions": [], "total_impact": 0.0},
                "away": {"injuries": [], "suspensions": [], "total_impact": 0.0},
                "source": f"sofascore:error:{type(e).__name__}",
            },
            "sofascore_features": {
                "lineup_confirmed": None,
                "home": {"missing_count": 0, "doubtful_count": 0, "missing_by_position": {}},
                "away": {"missing_count": 0, "doubtful_count": 0, "missing_by_position": {}},
            },
        }
    finally:
        client.close()


def sofascore_enabled() -> bool:
    return os.getenv("SOFASCORE_ENABLED", "").strip() == "1"
