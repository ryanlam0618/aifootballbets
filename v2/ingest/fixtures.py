from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd
import requests

from v2.config import settings_v2


@dataclass
class MatchRequest:
    raw: str
    home_input: str
    away_input: str
    league_key: str


@dataclass
class Fixture:
    match_id: str
    league_key: str
    league_name: str
    match_date: str
    match_time: str
    commence_time_utc: str
    home_team: str
    away_team: str
    source: str = "the_odds_api"


def parse_match_lines(lines: Iterable[str], default_league_key: str) -> List[MatchRequest]:
    reqs: List[MatchRequest] = []
    for line in lines:
        raw = (line or "").strip()
        if not raw:
            continue

        league_key = default_league_key
        match_part = raw
        if "|" in raw:
            left, right = raw.split("|", 1)
            if left.strip():
                league_key = left.strip()
            match_part = right.strip()

        parts = re.split(r"\s+vs\.?\s+|\s+v\s+", match_part, flags=re.IGNORECASE)
        if len(parts) < 2:
            raise ValueError(f"無法解析比賽輸入: {raw}")
        home = parts[0].strip()
        away = parts[1].strip()
        reqs.append(MatchRequest(raw=raw, home_input=home, away_input=away, league_key=league_key))
    return reqs


def _norm(x: str) -> str:
    x = (x or "").lower().strip()
    x = re.sub(r"[^a-z0-9\u4e00-\u9fff\s]", " ", x)
    return re.sub(r"\s+", " ", x).strip()


def _best_fixture_by_fuzzy(req: MatchRequest, events: list[dict]) -> Optional[dict]:
    best = None
    best_score = 0.0
    best_min_pair = 0.0

    for e in events:
        home = e.get("home_team", "")
        away = e.get("away_team", "")

        d_h = SequenceMatcher(None, _norm(req.home_input), _norm(home)).ratio()
        d_a = SequenceMatcher(None, _norm(req.away_input), _norm(away)).ratio()
        r_h = SequenceMatcher(None, _norm(req.home_input), _norm(away)).ratio()
        r_a = SequenceMatcher(None, _norm(req.away_input), _norm(home)).ratio()

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

    # avoid false positive when only one team matches
    if best_score < 0.65 or best_min_pair < 0.45:
        return None
    return best


def _fetch_league_events(league_key: str) -> list[dict]:
    keys = [
        (settings_v2.odds_api_key or "").strip(),
        (getattr(settings_v2, "odds_api_key_backup", "") or "").strip(),
    ]
    keys = [k for k in keys if k]
    if not keys:
        return []

    url = f"https://api.the-odds-api.com/v4/sports/{league_key}/odds"

    for api_key in keys:
        params = {
            "apiKey": api_key,
            "regions": "eu,uk",
            "markets": "h2h",
            "oddsFormat": "decimal",
        }
        try:
            r = requests.get(url, params=params, timeout=25)
            if r.status_code != 200:
                continue
            data = r.json()
            return data if isinstance(data, list) else []
        except Exception:
            continue

    return []


def resolve_fixtures(requests_list: List[MatchRequest]) -> List[Fixture]:
    fixtures: List[Fixture] = []
    by_league: dict[str, list[dict]] = {}

    for req in requests_list:
        if req.league_key not in by_league:
            by_league[req.league_key] = _fetch_league_events(req.league_key)

        event = _best_fixture_by_fuzzy(req, by_league[req.league_key])

        if event:
            commence = event.get("commence_time", "")
            dt_utc = None
            try:
                dt_utc = datetime.fromisoformat(commence.replace("Z", "+00:00"))
            except Exception:
                dt_utc = datetime.now(timezone.utc)

            fixtures.append(
                Fixture(
                    match_id=str(event.get("id", f"{req.home_input}-{req.away_input}")),
                    league_key=req.league_key,
                    league_name=event.get("sport_title", req.league_key),
                    match_date=dt_utc.date().isoformat(),
                    match_time=dt_utc.strftime("%H:%M"),
                    commence_time_utc=dt_utc.isoformat(),
                    home_team=event.get("home_team", req.home_input),
                    away_team=event.get("away_team", req.away_input),
                    source="the_odds_api",
                )
            )
        else:
            now = datetime.now(timezone.utc)
            fixtures.append(
                Fixture(
                    match_id=f"manual-{_norm(req.home_input)}-vs-{_norm(req.away_input)}",
                    league_key=req.league_key,
                    league_name=req.league_key,
                    match_date=now.date().isoformat(),
                    match_time=now.strftime("%H:%M"),
                    commence_time_utc=now.isoformat(),
                    home_team=req.home_input,
                    away_team=req.away_input,
                    source="manual_input",
                )
            )

    return fixtures


def fixtures_to_csv(fixtures: List[Fixture], out_path: Path) -> pd.DataFrame:
    rows = [
        {
            "match_id": f.match_id,
            "league": f.league_name,
            "league_key": f.league_key,
            "match_date": f.match_date,
            "match_time": f.match_time,
            "commence_time_utc": f.commence_time_utc,
            "home_team": f.home_team,
            "away_team": f.away_team,
            "source": f.source,
        }
        for f in fixtures
    ]
    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    return df
