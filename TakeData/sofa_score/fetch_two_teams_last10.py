#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取兩支球隊最近 10 場（完賽）並補到 data/history_data.csv
可用於快速建立目標對戰的本地樣本。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests


TEAM_LAST_EVENTS_API = "https://www.sofascore.com/api/v1/team/{team_id}/events/last/{page}"
EVENT_SHOTMAP_API = "https://www.sofascore.com/api/v1/event/{event_id}/shotmap"


@dataclass
class MatchRow:
    league: str
    match_date: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    home_shots: int
    away_shots: int
    home_shots_on: int
    away_shots_on: int
    home_corners: int
    away_corners: int
    home_yellow: int
    away_yellow: int
    home_red: int
    away_red: int
    home_fouls: int
    away_fouls: int
    home_poss: int
    away_poss: int
    home_xg_total: float
    away_xg_total: float
    season: str


def fetch_json(url: str, timeout: int = 20) -> Dict:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def season_from_date(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    if d.month >= 8:
        return f"{d.year}-{d.year + 1}"
    return f"{d.year - 1}-{d.year}"


def map_league_name(tournament_name: str, category_name: str) -> str:
    if category_name == "Japan":
        return "J League (Japan)"
    if category_name == "South Korea":
        return "K League 1 (South Korea)"
    if category_name == "Australia":
        return "A-League (Australia)"
    return f"{tournament_name} ({category_name})" if category_name else tournament_name


def parse_shotmap_xg(event_id: int) -> tuple[float, float]:
    try:
        data = fetch_json(EVENT_SHOTMAP_API.format(event_id=event_id))
    except Exception:
        return (0.0, 0.0)

    shots = data.get("shotmap") or []
    hxg = 0.0
    axg = 0.0
    for s in shots:
        try:
            xg = float(s.get("xg", 0) or 0)
        except Exception:
            xg = 0.0
        if bool(s.get("isHome", False)):
            hxg += xg
        else:
            axg += xg

    return (round(hxg, 2), round(axg, 2))


def build_row(event: Dict) -> Optional[MatchRow]:
    status = event.get("status", {})
    if status.get("code") != 100:
        return None

    home_team = (event.get("homeTeam") or {}).get("name")
    away_team = (event.get("awayTeam") or {}).get("name")
    if not home_team or not away_team:
        return None

    hs = (event.get("homeScore") or {}).get("current")
    as_ = (event.get("awayScore") or {}).get("current")
    if hs is None or as_ is None:
        return None

    ts = event.get("startTimestamp")
    if not ts:
        return None
    date_str = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")

    tournament = event.get("tournament", {})
    t_name = tournament.get("name", "")
    c_name = (tournament.get("category") or {}).get("name", "")
    league = map_league_name(t_name, c_name)

    event_id = event.get("id")
    hxg, axg = parse_shotmap_xg(int(event_id)) if event_id is not None else (0.0, 0.0)

    return MatchRow(
        league=league,
        match_date=date_str,
        home_team=home_team,
        away_team=away_team,
        home_goals=int(hs),
        away_goals=int(as_),
        home_shots=0,
        away_shots=0,
        home_shots_on=0,
        away_shots_on=0,
        home_corners=0,
        away_corners=0,
        home_yellow=0,
        away_yellow=0,
        home_red=0,
        away_red=0,
        home_fouls=0,
        away_fouls=0,
        home_poss=50,
        away_poss=50,
        home_xg_total=hxg,
        away_xg_total=axg,
        season=season_from_date(date_str),
    )


def fetch_team_last_events(team_id: int, pages: int = 3) -> List[Dict]:
    """抓取 team 最近賽事（分頁 last/{page}，每頁約 30 場）。"""
    events: List[Dict] = []
    for page in range(pages):
        try:
            data = fetch_json(TEAM_LAST_EVENTS_API.format(team_id=team_id, page=page))
        except Exception:
            break
        page_events = data.get("events") or []
        if not page_events:
            break
        events.extend(page_events)
        if not data.get("hasNextPage", False):
            break
    return events


def merge_history(new_df: pd.DataFrame, history_path: Path) -> pd.DataFrame:
    if history_path.exists():
        base = pd.read_csv(history_path)
    else:
        base = pd.DataFrame(columns=new_df.columns)

    merged = pd.concat([base, new_df], ignore_index=True)
    dedup_cols = ["match_date", "home_team", "away_team", "league"]
    for c in dedup_cols:
        if c not in merged.columns:
            merged[c] = ""
    merged = merged.drop_duplicates(subset=dedup_cols, keep="last")
    return merged


def main():
    parser = argparse.ArgumentParser(description="Fetch last N matches for two teams and merge into history_data.csv")
    parser.add_argument("--home-id", type=int, required=True)
    parser.add_argument("--away-id", type=int, required=True)
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--history", default="data/history_data.csv")
    parser.add_argument("--output", default="data/history_data_two_teams.csv")
    args = parser.parse_args()

    # 每頁約 30 場，抓 2-3 頁足夠覆蓋最近 10 場需求
    pages = 3 if args.n > 10 else 2
    home_events = fetch_team_last_events(args.home_id, pages=pages)
    away_events = fetch_team_last_events(args.away_id, pages=pages)

    # 以 event id 去重，並按時間倒序
    pool: Dict[int, Dict] = {}
    for e in home_events + away_events:
        eid = e.get("id")
        if eid is not None:
            pool[int(eid)] = e

    events = sorted(pool.values(), key=lambda x: x.get("startTimestamp", 0), reverse=True)

    rows = []
    for e in events:
        row = build_row(e)
        if row:
            rows.append(row.__dict__)
        if len(rows) >= args.n * 2:  # 兩隊合計，最多約 20
            break

    if not rows:
        print("NO_DATA")
        return

    df = pd.DataFrame(rows)

    # 保持欄位順序
    ordered = [
        "league", "match_date", "home_team", "away_team",
        "home_goals", "away_goals",
        "home_shots", "away_shots", "home_shots_on", "away_shots_on",
        "home_corners", "away_corners",
        "home_yellow", "away_yellow", "home_red", "away_red",
        "home_fouls", "away_fouls", "home_poss", "away_poss",
        "home_xg_total", "away_xg_total", "season",
    ]
    for c in ordered:
        if c not in df.columns:
            df[c] = 0
    df = df[ordered]

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")

    history_path = Path(args.history)
    merged = merge_history(df, history_path)
    merged.to_csv(history_path, index=False, encoding="utf-8-sig")

    print(f"WROTE {out} rows={len(df)}")
    print(f"MERGED {history_path} rows={len(merged)}")


if __name__ == "__main__":
    main()
