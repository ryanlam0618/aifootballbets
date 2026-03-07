#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""獲取 J2 League 球隊列表"""

import sys
import os
import requests
import json

from config import settings

sys.stdout.reconfigure(encoding='utf-8')

API_KEY = settings.API_FOOTBALL_KEY
BASE_URL = "https://v3.football.api-sports.io"
J2_LEAGUE_ID = 99  # v3 - 正確的日本J2聯賽ID

if not API_KEY:
    print("Error: API_FOOTBALL_KEY 未配置，請先設定 .env")
    raise SystemExit(1)

response = requests.get(
    f"{BASE_URL}/teams",
    params={"league": J2_LEAGUE_ID, "season": 2024},
    headers={"x-apisports-key": API_KEY}
)

if response.status_code == 200:
    data = response.json()
    print(f"\nJ2 League Teams (2024) - Total: {len(data.get('response', []))}")
    print("-" * 50)
    for item in sorted(data["response"], key=lambda x: x["team"]["id"]):
        t = item["team"]
        print(f"{t['id']}: {t['name']}")

    # Export to JSON
    with open("data/archive/j2_teams_2024.json", "w", encoding="utf-8") as f:
        json.dump({
            "league": "J2 League (Japan)",
            "league_id": 99,
            "season": 2024,
            "teams": [{"id": t["team"]["id"], "name": t["team"]["name"]} for t in data["response"]]
        }, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Exported to data/archive/j2_teams_2024.json")
else:
    print(f"Error: {response.status_code}")
