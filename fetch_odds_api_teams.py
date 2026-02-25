#!/usr/bin/env python3
"""
從 The Odds API 獲取球隊列表並更新 top5_leagues_teams.json

使用方式:
    python fetch_odds_api_teams.py

需要設置環境變量:
    ODDS_API_KEY=your_api_key_here

或直接在此處設置 API_KEY
"""

import os
import sys
import json
import requests
from datetime import datetime
from typing import Dict, List, Set

# ============================================================
# 請在此處設置你的 API Key (或設置環境變量 ODDS_API_KEY)
# ============================================================
# 從環境變量讀取，如果沒有則使用下面的測試 key
API_KEY = os.getenv("ODDS_API_KEY", "")

# API 端點
ODDS_API_HOST = "https://api.the-odds-api.com"
API_VERSION = "v4"

# 五大聯賽的 sport keys
TOP5_LEAGUES = {
    "soccer_epl": "Premier League (England)",
    "soccer_spain_la_liga": "La Liga (Spain)", 
    "soccer_germany_bundesliga": "Bundesliga (Germany)",
    "soccer_italy_serie_a": "Serie A (Italy)",
    "soccer_france_ligue_one": "Ligue 1 (France)"
}

# 其他聯賽 (可選)
EXTRA_LEAGUES = {
    "soccer_uefa_champs_league": "UEFA Champions League",
    "soccer_uefa_europa_league": "UEFA Europa League",
    "soccer_efl_champ": "Championship (England)",
    "soccer_usa_mls": "MLS (USA)",
    "soccer_brazil_campeonato": "Série A (Brazil)",
    "soccer_japan_j_league": "J League (Japan)",
    "soccer_australia_aleague": "A-League (Australia)"
}


def get_sports(api_key: str) -> List[Dict]:
    """獲取所有育項目可用的體"""
    url = f"{ODDS_API_HOST}/{API_VERSION}/sports/"
    params = {"apiKey": api_key}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching sports: {e}")
        return []


def get_upcoming_events(sport_key: str, api_key: str, regions: str = "us,eu", max_events: int = 50) -> List[Dict]:
    """獲取即將進行的比賽"""
    url = f"{ODDS_API_HOST}/{API_VERSION}/sports/{sport_key}/odds/"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "oddsFormat": "decimal",
        "dateFormat": "iso"
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # 返回前 max_events 場比賽
        return data[:max_events] if isinstance(data, list) else []
    except requests.exceptions.RequestException as e:
        print(f"  Error fetching odds for {sport_key}: {e}")
        return []


def extract_teams_from_events(events: List[Dict]) -> Set[str]:
    """從比賽列表中提取唯一的球隊名稱"""
    teams = set()
    for event in events:
        home_team = event.get("home_team", "")
        away_team = event.get("away_team", "")
        if home_team:
            teams.add(home_team)
        if away_team:
            teams.add(away_team)
    return teams


def fetch_all_teams(api_key: str, leagues: Dict[str, str], max_events_per_league: int = 100) -> Dict[str, Dict]:
    """獲取所有聯賽的球隊"""
    all_teams = {}
    
    print("=" * 60)
    print("從 The Odds API 獲取球隊列表")
    print("=" * 60)
    
    # 先測試 API 連接
    print("\n[1/3] 測試 API 連接...")
    sports = get_sports(api_key)
    if not sports:
        print("無法獲取體育項目，請檢查 API Key 是否正確")
        return {}
    print(f"  ✅ API 連接成功，找到 {len(sports)} 個體育項目")
    
    print(f"\n[2/3] 獲取 {len(leagues)} 個聯賽的球隊...")
    
    for i, (sport_key, league_name) in enumerate(leagues.items(), 1):
        print(f"  [{i}/{len(leagues)}] 正在獲取: {league_name} ({sport_key})")
        
        events = get_upcoming_events(sport_key, api_key, max_events=max_events_per_league)
        
        if events:
            teams = extract_teams_from_events(events)
            all_teams[sport_key] = {
                "league_name": league_name,
                "teams": {team: {"name": team, "odds_api_key": sport_key} for team in sorted(teams)}
            }
            print(f"      ✅ 找到 {len(teams)} 支球隊")
        else:
            # 如果沒有 upcoming events，嘗試獲取所有 events
            print(f"      ⚠️ 沒有即時數據，嘗試獲取更多比赛...")
            events = get_upcoming_events(sport_key, api_key, max_events=200)
            if events:
                teams = extract_teams_from_events(events)
                all_teams[sport_key] = {
                    "league_name": league_name,
                    "teams": {team: {"name": team, "odds_api_key": sport_key} for team in sorted(teams)}
                }
                print(f"      ✅ 找到 {len(teams)} 支球隊 (擴大範圍)")
            else:
                print(f"      ❌ 無法獲取數據")
                # 創建空結構
                all_teams[sport_key] = {
                    "league_name": league_name,
                    "teams": {}
                }
    
    print(f"\n[3/3] 總結:")
    total_teams = sum(len(data["teams"]) for data in all_teams.values())
    print(f"  - 聯賽數量: {len(all_teams)}")
    print(f"  - 總球隊數: {total_teams}")
    
    return all_teams


