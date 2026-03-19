from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx


SOFASCORE_BASE_URL = "https://www.sofascore.com"


def _norm(x: str) -> str:
    x = (x or "").lower().strip()
    x = re.sub(r"[^a-z0-9\u4e00-\u9fff\s]", " ", x)
    return re.sub(r"\s+", " ", x).strip()


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


def _best_event_by_fuzzy(home_team: str, away_team: str, events: list[dict]) -> Optional[dict]:
    best: Optional[dict] = None
    best_score = 0.0
    best_min_pair = 0.0

    h_in = _norm(home_team)
    a_in = _norm(away_team)

    for e in events:
        ht = (e.get("homeTeam") or {}).get("name", "")
        at = (e.get("awayTeam") or {}).get("name", "")

        d_h = SequenceMatcher(None, h_in, _norm(ht)).ratio()
        d_a = SequenceMatcher(None, a_in, _norm(at)).ratio()
        r_h = SequenceMatcher(None, h_in, _norm(at)).ratio()
        r_a = SequenceMatcher(None, a_in, _norm(ht)).ratio()

        direct_score = (d_h + d_a) / 2
        reverse_score = (r_h + r_a) / 2

        if direct_score >= reverse_score:
            score = direct_score
            min_pair = min(d_h, d_a)
        else:
            score = reverse_score
            min_pair = min(r_h, r_a)

        if score > best_score:
            best_score = score
            best_min_pair = min_pair
            best = e

    # avoid false positives when only one team matches
    if best is None:
        return None
    if best_score < 0.65 or best_min_pair < 0.45:
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
    ):
        self.base_url = base_url.rstrip("/")
        self.raw_dir = raw_dir
        self.sleep_s = sleep_s
        self.timeout_s = timeout_s

        self._client = httpx.Client(
            headers=_default_headers(),
            timeout=httpx.Timeout(timeout_s),
            follow_redirects=True,
        )

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    def _get_json(self, path: str, *, dump_name: Optional[str] = None) -> Any:
        url = f"{self.base_url}{path}"
        r = self._client.get(url)
        r.raise_for_status()
        data = r.json()

        if self.raw_dir and dump_name:
            _dump_json(data, self.raw_dir / dump_name)

        if self.sleep_s:
            time.sleep(self.sleep_s)
        return data

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
) -> Optional[ResolvedEvent]:
    date_str = (match_date or "").strip()[:10]
    if not date_str:
        return None

    data = client.scheduled_events(date_str)
    events = data.get("events", []) if isinstance(data, dict) else []
    if not events:
        return None

    best = _best_event_by_fuzzy(home_team, away_team, events)
    if not best:
        return None

    event_id = int(best.get("id"))
    home_name = (best.get("homeTeam") or {}).get("name") or home_team
    away_name = (best.get("awayTeam") or {}).get("name") or away_team
    start_ts = best.get("startTimestamp")

    return ResolvedEvent(event_id=event_id, home_name=home_name, away_name=away_name, start_timestamp=start_ts)


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


def parse_lineups_to_schema(
    raw_lineups: dict,
    *,
    home_team_name: str,
    away_team_name: str,
    source: str = "sofascore",
) -> Dict[str, Any]:
    """Parse SofaScore lineups JSON into v2 stable schema.

    Returns {"lineup": ..., "injury": ...}
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

    if not isinstance(raw_lineups, dict) or ("error" in raw_lineups):
        return {"lineup": lineup, "injury": injury}

    # New format: {confirmed: bool, home:{players:[...],missingPlayers:[...],formation:""}, away:{...}}
    if "home" in raw_lineups and "away" in raw_lineups:
        home = raw_lineups.get("home") or {}
        away = raw_lineups.get("away") or {}

        lineup["home_team"]["formation"] = home.get("formation") or "Unknown"
        lineup["away_team"]["formation"] = away.get("formation") or "Unknown"

        h_st, h_sb = _parse_players(home.get("players"))
        a_st, a_sb = _parse_players(away.get("players"))
        lineup["home_team"]["starters"] = h_st
        lineup["home_team"]["substitutes"] = h_sb
        lineup["away_team"]["starters"] = a_st
        lineup["away_team"]["substitutes"] = a_sb

        h_inj, h_sus = _parse_missing_players(home.get("missingPlayers"))
        a_inj, a_sus = _parse_missing_players(away.get("missingPlayers"))
        injury["home"]["injuries"] = h_inj
        injury["home"]["suspensions"] = h_sus
        injury["away"]["injuries"] = a_inj
        injury["away"]["suspensions"] = a_sus

        return {"lineup": lineup, "injury": injury}

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

            # Some old payloads might include missingPlayers, keep best-effort
            inj, sus = _parse_missing_players(tl.get("missingPlayers"))

            if is_home:
                lineup["home_team"]["formation"] = formation
                lineup["home_team"]["starters"] = starters
                lineup["home_team"]["substitutes"] = subs
                injury["home"]["injuries"] = inj
                injury["home"]["suspensions"] = sus
            else:
                lineup["away_team"]["formation"] = formation
                lineup["away_team"]["starters"] = starters
                lineup["away_team"]["substitutes"] = subs
                injury["away"]["injuries"] = inj
                injury["away"]["suspensions"] = sus

        return {"lineup": lineup, "injury": injury}

    return {"lineup": lineup, "injury": injury}


def fetch_lineup_and_injury(
    home_team: str,
    away_team: str,
    match_date: str,
    *,
    raw_dir: Optional[Path] = None,
    sleep_s: float = 0.2,
) -> Dict[str, Any]:
    """Resolve event (by date+teams) and fetch lineups. Best-effort; never raises."""
    client = SofaScoreClient(raw_dir=raw_dir, sleep_s=sleep_s)
    try:
        resolved = resolve_event(home_team, away_team, match_date, client=client)
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
            }

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
        }
    finally:
        client.close()


def sofascore_enabled() -> bool:
    return os.getenv("SOFASCORE_ENABLED", "").strip() == "1"
