#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
將五大聯賽的比賽數據合并到 big_five_history.csv
"""

import os
import pandas as pd
import glob

from datetime import datetime

# 路徑設定
MATCH_DATA_DIR = r"c:/Users/Ryan/Documents/data/五大联赛数据/比赛数据"
BIG_FIVE_HISTORY_PATH = r"c:/Users/Ryan/python/.vscode/fb_ai_bets/data/big_five_history.csv"

# 聯賽映射 (matchlog 的 Comp 值 -> big_five_history 的 Div 值)
LEAGUE_MAP = {
    "Bundesliga": "Bundesliga",
    "La Liga": "La Liga",
    "Ligue 1": "Ligue 1",
    "Premier League": "Premier League",
    "Serie A": "Serie A",
    "DFB-Pokal": "DFB-Pokal",
    "Copa del Rey": "Copa del Rey",
    "Coupe de France": "Coupe de France",
    "FA Cup": "FA Cup",
    "League Cup": "League Cup",
    "Coppa Italia": "Coppa Italia",
    "Supercopa": "Supercopa",
    "Trophée des Champions": "Trophée des Champions",
    "DFL-Supercup": "DFL-Supercup",
    "Community Shield": "Community Shield",
}

# 需要過濾的杯賽 (只保留聯賽)
LEAGUE_ONLY = ["Bundesliga", "La Liga", "Ligue 1", "Premier League", "Serie A"]


def get_league_from_path(path):
    """從路徑獲取聯賽名稱"""
    parts = path.split(os.sep)
    for part in parts:
        if part in ["Bundesliga", "La-Liga", "Ligue-1", "Premier-League", "Serie-A"]:
            return part.replace("-", " ")
    return "Unknown"


def read_all_matchlogs():
    """讀取所有 matchlog 文件"""
    all_matches = []
    
    # 遍歷所有聯賽文件夾
    for league_folder in os.listdir(MATCH_DATA_DIR):
        league_path = os.path.join(MATCH_DATA_DIR, league_folder)
        if not os.path.isdir(league_path):
            continue
            
        # 遍歷所有球隊文件夾
        for team_folder in os.listdir(league_path):
            team_path = os.path.join(league_path, team_folder)
            if not os.path.isdir(team_path):
                continue
                
            # 遍歷該球隊的所有 matchlog 文件
            for matchlog_file in glob.glob(os.path.join(team_path, "*_matchlog.csv")):
                try:
                    df = pd.read_csv(matchlog_file, encoding='utf-8')
                    if "Season" in df.columns and "Date" in df.columns:
                        df["SourceFile"] = matchlog_file
                        df["TeamFolder"] = team_folder
                        all_matches.append(df)
                except Exception as e:
                    print(f"⚠️ 讀取失敗: {matchlog_file} - {e}")
    
    if all_matches:
        return pd.concat(all_matches, ignore_index=True)
    return pd.DataFrame()


def normalize_team_name(name):
    """標準化球隊名稱"""
    if pd.isna(name):
        return name
    name = str(name).strip()
    
    # 常見的標準化映射
    name_mappings = {
        "Manchester City": ["Man City"],
        "Manchester United": ["Man United"],
        "Newcastle United": ["Newcastle Utd", "Newcastle"],
        "Tottenham Hotspur": ["Tottenham"],
        "West Ham United": ["West Ham"],
        "Wolverhampton Wanderers": ["Wolves", "Wolverhampton"],
        "Nottingham Forest": ["Nott'ham Forest", "Notts Forest"],
        "Leicester City": ["Leicester"],
        "Leeds United": ["Leeds"],
        "Sheffield United": ["Sheffield United", "Sheffield Utd"],
        "Crystal Palace": ["Crystal Palace"],
        "Brighton & Hove Albion": ["Brighton"],
        "AFC Bournemouth": ["Bournemouth"],
        "Aston Villa": ["Aston Villa"],
        "Bayern Munich": ["Bayern Munich", "Bayern"],
        "Eintracht Frankfurt": ["Eint Frankfurt"],
        "Borussia Dortmund": ["Dortmund"],
        "VfB Stuttgart": ["Stuttgart"],
        "Borussia M'gladbach": ["Gladbach"],
        "RB Leipzig": ["RB Leipzig"],
        "SC Freiburg": ["Freiburg"],
        "TSG Hoffenheim": ["Hoffenheim"],
        "VfL Wolfsburg": ["Wolfsburg"],
        "VfL Bochum": ["Bochum"],
        "1. FC Heidenheim": ["Heidenheim"],
        "1. FSV Mainz 05": ["Mainz 05"],
        "SV Werder Bremen": ["Werder Bremen"],
        "Holstein Kiel": ["Holstein Kiel"],
        "FC Augsburg": ["Augsburg"],
        "Union Berlin": ["Union Berlin"],
        "FC St. Pauli": ["St. Pauli"],
        "Real Madrid": ["Real Madrid"],
        "FC Barcelona": ["Barcelona"],
        "Atlético Madrid": ["Atlético Madrid", "Atlético"],
        "Sevilla FC": ["Sevilla"],
        "Villarreal CF": ["Villarreal"],
        "Real Sociedad": ["Real Sociedad"],
        "Athletic Club": ["Athletic Club", "Athletic"],
        "Real Betis": ["Betis"],
        "Girona FC": ["Girona"],
        "Valencia CF": ["Valencia"],
        "CA Osasuna": ["Osasuna"],
        "Celta de Vigo": ["Celta Vigo"],
        "Rayo Vallecano": ["Rayo Vallecano"],
        "Deportivo Alavés": ["Alavés"],
        "RCD Mallorca": ["Mallorca"],
        "Getafe CF": ["Getafe"],
        "CD Leganés": ["Leganés"],
        "Real Valladolid": ["Valladolid"],
        "RCD Espanyol": ["Espanyol"],
        "Paris Saint-Germain": ["Paris S-G", "Paris SG", "PSG"],
        "Olympique Lyonnais": ["Lyon"],
        "Olympique de Marseille": ["Marseille"],
        "AS Monaco": ["Monaco"],
        "LOSC Lille": ["Lille"],
        "Stade Rennais": ["Rennes"],
        "OGC Nice": ["Nice"],
        "RC Lens": ["Lens"],
        "FC Nantes": ["Nantes"],
        "Stade de Reims": ["Reims"],
        "Montpellier HSC": ["Montpellier"],
        "FC Lorient": ["Lorient"],
        "Stade Brestois 29": ["Brest"],
        "Toulouse FC": ["Toulouse"],
        "Le Havre AC": ["Le Havre"],
        "AJ Auxerre": ["Auxerre"],
        "Angers SCO": ["Angers"],
        "FC Girondins de Bordeaux": ["Bordeaux"],
        "AS Saint-Étienne": ["Saint-Étienne"],
        "RC Strasbourg Alsace": ["Strasbourg"],
        "FC Internazionale": ["Inter"],
        "AC Milan": ["Milan"],
        "Juventus FC": ["Juventus"],
        "AS Roma": ["Roma"],
        "SS Lazio": ["Lazio"],
        "SSC Napoli": ["Napoli"],
        "Atalanta BC": ["Atalanta"],
        "ACF Fiorentina": ["Fiorentina"],
        "Torino FC": ["Torino"],
        "Bologna FC": ["Bologna"],
        "Udinese Calcio": ["Udinese"],
        "US Sassuolo": ["Sassuolo"],
        "US Lecce": ["Lecce"],
        "Hellas Verona": ["Hellas Verona"],
        "Empoli FC": ["Empoli"],
        "Cagliari Calcio": ["Cagliari"],
        "US Salernitana": ["Salernitana"],
        "Spezia Calcio": ["Spezia"],
        "UC Sampdoria": ["Sampdoria"],
        "Genoa CFC": ["Genoa"],
        "Venezia FC": ["Venezia"],
        "FC Como": ["Como"],
        "US Cremonese": ["Cremonese"],
        "Parma Calcio": ["Parma"],
        "FC Monza": ["Monza"],
    }
    
    return name_mappings.get(name, name)


def convert_matchlog_to_history_format(df):
    """將 matchlog 數據轉換為 big_five_history 格式"""
    if df.empty:
        return pd.DataFrame()
    
    matches = []
    
    for _, row in df.iterrows():
        # 只處理聯賽
        comp = row.get("Comp", "")
        if comp not in LEAGUE_ONLY:
            continue
            
        season = row.get("Season", "")
        match_date = row.get("Date", "")
        match_time = row.get("Time", "")
        venue = row.get("Venue", "")
        result = row.get("Result", "")
        gf = row.get("GF", 0)
        ga = row.get("GA", 0)
        opponent = row.get("Opponent", "")
        team_folder = row.get("TeamFolder", "")
        
        if venue == "Home":
            # 主場比賽
            home_team = normalize_team_name(team_folder)
            away_team = normalize_team_name(opponent)
            home_goals = gf
            away_goals = ga
        else:
            # 客場比賽
            home_team = normalize_team_name(opponent)
            away_team = normalize_team_name(team_folder)
            home_goals = ga
            away_goals = gf
        
        # 根據結果設置 Full Time Result
        if home_goals > away_goals:
            ftr = "H"
        elif home_goals < away_goals:
            ftr = "A"
        else:
            ftr = "D"
        
        # 解析時間
        time_str = str(match_time) if pd.notna(match_time) else ""
        if "(" in time_str:
            time_str = time_str.split("(")[0].strip()
        
        match_record = {
            "Div": comp,
            "Date": match_date,
            "Time": time_str,
            "HomeTeam": home_team,
            "AwayTeam": away_team,
            "FTHG": home_goals,
            "FTAG": away_goals,
            "FTR": ftr,
            "Season": season,
        }
        matches.append(match_record)
    
    return pd.DataFrame(matches)


def find_new_matches(new_df, existing_df):
    """找出在新數據中存在但不在現有數據中的比賽"""
    if new_df.empty or existing_df.empty:
        return new_df
    
    # 創建唯一標識符
    new_df["MatchKey"] = new_df["Date"].astype(str) + "_" + new_df["HomeTeam"].astype(str) + "_" + new_df["AwayTeam"].astype(str)
    existing_df["MatchKey"] = existing_df["Date"].astype(str) + "_" + existing_df["HomeTeam"].astype(str) + "_" + existing_df["AwayTeam"].astype(str)
    
    # 找出新的比賽
    existing_keys = set(existing_df["MatchKey"].str.lower())
    new_matches = new_df[~new_df["MatchKey"].str.lower().isin(existing_keys)]
    
    return new_matches.drop(columns=["MatchKey"])


def main():
    print("=" * 60)
    print("五大聯賽數據合并工具")
    print("=" * 60)
    
    # 1. 讀取現有的 big_five_history.csv
    print(f"\n📂 讀取現有數據: {BIG_FIVE_HISTORY_PATH}")
    if os.path.exists(BIG_FIVE_HISTORY_PATH):
        try:
            existing_df = pd.read_csv(BIG_FIVE_HISTORY_PATH, encoding='utf-8-sig', low_memory=False)
            print(f"   已載入 {len(existing_df)} 場比賽記錄")
        except UnicodeDecodeError:
            existing_df = pd.read_csv(BIG_FIVE_HISTORY_PATH, encoding='latin-1', low_memory=False)
            print(f"   已載入 {len(existing_df)} 場比賽記錄")
    else:
        print(f"   ⚠️ 文件不存在: {BIG_FIVE_HISTORY_PATH}")
        existing_df = pd.DataFrame()
    
    # 2. 讀取所有 matchlog 文件
    print(f"\n📂 讀取 matchlog 數據: {MATCH_DATA_DIR}")
    matchlog_df = read_all_matchlogs()
    if not matchlog_df.empty:
        print(f"   已載入 {len(matchlog_df)} 條 matchlog 記錄")
    else:
        print("   ⚠️ 未找到任何 matchlog 文件")
        return
    
    # 3. 轉換為歷史數據格式
    print("\n🔄 轉換數據格式...")
    new_history_df = convert_matchlog_to_history_format(matchlog_df)
    if not new_history_df.empty:
        print(f"   轉換後的聯賽記錄: {len(new_history_df)} 場")
    else:
        print("   ⚠️ 轉換後無有效數據")
        return
    
    # 4. 找出新的比賽
    print("\n🔍 比對數據...")
    unique_matches = new_history_df.drop_duplicates(subset=["Date", "HomeTeam", "AwayTeam"])
    print(f"   去重後的記錄: {len(unique_matches)} 場")
    
    new_matches = find_new_matches(unique_matches, existing_df)
    print(f"   新發現的比賽: {len(new_matches)} 場")
    
    if new_matches.empty:
        print("\n✅ 沒有需要添加的新數據")
        return
    
    # 5. 顯示新數據的詳細信息
    print("\n📋 新數據預覽:")
    print("-" * 60)
    for _, row in new_matches.head(10).iterrows():
        print(f"   {row['Date']} | {row['Div']} | {row['HomeTeam']} vs {row['AwayTeam']} ({row['FTHG']}-{row['FTAG']})")
    if len(new_matches) > 10:
        print(f"   ... 以及其他 {len(new_matches) - 10} 場比賽")
    
    # 6. 添加到現有數據
    print("\n" + "=" * 60)
    confirm = input(f"確定要將 {len(new_matches)} 場新比賽添加到 big_five_history.csv 嗎? (y/n): ")
    
    if confirm.lower() == "y":
        # 合并數據
        combined_df = pd.concat([existing_df, new_matches], ignore_index=True)
        
        # 排序
        combined_df["DateSort"] = pd.to_datetime(combined_df["Date"], errors='coerce')
        combined_df = combined_df.sort_values("DateSort", ascending=False)
        combined_df = combined_df.drop(columns=["DateSort"])
        
        # 保存
        combined_df.to_csv(BIG_FIVE_HISTORY_PATH, index=False, encoding='utf-8-sig')
        print(f"\n✅ 成功添加 {len(new_matches)} 場比賽!")
        print(f"   總記錄數: {len(combined_df)} 場")
    else:
        print("\n❌ 已取消")


if __name__ == "__main__":
    main()

