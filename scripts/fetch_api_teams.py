#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
從 API-Football 獲取五大聯賽球隊 ID
"""

import sys
import os
import json
import urllib.request
import urllib.error
import ssl
import time

API_KEY = "147e3f1218fa63de077c346ddac4f5ad"
BASE_URL = "https://v3.football.api-sports.io"

# 五大聯賽 ID
LEAGUES = {
    "Premier League (England)": 39,
    "La Liga (Spain)": 140,
    "Bundesliga (Germany)": 78,
    "Serie A (Italy)": 135,
    "Ligue 1 (France)": 61,
}

# 2024/25 賽季
SEASON = 2024


def fetch_teams(league_id: int) -> list:
    """從 API 獲取球隊列表"""
    url = f"{BASE_URL}/teams?league={league_id}&season={SEASON}"
    
    headers = {
        "x-apisports-key": API_KEY
    }
    
    try:
        context = ssl.create_default_context()
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=30, context=context)
        result = json.loads(response.read().decode('utf-8'))
        
        if result.get("response"):
            return result["response"]
        else:
            print(f"[WARNING] API Error: {result.get('errors', 'Unknown error')}")
            return []
            
    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTP Error: {e.code} - {e.reason}")
        return []
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        return []


def clean_team_name(name: str) -> str:
    """清理球隊名稱用於 key"""
    import re
    # 移除特殊字符，轉為小寫
    clean = name.lower()
    # 移除常見後綴
    clean = re.sub(r'[^\w\s]', '', clean)
    # 移除多餘空格
    clean = ' '.join(clean.split())
    # 移除空格和連字符
    clean = clean.replace(' ', '').replace('-', '')
    return clean


def main():
    print("=" * 70)
    print("從 API-Football 獲取五大聯賽球隊 ID")
    print("=" * 70)
    
    all_leagues_data = {}
    
    for league_name, league_id in LEAGUES.items():
        print(f"\n[API] Fetching {league_name} (ID: {league_id})...")
        
        teams = fetch_teams(league_id)
        
        if teams:
            # 數據結構: [{"team": {"id": 33, "name": "..."}, "venue": {...}}, ...]
            print(f"   Found {len(teams)} teams")
            all_leagues_data[league_name] = teams
            
            # 打印球隊列表
            for t in teams:
                team_info = t.get("team", {})
                team_id = team_info.get("id")
                team_name = team_info.get("name", "Unknown")
                print(f"   {team_id:5d} | {team_name}")
        else:
            print(f"   [WARNING] Failed to fetch teams")
        
        # 等待一下，避免 rate limit
        print("   [WAIT] 10 seconds to avoid rate limit...")
        time.sleep(10)
    
    # 保存完整數據到 JSON 文件
    output_json = os.path.join(os.path.dirname(__file__), "..", "data", "top5_leagues_teams.json")
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_leagues_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n[OK] JSON saved to: {output_json}")
    print(f"Total leagues: {len(all_leagues_data)}")
    
    # 生成 Python 格式的輸出
    print("\n" + "=" * 70)
    print("Python 格式輸出")
    print("=" * 70)
    
    output_lines = ["# ============================================",
                    "# 五大聯賽球隊 (從 API 獲取)",
                    "# ============================================",
                    "",
                    "TEAM_MAPPING_DB = {"]
    
    for league_name, teams in all_leagues_data.items():
        output_lines.append(f"\n    # {league_name}")
        output_lines.append("")
        
        for t in sorted(teams, key=lambda x: x.get("team", {}).get("name", "")):
            team_info = t.get("team", {})
            team_name = team_info.get("name", "")
            team_id = team_info.get("id", 0)
            key = clean_team_name(team_name)
            
            output_lines.append(f'    "{key}": {{"odds_name": "{team_name}", "api_football_id": {team_id}, "api_name": "{team_name.lower()}"}},')
    
    output_lines.append("}")
    
    # 保存到 txt 文件
    output_txt = os.path.join(os.path.dirname(__file__), "..", "data", "top5_leagues_teams.txt")
    with open(output_txt, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
    
    print(f"[OK] Python format saved to: {output_txt}")
    print(f"\n總共 {sum(len(teams) for teams in all_leagues_data.values())} 支球队")


if __name__ == "__main__":
    main()