def merge_with_existing(new_teams: Dict, existing_file: str) -> Dict:
    """合併新數據與現有數據，保留現有數據中的額外字段"""
    if not os.path.exists(existing_file):
        return new_teams
    
    try:
        with open(existing_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)
    except:
        return new_teams
    
    # 合併
    for league_key, league_data in new_teams.items():
        if league_key in existing:
            # 合併球隊，保留現有的額外信息
            existing_teams = existing[league_key].get("teams", {})
            new_teams_list = league_data.get("teams", {})
            
            for team_name, team_info in new_teams_list.items():
                if team_name not in existing_teams:
                    existing_teams[team_name] = team_info
                else:
                    # 保留現有的 odds_api_key 等信息
                    existing_teams[team_name]["odds_api_key"] = team_info.get("odds_api_key")
            
            new_teams[league_key]["teams"] = existing_teams
    
    return new_teams


def save_teams_to_json(teams_data: Dict, output_file: str):
    """保存球隊數據到 JSON 檔案"""
    # 確保目錄存在
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(teams_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 數據已保存到: {output_file}")


def main():
    # 檢查 API Key
    api_key = os.getenv("ODDS_API_KEY", "")
    
    if not api_key:
        print("錯誤: 請設置 ODDS_API_KEY 環境變量")
        print("或在此腳本中設置 API_KEY 變量")
        print("\n使用方法:")
        print("  1. 設置環境變量: set ODDS_API_KEY=your_key")
        print("  2. 或編輯此腳本直接設置 API_KEY")
        
        # 嘗試從 config 導入
        try:
            from config import settings
            api_key = settings.ODDS_API_KEY
            if api_key:
                print(f"\n✅ 從 config.py 找到 API Key")
            else:
                print("\n❌ config.py 中也沒有 API Key")
                return
        except ImportError:
            pass
    
    if not api_key:
        print("\n❌ 沒有找到 API Key，無法繼續")
        return
    
    print(f"API Key: {api_key[:10]}..." if len(api_key) > 10 else api_key)
    
    # 輸出檔案路徑
    output_file = "data/top5_leagues_teams.json"
    
    # 合併所有要獲取的聯賽
    all_leagues = {**TOP5_LEAGUES, **EXTRA_LEAGUES}
    
    # 獲取球隊數據
    teams_data = fetch_all_teams(api_key, all_leagues)
    
    if not teams_data:
        print("無法獲取球隊數據")
        return
    
    # 嘗試與現有數據合併
    teams_data = merge_with_existing(teams_data, output_file)
    
    # 保存到 JSON
    save_teams_to_json(teams_data, output_file)
    
    # 顯示結果
    print("\n" + "=" * 60)
    print("獲取的球隊列表:")
    print("=" * 60)
    for league_key, data in teams_data.items():
        print(f"\n{data['league_name']} ({league_key}):")
        teams = list(data["teams"].keys())
        if len(teams) <= 10:
            print(f"  {', '.join(teams)}")
        else:
            print(f"  {', '.join(teams[:10])} ... (+{len(teams)-10} more)")


if __name__ == "__main__":
    main()
