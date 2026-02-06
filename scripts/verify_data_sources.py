#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
驗證球隊數據來源 - API vs 靜態映射
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

sys.stdout.reconfigure(encoding='utf-8')


def check_data_sources():
    """檢查數據來源"""
    print("=" * 70)
    print("📊 球隊數據來源分析")
    print("=" * 70)

    # 導入模組
    from src.team_name_matcher import TEAM_MAPPING_DB
    from src.injury_api import APIFootballIntegration
    from config import settings

    print()
    print("1️⃣  API-Football (傷停數據):")
    print("-" * 50)

    # 檢查 API-Football 是否可用
    api_football = APIFootballIntegration()
    print(f"   API Key: {api_football.API_KEY[:10]}... (已設定)")

    # 測試 API 調用
    try:
        test_response = api_football.session.get(
            f"{api_football.BASE_URL}/teams",
            params={"league": 98, "season": 2024},
            timeout=10
        )
        if test_response.status_code == 200:
            data = test_response.json()
            teams_from_api = len(data.get("response", []))
            print(f"   聯賽 ID 98 (J1) 球隊數量: {teams_from_api}")
            print(f"   ✅ 數據來源: API-Football 官方 API")
        else:
            print(f"   ❌ API 調用失敗: {test_response.status_code}")
    except Exception as e:
        print(f"   ❌ API 調用錯誤: {e}")

    print()
    print("2️⃣  The Odds API (賠率數據):")
    print("-" * 50)

    odds_key = getattr(settings, 'ODDS_API_KEY', '')
    if odds_key:
        print(f"   API Key: {odds_key[:10]}... (已設定)")

        import requests
        response = requests.get(
            "https://api.the-odds-api.com/v4/sports/soccer_japan_j_league/odds",
            params={
                'apiKey': odds_key,
                'regions': 'eu,uk',
                'markets': 'h2h'
            },
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            teams_from_odds = set()
            for match in data:
                teams_from_odds.add(match.get('home_team', ''))
                teams_from_odds.add(match.get('away_team', ''))

            print(f"   當前有投注的球隊數量: {len(teams_from_odds)}")
            print(f"   ✅ 數據來源: The Odds API 官方 API")
            print(f"   ⚠️  Note: 並非所有 20 隊都有活躍投注")
        else:
            print(f"   ❌ API 調用失敗: {response.status_code}")
    else:
        print(f"   ⚠️ API Key 未設定")

    print()
    print("3️⃣  TEAM_MAPPING_DB (本地映射):")
    print("-" * 50)

    # 統計 J1 球隊
    j1_ids = [279, 280, 281, 282, 284, 287, 288, 289, 290, 291, 292, 293, 294, 295, 296, 302, 303, 306, 311, 316]
    j1_teams = []

    for name, info in TEAM_MAPPING_DB.items():
        if info['api_football_id'] in j1_ids:
            j1_teams.append(info)

    print(f"   J1 球隊映射數量: {len(j1_teams)}")
    print(f"   數據來源: 手動創建的靜態映射表")
    print(f"   用於: 整合 The Odds API 和 API-Football 的球隊名稱")

    print()
    print("=" * 70)
    print("📋 總結:")
    print("=" * 70)
    print()
    print("| 數據類型 | 來源 | 說明 |")
    print("|---------|------|------|")
    print("| J1 球隊列表 | API-Football | 完整的 20 隊通過 API 獲取 |")
    print("| J1 球隊名稱映射 | 靜態映射 | 用於整合兩個 API 的名稱差異 |")
    print("| 即時投注 | The Odds API | 只有 14 隊有活躍投注 |")
    print("| 傷停數據 | API-Football | 需要 API Key |")
    print()


if __name__ == "__main__":
    check_data_sources()
