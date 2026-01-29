#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
標準化 big_five_history.csv 中的隊名
"""

import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

BIG_FIVE_HISTORY_PATH = r"c:/Users/Ryan/python/.vscode/fb_ai_bets/data/big_five_history.csv"

# 隊名標準化映射 (原始名稱 -> 標準名稱)
TEAM_NAME_NORMALIZE = {
    # 德甲
    "FC Augsburg": "Augsburg",
    "FC St. Pauli": "St. Pauli",
    "SV Werder Bremen": "Werder Bremen",
    "1. FSV Mainz 05": "Mainz 05",
    "1. FC Heidenheim": "Heidenheim",
    "VfL Bochum": "Bochum",
    "VfL Wolfsburg": "Wolfsburg",
    "TSG Hoffenheim": "Hoffenheim",
    "SC Freiburg": "Freiburg",
    "Borussia M'gladbach": "Gladbach",
    "Eintracht Frankfurt": "Eint Frankfurt",
    "VfB Stuttgart": "Stuttgart",
    "Borussia Dortmund": "Dortmund",
    "FC Bayern München": "Bayern Munich",
    "Bayern Munich": "Bayern Munich",  # 保持原樣
    "RB Leipzig": "RB Leipzig",  # 保持原樣
    "Union Berlin": "Union Berlin",  # 保持原樣
    
    # 英超
    "Tottenham Hotspur": "Tottenham",
    "Wolverhampton Wanderers": "Wolves",
    "West Ham United": "West Ham",
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Newcastle United": "Newcastle Utd",
    "Nottingham Forest": "Nott'ham Forest",
    "Brighton & Hove Albion": "Brighton",
    "AFC Bournemouth": "Bournemouth",
    "Sheffield United": "Sheffield Utd",
    "Leicester City": "Leicester",
    "Leeds United": "Leeds",
    
    # 西甲
    "Atlético de Madrid": "Atlético",
    "Atlético Madrid": "Atlético",
    "Sevilla FC": "Sevilla",
    "Villarreal CF": "Villarreal",
    "Real Sociedad": "Real Sociedad",
    "Athletic Club": "Athletic",
    "Real Betis": "Betis",
    "Girona FC": "Girona",
    "Valencia CF": "Valencia",
    "CA Osasuna": "Osasuna",
    "Celta de Vigo": "Celta Vigo",
    "Rayo Vallecano": "Rayo Vallecano",
    "Deportivo Alavés": "Alavés",
    "RCD Mallorca": "Mallorca",
    "Getafe CF": "Getafe",
    "CD Leganés": "Leganés",
    "Real Valladolid": "Valladolid",
    "RCD Espanyol": "Espanyol",
    
    # 法甲
    "Paris Saint-Germain": "Paris S-G",
    "Olympique Lyonnais": "Lyon",
    "Olympique de Marseille": "Marseille",
    "AS Monaco": "Monaco",
    "LOSC Lille": "Lille",
    "Stade Rennais": "Rennes",
    "OGC Nice": "Nice",
    "RC Lens": "Lens",
    "FC Nantes": "Nantes",
    "Stade de Reims": "Reims",
    "Montpellier HSC": "Montpellier",
    "FC Lorient": "Lorient",
    "Stade Brestois 29": "Brest",
    "Toulouse FC": "Toulouse",
    "Le Havre AC": "Le Havre",
    "AJ Auxerre": "Auxerre",
    "Angers SCO": "Angers",
    
    # 意甲
    "FC Internazionale": "Inter",
    "AC Milan": "Milan",
    "Juventus FC": "Juventus",
    "AS Roma": "Roma",
    "SS Lazio": "Lazio",
    "SSC Napoli": "Napoli",
    "Atalanta BC": "Atalanta",
    "ACF Fiorentina": "Fiorentina",
    "Torino FC": "Torino",
    "Bologna FC": "Bologna",
    "Udinese Calcio": "Udinese",
}


def normalize_team_names(df):
    """標準化所有隊名"""
    df = df.copy()
    
    # 標準化主隊
    df['HomeTeam'] = df['HomeTeam'].replace(TEAM_NAME_NORMALIZE)
    
    # 標準化客隊
    df['AwayTeam'] = df['AwayTeam'].replace(TEAM_NAME_NORMALIZE)
    
    return df


def main():
    print("=" * 60)
    print("隊名標準化工具")
    print("=" * 60)
    
    # 讀取數據
    print(f"\n[INFO] 讀取數據: {BIG_FIVE_HISTORY_PATH}")
    df = pd.read_csv(BIG_FIVE_HISTORY_PATH, encoding='utf-8-sig', low_memory=False)
    print(f"   總記錄數: {len(df)}")
    
    # 統計標準化前的情況
    before_home = df['HomeTeam'].nunique()
    before_away = df['AwayTeam'].nunique()
    
    # 標準化隊名
    print("\n[INFO] 標準化隊名...")
    df = normalize_team_names(df)
    
    # 統計標準化後的情況
    after_home = df['HomeTeam'].nunique()
    after_away = df['AwayTeam'].nunique()
    
    print(f"   主隊唯一值: {before_home} -> {after_home}")
    print(f"   客隊唯一值: {before_away} -> {after_away}")
    
    # 保存
    df.to_csv(BIG_FIVE_HISTORY_PATH, index=False, encoding='utf-8-sig')
    print(f"\n[OK] 隊名標準化完成!")
    
    # 驗證
    print("\n[INFO] 驗證結果:")
    teams_to_check = ['Augsburg', 'Tottenham', 'Bayern', 'Inter', 'PSG']
    for team in teams_to_check:
        home_matches = df[df['HomeTeam'].str.contains(team, case=False, na=False)]['HomeTeam'].unique()
        away_matches = df[df['AwayTeam'].str.contains(team, case=False, na=False)]['AwayTeam'].unique()
        all_matches = list(home_matches) + list(away_matches)
        if len(all_matches) > 0:
            print(f"   {team}: {set(all_matches)}")
        else:
            print(f"   {team}: 沒有找到")


if __name__ == "__main__":
    main()

