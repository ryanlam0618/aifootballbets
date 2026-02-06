#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
獲取 J1 League (日本J1足球聯賽) 所有球隊列表
API-Football v3
League ID: 98
"""

import sys
import os
import requests
import json

sys.stdout.reconfigure(encoding='utf-8')

# API 配置 (使用 injury_api 中的 KEY)
API_KEY = "147e3f1218fa63de077c346ddac4f5ad"
BASE_URL = "https://v3.football.api-sports.io"

# J1 League ID
J1_LEAGUE_ID = 98  # v3
# J2_LEAGUE_ID = 197

def get_teams_by_league(league_id: int, season: int = 2024) -> dict:
    """獲取指定聯賽的所有球隊"""
    endpoint = f"{BASE_URL}/teams"
    params = {
        "league": league_id,
        "season": season
    }
    headers = {
        "x-apisports-key": API_KEY,
        "x-apisports-host": "v3.football.api-sports.io"
    }

    print(f"🔍 正在獲取聯賽 ID {league_id} 的球隊列表 (2024賽季)...")
    print(f"   URL: {endpoint}")
    print(f"   Params: {params}")

    response = requests.get(endpoint, params=params, headers=headers, timeout=30)

    print(f"   Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"   Response: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}...")
        return data
    else:
        print(f"   Error: {response.text}")
        return {"error": response.text}


def get_league_teams(league_id: int, season: int = 2024) -> list:
    """獲取球隊名單列表"""
    data = get_teams_by_league(league_id, season)

    if "response" in data:
        teams = []
        for item in data["response"]:
            team = item.get("team", {})
            teams.append({
                "id": team.get("id"),
                "name": team.get("name"),
                "code": team.get("code"),
                "country": team.get("country"),
                "founded": team.get("founded"),
                "logo": team.get("logo"),
                "national": team.get("national"),
                "venue": item.get("venue", {}).get("name") if item.get("venue") else None
            })
        return teams
    else:
        print(f"❌ 獲取失敗: {data.get('errors', data)}")
        return []


def print_teams_table(teams: list):
    """以表格形式打印球隊列表"""
    if not teams:
        print("❌ 沒有找到球隊")
        return

    print(f"\n{'='*80}")
    print(f"📋 J1 League 球隊列表 (共 {len(teams)} 隊)")
    print(f"{'='*80}")

    # 打印表頭
    print(f"{'ID':<6} {'名稱':<30} {'代碼':<10} {'主場':<25}")
    print("-" * 80)

    # 按 ID 排序
    teams_sorted = sorted(teams, key=lambda x: x["id"] or 0)

    for team in teams_sorted:
        print(f"{team['id']:<6} {team['name']:<30} {team['code'] or 'N/A':<10} {team['venue'] or 'N/A':<25}")

    print("-" * 80)


def export_to_json(teams: list, filename: str = "j1_teams_2024.json"):
    """導出到 JSON 文件"""
    output_path = os.path.join(os.path.dirname(__file__), "..", "data", "archive", filename)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "league": "J1 League (Japan)",
            "league_id": 98,
            "season": 2024,
            "teams": teams
        }, f, indent=2, ensure_ascii=False)

    print(f"\n💾 已導出到: {output_path}")
    return output_path


def main():
    print("=" * 80)
    print("🏆 API-Football - J1 League 球隊列表獲取工具")
    print("=" * 80)

    # 獲取 J1 球隊 (2024賽季)
    teams = get_league_teams(J1_LEAGUE_ID, 2024)

    if teams:
        print_teams_table(teams)
        export_to_json(teams)

        # 生成 Python TEAM_IDS 字典格式
        print("\n📝 生成的 TEAM_IDS 格式:")
        print("-" * 40)
        for team in sorted(teams, key=lambda x: x["id"] or 0):
            name_lower = team["name"].lower().replace(" ", " ").replace(".", "")
            print(f"    '{name_lower}': {team['id']},")
    else:
        print("❌ 未能獲取球隊列表")


if __name__ == "__main__":
    main()
