#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
球隊名稱整合測試 - 整合 The Odds API 和 API-Football
輸入主客隊，自動找出兩個 API 的 ID
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.team_name_matcher import match_teams, get_team_info
from src.injury_api import InjuryDataAggregator
from src.data_modules import RealOddsFetcher

sys.stdout.reconfigure(encoding='utf-8')


def test_injury_data(home_team: str, away_team: str):
    """測試獲取傷停數據"""
    print("\n🏥 測試 API-Football 傷停數據:")
    print("-" * 50)

    try:
        injury_aggregator = InjuryDataAggregator()

        # 使用 API-Football ID 獲取傷停
        home_id = get_api_football_id(home_team)
        away_id = get_api_football_id(away_team)

        if home_id:
            home_data = injury_aggregator.api_football.get_team_injuries(
                home_team, league_id=98, season=2024
            )
            print(f"   {home_team}: {home_data}")

        if away_id:
            away_data = injury_aggregator.api_football.get_team_injuries(
                away_team, league_id=98, season=2024
            )
            print(f"   {away_team}: {away_data}")

    except Exception as e:
        print(f"   傷停數據獲取失敗: {e}")


def get_api_football_id(team_name: str) -> int:
    """獲取 API-Football ID"""
    info = get_team_info(team_name)
    return info.get("api_football_id")


def main():
    print("=" * 70)
    print("⚽ 球隊名稱整合測試")
    print("   整合 The Odds API 和 API-Football")
    print("=" * 70)
    print()
    print("輸入格式: 主隊名稱,客隊名稱")
    print("範例: Cerezo Osaka,Gamba Osaka")
    print("範例: Urawa Red Diamonds,Kashima Antlers")
    print("範例: Liverpool,Arsenal")
    print("輸入 'q' 退出")
    print()

    while True:
        try:
            user_input = input("🏟️ 請輸入球隊 (主隊,客隊): ").strip()

            if user_input.lower() == 'q':
                print("👋 再见!")
                break

            if ',' not in user_input:
                print("⚠️  格式錯誤，請使用逗號分隔主客隊")
                continue

            parts = user_input.split(',')
            home_team = parts[0].strip()
            away_team = parts[1].strip()

            if not home_team or not away_team:
                print("⚠️  球隊名稱不能為空")
                continue

            print()
            print("=" * 70)
            print(f"🔍 匹配結果: {home_team} vs {away_team}")
            print("=" * 70)

            # 匹配球隊
            result = match_teams(home_team, away_team)

            # 主隊信息
            print(f"\n📌 主隊 (Home): {home_team}")
            print(f"   ✅ The Odds API: {result['home']['odds_name']}")
            print(f"   🆔 API-Football ID: {result['home']['api_football_id']}")
            print(f"   📛 API-Football Name: {result['home']['api_name']}")
            print(f"   📍 Match Source: {result['home']['source']}")

            # 客隊信息
            print(f"\n📌 客隊 (Away): {away_team}")
            print(f"   ✅ The Odds API: {result['away']['odds_name']}")
            print(f"   🆔 API-Football ID: {result['away']['api_football_id']}")
            print(f"   📛 API-Football Name: {result['away']['api_name']}")
            print(f"   📍 Match Source: {result['away']['source']}")

            # 整合結果
            print()
            print("=" * 70)
            print("📊 API 調用準備完成:")
            print("=" * 70)
            print(f"\n🏈 The Odds API 調用:")
            print(f"   home_team = \"{result['home']['odds_name']}\"")
            print(f"   away_team = \"{result['away']['odds_name']}\"")

            print(f"\n🏥 API-Football 調用:")
            print(f"   home_id = {result['home']['api_football_id']}")
            print(f"   away_id = {result['away']['api_football_id']}")

            print()
            print("=" * 70)

        except KeyboardInterrupt:
            print("\n👋 退出")
            break
        except Exception as e:
            print(f"❌ 錯誤: {e}")


if __name__ == "__main__":
    main()
