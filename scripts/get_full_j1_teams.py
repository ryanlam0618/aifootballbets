#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
獲取完整的 J1 League (日本J1足球聯賽) 所有球隊列表
The Odds API
"""

import sys
import os
import requests
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings

sys.stdout.reconfigure(encoding='utf-8')

ODDS_API_KEY = getattr(settings, 'ODDS_API_KEY', '')
BASE_URL = "https://api.the-odds-api.com/v4/sports"

J_LEAGUE_KEY = "soccer_japan_j_league"


def get_jleague_matches():
    """獲取 J League 所有比賽"""
    if not ODDS_API_KEY:
        print("⚠️ 錯誤: 未設定 ODDS_API_KEY")
        return []

    print("🔍 正在獲取 J League 球隊列表...")

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
        return data
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return []


def extract_all_teams(matches: list) -> set:
    """從比賽中提取所有球隊名稱"""
    teams = set()
    for match in matches:
        teams.add(match.get('home_team', ''))
        teams.add(match.get('away_team', ''))
    return sorted(teams)


def main():
    print("=" * 70)
    print("⚽ J1 League 完整球隊列表 (The Odds API)")
    print("=" * 70)

    matches = get_jleague_matches()

    if matches:
        teams = extract_all_teams(matches)

        print(f"\n📊 共 {len(teams)} 隊\n")
        print("-" * 70)

        for i, team in enumerate(teams, 1):
            print(f"  {i:2}. {team}")

        print("-" * 70)

        # 導出到 JSON
        output_path = os.path.join(
            os.path.dirname(__file__),
            "..", "data", "archive", "j1_teams_odds_api.json"
        )

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "league": "J1 League (Japan) - The Odds API",
                "league_key": J_LEAGUE_KEY,
                "total_teams": len(teams),
                "teams": list(teams)
            }, f, indent=2, ensure_ascii=False)

        print(f"\n💾 已導出到: {output_path}")
    else:
        print("❌ 未能獲取球隊列表")


if __name__ == "__main__":
    main()
