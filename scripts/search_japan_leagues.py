#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""搜索日本聯賽正確的 League ID"""

import sys
import requests
import json

from config import settings

sys.stdout.reconfigure(encoding='utf-8')

API_KEY = settings.API_FOOTBALL_KEY
BASE_URL = "https://v3.football.api-sports.io"

if not API_KEY:
    print("Error: API_FOOTBALL_KEY 未配置，請先設定 .env")
    raise SystemExit(1)

# 搜索 Japan 相關聯賽
print("🔍 搜索 Japan 相關聯賽...")
response = requests.get(
    f"{BASE_URL}/leagues",
    params={"country": "Japan"},
    headers={"x-apisports-key": API_KEY}
)

if response.status_code == 200:
    data = response.json()
    print(f"\n找到 {len(data.get('response', []))} 個聯賽:\n")

    for item in data.get("response", []):
        league = item.get("league", {})
        country = item.get("country", {})
        seasons = item.get("seasons", [])

        # 檢查是否有 2024 賽季
        has_2024 = any(s.get("year") == 2024 for s in seasons)

        if has_2024:
            print(f"🏆 {league.get('name')}")
            print(f"   ID: {league.get('id')}")
            print(f"   Type: {league.get('type')}")
            print(f"   Country: {country.get('name')}")
            print()
else:
    print(f"Error: {response.status_code}")
