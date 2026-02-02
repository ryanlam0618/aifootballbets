#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
將所有 MatchPlayerData 整合到主歷史數據庫

用法:
    python combine_all_data.py
"""

import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

# 路徑設定
DATA_DIR = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\data"
BIG_FIVE_HISTORY_PATH = os.path.join(DATA_DIR, "big_five_history.csv")

def standardize_team_name(name):
    """標準化隊名"""
    if pd.isna(name):
        return name
    name = str(name).strip()
    
    mappings = {
        "Manchester City": "Man City",
        "Manchester United": "Man United",
        "Newcastle United": "Newcastle Utd",
        "Tottenham Hotspur": "Tottenham",
        "West Ham United": "West Ham",
        "Wolverhampton Wanderers": "Wolves",
        "Nottingham Forest": "Nott'ham Forest",
        "Brighton & Hove Albion": "Brighton",
        "AFC Bournemouth": "Bournemouth",
    }
    
    reverse = {v: k for k, v in mappings.items()}
    return reverse.get(name, name)


def convert_to_history_format(df):
    """轉換為歷史數據格式"""
    if df.empty:
        return pd.DataFrame()
    
    records = []
    for _, row in df.iterrows():
        home_goals = row.get('home_goals')
        away_goals = row.get('away_goals')
        
        if pd.isna(home_goals) or pd.isna(away_goals):
            continue
        
        # 計算結果
        if home_goals > away_goals:
            ftr = "H"
        elif home_goals < away_goals:
            ftr = "A"
        else:
            ftr = "D"
        
        # 轉換聯賽名稱
        league = row.get('league', '')
        div_mapping = {
            'Premier League': 'Premier League',
            'La Liga': 'La Liga',
            'Serie A': 'Serie A',
            'Bundesliga': 'Bundesliga',
            'Ligue 1': 'Ligue 1',
            'J1League': 'J1 League',
            'ALeague': 'A-League',
        }
        div = div_mapping.get(league, league)
        
        record = {
            "Date": row.get('date', ''),
            "Time": "",
            "Div": div,
            "HomeTeam": standardize_team_name(row.get('home_team', '')),
            "AwayTeam": standardize_team_name(row.get('away_team', '')),
            "FTHG": int(home_goals),
            "FTAG": int(away_goals),
            "FTR": ftr,
            "Season": "",
            "SourceType": "matchplayer",
            # 新增欄位
            "HT_HG": row.get('ht_home_goals'),
            "HT_AG": row.get('ht_away_goals'),
            "HomeCorners": row.get('home_corners'),
            "AwayCorners": row.get('away_corners'),
            "HomeShots": row.get('home_shots'),
            "AwayShots": row.get('away_shots'),
            "HomeShotsOn": row.get('home_shots_on'),
            "AwayShotsOn": row.get('away_shots_on'),
        }
        records.append(record)
    
    return pd.DataFrame(records)


def main():
    print("=" * 60)
    print("整合所有 MatchPlayerData 到歷史數據庫")
    print("=" * 60)
    
    # 讀取現有歷史數據
    print(f"\n📂 讀取現有歷史數據...")
    if os.path.exists(BIG_FIVE_HISTORY_PATH):
        existing_df = pd.read_csv(BIG_FIVE_HISTORY_PATH, encoding='utf-8-sig', low_memory=False)
        print(f"   已載入 {len(existing_df)} 場比賽")
    else:
        existing_df = pd.DataFrame()
        print("   ⚠️ 沒有現有數據，將創建新檔案")
    
    # 讀取各聯賽數據
    data_files = {
        'J1 League': 'j1_league_data.csv',
        'Premier League': 'premier_league_data.csv',
        'European Leagues': 'european_leagues_data.csv'
    }
    
    all_new_data = []
    
    for name, filename in data_files.items():
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.exists(filepath):
            print(f"\n📄 讀取 {name}...")
            df = pd.read_csv(filepath, encoding='utf-8-sig', low_memory=False)
            print(f"   {len(df)} 場比賽")
            
            # 轉換格式
            converted = convert_to_history_format(df)
            all_new_data.append(converted)
    
    if not all_new_data:
        print("\n⚠️ 沒有找到可整合的數據")
        return
    
    # 合併所有新數據
    new_df = pd.concat(all_new_data, ignore_index=True)
    print(f"\n📊 總新數據: {len(new_df)} 場")
    
    # 去除重複 (基於日期和球隊)
    if not existing_df.empty:
        existing_df['MatchKey'] = existing_df['Date'].astype(str) + '_' + \
                                   existing_df['HomeTeam'].astype(str) + '_' + \
                                   existing_df['AwayTeam'].astype(str)
        new_df['MatchKey'] = new_df['Date'].astype(str) + '_' + \
                             new_df['HomeTeam'].astype(str) + '_' + \
                             new_df['AwayTeam'].astype(str)
        
        # 去除重複
        new_df = new_df[~new_df['MatchKey'].str.lower().isin(existing_df['MatchKey'].str.lower())]
        new_df = new_df.drop(columns=['MatchKey'])
        existing_df = existing_df.drop(columns=['MatchKey'])
    
    print(f"   去重後新數據: {len(new_df)} 場")
    
    if len(new_df) == 0:
        print("\n✅ 沒有需要添加的新數據")
        return
    
    # 合併
    combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    
    # 排序
    combined_df['DateSort'] = pd.to_datetime(combined_df['Date'], errors='coerce')
    combined_df = combined_df.sort_values('DateSort', ascending=False)
    combined_df = combined_df.drop(columns=['DateSort'])
    
    # 保存
    combined_df.to_csv(BIG_FIVE_HISTORY_PATH, index=False, encoding='utf-8-sig')
    
    print(f"\n✅ 整合完成！")
    print(f"   總記錄數: {len(combined_df)} 場")
    print(f"   新增記錄: {len(new_df)} 場")
    print(f"   檔案: {BIG_FIVE_HISTORY_PATH}")
    
    # 顯示各聯賽統計
    print(f"\n📊 各聯賽統計:")
    print(combined_df['Div'].value_counts().to_string())


if __name__ == "__main__":
    main()
