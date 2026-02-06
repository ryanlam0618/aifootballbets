#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
互動式球隊匹配測試 - 輸入主客隊，自動匹配兩個 API 的 ID
"""

import sys
import os
from src.team_name_matcher import match_teams, get_team_info

sys.stdout.reconfigure(encoding='utf-8')


def print_team_info(team_name: str, label: str):
    """打印球隊信息"""
    info = get_team_info(team_name)

    print(f"   {label}:")
    print(f"      The Odds API: {info['odds_name']}")
    print(f"      API-Football ID: {info['api_football_id']}")
    print(f"      API-Football Name: {info['api_name']}")
    print(f"      Match Source: {info['source']}")

    return info


def main():
    print("=" * 70)
    print("⚽ 球隊名稱匹配器 - 互動測試")
    print("=" * 70)
    print()
    print("輸入格式: 主隊名稱,客隊名稱")
    print("範例: Cerezo Osaka,Gamba Osaka")
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
            if len(parts) != 2:
                print("⚠️  格式錯誤，請輸入兩個球隊名稱")
                continue

            home_team = parts[0].strip()
            away_team = parts[1].strip()

            if not home_team or not away_team:
                print("⚠️  球隊名稱不能為空")
                continue

            print()
            print("-" * 70)
            print(f"🔍 匹配結果: {home_team} vs {away_team}")
            print("-" * 70)

            home_info = print_team_info(home_team, "主隊 (Home)")
            print()
            away_info = print_team_info(away_team, "客隊 (Away)")

            print()
            print("=" * 70)
            print("✅ API 調用準備完成:")
            print(f"   The Odds API: {home_info['odds_name']} vs {away_info['odds_name']}")
            print(f"   API-Football: ID {home_info['api_football_id']} vs ID {away_info['api_football_id']}")
            print("=" * 70)
            print()

        except KeyboardInterrupt:
            print("\n👋 退出")
            break
        except Exception as e:
            print(f"❌ 錯誤: {e}")


if __name__ == "__main__":
    main()
