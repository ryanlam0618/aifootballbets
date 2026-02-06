#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
檢查 The Odds API 返回的 J League 球隊名稱
"""

import sys
import os
import requests
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings

sys.stdout.reconfigure(encoding='utf-8')

# The Odds API 配置
ODDS_API_KEY = getattr(settings, 'ODDS_API_KEY', '')
BASE_URL = "https://api.the-odds-api.com/v4/sports"

# J League Key
J_LEAGUE_KEY = "soccer_japan_j_league"


def get_available_sports():
    """獲取所有可用的體育項目"""
    if not ODDS_API_KEY:
        print("⚠️ 錯誤: 未設定 ODDS_API_KEY")
        return

    print("🔍 獲取所有可用聯賽...")
    response = requests.get(
        f"{BASE_URL}",
        params={'apiKey': ODDS_API_KEY},
        timeout=10
    )

    if response.status_code == 200:
        sports = response.json()
        print(f"\n找到 {len(sports)} 個體育項目\n")

        # 過濾出 Japan 相關
        japan_sports = [s for s in sports if 'japan' in s.get('group', '').lower() or 'japan' in s.get('title', '').lower()]
        print("=" * 60)
        print("🇯🇵 Japan 相關聯賽:")
        print("=" * 60)
        for sport in japan_sports:
            print(f"  Key: {sport['key']}")
            print(f"  Title: {sport['title']}")
            print(f"  Group: {sport['group']}")
            print(f"  Active: {sport['active']}")
            print()
    else:
        print(f"Error: {response.status_code}")


def get_jleague_odds():
    """獲取 J League 投注選項 (會顯示球隊名稱)"""
    if not ODDS_API_KEY:
        print("⚠️ 錯誤: 未設定 ODDS_API_KEY")
        return

    print("\n" + "=" * 60)
    print("⚽ J League 投注市場")
    print("=" * 60)

    response = requests.get(
        f"{BASE_URL}/{J_LEAGUE_KEY}/odds",
        params={
            'apiKey': ODDS_API_KEY,
            'regions': 'eu,uk,us,au',
            'markets': 'h2h',
            'oddsFormat': 'decimal'
        },
        timeout=10
    )

    if response.status_code == 200:
        data = response.json()
        print(f"找到 {len(data)} 場比賽\n")

        teams_seen = set()
        team_mapping = {}

        for match in data:
            home_team = match.get('home_team', '')
            away_team = match.get('away_team', '')
            commence_time = match.get('commence_time', '')

            teams_seen.add(home_team)
            teams_seen.add(away_team)

            team_mapping[home_team] = {
                'id': match.get('id', ''),
                'time': commence_time
            }
            team_mapping[away_team] = {
                'id': match.get('id', ''),
                'time': commence_time
            }

            print(f"🏟️ {home_team} vs {away_team}")
            print(f"   開始時間: {commence_time}")

            # 顯示幾個博彩公司的賠率
            bookmakers = match.get('bookmakers', [])
            if bookmakers:
                bm = bookmakers[0]  # 第一家
                print(f"   Bookmaker: {bm.get('name', 'N/A')}")
                for market in bm.get('markets', []):
                    if market.get('key') == 'h2h':
                        outcomes = market.get('outcomes', [])
                        for o in outcomes:
                            print(f"      {o.get('name', 'N/A')}: {o.get('price', 'N/A')}")
            print()

        print("\n" + "=" * 60)
        print("📋 所有 J League 球隊名稱 (The Odds API):")
        print("=" * 60)
        for i, team in enumerate(sorted(teams_seen), 1):
            print(f"  {i:2}. {team}")
    else:
        print(f"Error: {response.status_code}")
        print(response.text)


def main():
    print("=" * 60)
    print("🔍 The Odds API - J League 球隊名稱檢查")
    print("=" * 60)

    # 1. 先查看所有 Japan 相關聯賽
    get_available_sports()

    # 2. 獲取 J League 球隊名稱
    get_jleague_odds()


if __name__ == "__main__":
    main()
