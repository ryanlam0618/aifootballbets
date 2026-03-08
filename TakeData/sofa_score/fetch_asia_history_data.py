#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取日本/韓國/澳洲歷史賽事並轉成 history_data.csv 格式所需欄位。

特點：
- 不依賴 DrissionPage（純 requests）
- 使用 SofaScore 官方公開 API
- 只抓已完賽比賽（status.code == 100）
- 生成輸出：data/history_data_asia.csv

用途：
- 補足 AI_FOOTBALL_BETS 在 J/K/A 聯賽的歷史樣本，避免 xG 樣本=0。
"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests


SOFA_SCHEDULED_EVENTS = "https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date}"
SOFA_EVENT_SHOTMAP = "https://www.sofascore.com/api/v1/event/{event_id}/shotmap"


TARGET_LEAGUES = {
    # 日本（含分組命名）
    ("J1 League", "Japan"): "J League (Japan)",
    ("J1 League, East", "Japan"): "J League (Japan)",
    ("J1 League, West", "Japan"): "J League (Japan)",

    # 韓國
    ("K League 1", "South Korea"): "K League 1 (South Korea)",

    # 澳洲
    ("A-League Men", "Australia"): "A-League (Australia)",
}


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
    d = dt.datetime.strptime(date_str, "%Y-%m-%d")
    # 歐亞聯賽一般跨年賽季：8 月起算新賽季
    if d.month >= 8:
        y1 = d.year
        y2 = d.year + 1
    else:
        y1 = d.year - 1
        y2 = d.year
    return f"{y1}-{y2}"


def parse_shotmap_xg(event_id: int) -> tuple[float, float]:
    """從 shotmap 聚合主客 xG。失敗時回傳 (None, None)。"""
    try:
        data = fetch_json(SOFA_EVENT_SHOTMAP.format(event_id=event_id))
    except Exception:
        return (None, None)

    shots = data.get("shotmap") or []
    home_xg = 0.0
    away_xg = 0.0

    for s in shots:
        try:
            xg = float(s.get("xg", 0) or 0)
        except Exception:
            xg = 0.0
        is_home = bool(s.get("isHome", False))
        if is_home:
            home_xg += xg
        else:
            away_xg += xg

    # 保留兩位小數
    return (round(home_xg, 2), round(away_xg, 2))


def build_row_from_event(event: Dict, date_str: str) -> Optional[MatchRow]:
    tournament = event.get("tournament", {})
    t_name = tournament.get("name")
    c_name = (tournament.get("category") or {}).get("name")

    league = TARGET_LEAGUES.get((t_name, c_name))
    if not league:
        return None

    status = event.get("status", {})
    if status.get("code") != 100:  # finished only
        return None

    home_team = (event.get("homeTeam") or {}).get("name")
    away_team = (event.get("awayTeam") or {}).get("name")
    if not home_team or not away_team:
        return None

    hs = (event.get("homeScore") or {}).get("current")
    as_ = (event.get("awayScore") or {}).get("current")
    if hs is None or as_ is None:
        return None

    event_id = event.get("id")
    home_xg, away_xg = (None, None)
    if event_id is not None:
        home_xg, away_xg = parse_shotmap_xg(int(event_id))

    # 其餘統計欄位暫時保守填 0（可後續再由 statistics API 補強）
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
        home_xg_total=float(home_xg) if home_xg is not None else 0.0,
        away_xg_total=float(away_xg) if away_xg is not None else 0.0,
        season=season_from_date(date_str),
    )


def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def fetch_range(start_date: str, end_date: str) -> List[MatchRow]:
    start = dt.datetime.strptime(start_date, "%Y-%m-%d").date()
    end = dt.datetime.strptime(end_date, "%Y-%m-%d").date()

    rows: List[MatchRow] = []

    for d in daterange(start, end):
        ds = d.strftime("%Y-%m-%d")
        url = SOFA_SCHEDULED_EVENTS.format(date=ds)
        try:
            data = fetch_json(url)
        except Exception:
            continue

        events = data.get("events") or []
        for e in events:
            row = build_row_from_event(e, ds)
            if row:
                rows.append(row)

    return rows


def merge_into_history(base_history_csv: Path, new_rows_df: pd.DataFrame) -> pd.DataFrame:
    if base_history_csv.exists():
        base = pd.read_csv(base_history_csv)
    else:
        base = pd.DataFrame(columns=new_rows_df.columns)

    merged = pd.concat([base, new_rows_df], ignore_index=True)

    # 去重 key：日期 + 主客隊 + 聯賽
    dedup_cols = ["match_date", "home_team", "away_team", "league"]
    for c in dedup_cols:
        if c not in merged.columns:
            merged[c] = ""

    merged = merged.drop_duplicates(subset=dedup_cols, keep="last")
    return merged


def main():
    parser = argparse.ArgumentParser(description="Fetch Asia history data from SofaScore API")
    parser.add_argument("--start", default="2025-08-01", help="start date YYYY-MM-DD")
    parser.add_argument("--end", default=dt.date.today().strftime("%Y-%m-%d"), help="end date YYYY-MM-DD")
    parser.add_argument("--output", default="data/history_data_asia.csv", help="output CSV path")
    parser.add_argument("--merge-history", action="store_true", help="merge into data/history_data.csv")
    args = parser.parse_args()

    rows = fetch_range(args.start, args.end)
    df = pd.DataFrame([r.__dict__ for r in rows])

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    if df.empty:
        print("NO_DATA")
        return

    # 保證欄位順序與現有 history_data.csv 一致
    ordered_cols = [
        "league", "match_date", "home_team", "away_team",
        "home_goals", "away_goals",
        "home_shots", "away_shots", "home_shots_on", "away_shots_on",
        "home_corners", "away_corners",
        "home_yellow", "away_yellow", "home_red", "away_red",
        "home_fouls", "away_fouls", "home_poss", "away_poss",
        "home_xg_total", "away_xg_total", "season",
    ]

    for c in ordered_cols:
        if c not in df.columns:
            df[c] = 0

    df = df[ordered_cols]
    df.to_csv(out, index=False, encoding="utf-8-sig")

    print(f"WROTE {out} rows={len(df)}")

    if args.merge_history:
        history_path = Path("data/history_data.csv")
        merged = merge_into_history(history_path, df)
        merged.to_csv(history_path, index=False, encoding="utf-8-sig")
        print(f"MERGED {history_path} rows={len(merged)}")


if __name__ == "__main__":
    main()
