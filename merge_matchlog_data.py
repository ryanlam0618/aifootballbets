#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
將五大聯賽的比賽數據合并到 big_five_history.csv
新增：整合 MatchPlayerData Excel 文件

用法:
    python merge_matchlog_data.py [--auto-confirm]
    python merge_matchlog_data.py --matchplayer SOURCE_FOLDER [--output OUTPUT]
"""

import os
import sys
import argparse
import pandas as pd
import glob
import re

# 強制設定輸出編碼
sys.stdout.reconfigure(encoding='utf-8')

# 路徑設定
MATCH_DATA_DIR = r"c:/Users/Ryan/Documents/data/五大联赛数据/比赛数据"
BIG_FIVE_HISTORY_PATH = r"c:/Users/Ryan/python/.vscode/fb_ai_bets/data/big_five_history.csv"

# 需要過濾的杯賽 (只保留聯賽)
LEAGUE_ONLY = ["Bundesliga", "La Liga", "Ligue 1", "Premier League", "Serie A"]

# 聯賽名稱映射
LEAGUE_MAPPING = {
    "Premier League": "Premier League",
    "La Liga": "La Liga",
    "Bundesliga": "Bundesliga",
    "Serie A": "Serie A",
    "Ligue 1": "Ligue 1",
    "J1League": "J1 League",  # 新增日本聯賽
    "ALeague": "A-League",    # 澳洲聯賽
}


def read_all_matchlogs():
    """讀取所有 matchlog 文件"""
    all_matches = []
    
    if not os.path.exists(MATCH_DATA_DIR):
        print(f"⚠️ matchlog 目錄不存在: {MATCH_DATA_DIR}")
        return pd.DataFrame()
    
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
                        df["SourceType"] = "matchlog"
                        all_matches.append(df)
                except Exception as e:
                    print(f"[WARN] Read failed: {matchlog_file} - {e}")
    
    if all_matches:
        return pd.concat(all_matches, ignore_index=True)
    return pd.DataFrame()


def read_matchplayer_data(source_folder):
    """讀取 MatchPlayerData Excel 文件"""
    all_matches = []
    
    if not os.path.exists(source_folder):
        print(f"⚠️ MatchPlayerData 目錄不存在: {source_folder}")
        return pd.DataFrame()
    
    excel_files = glob.glob(os.path.join(source_folder, "*.xlsx"))
    print(f"📂 找到 {len(excel_files)} 個 Excel 文件")
    
    for filepath in sorted(excel_files):
        filename = os.path.basename(filepath)
        
        try:
            # 解析檔名
            # 格式：YYYYMMDD_聯賽_[輪次]主隊_vs_客隊[排名].xlsx
            name = filename.replace(".xlsx", "")
            parts = name.split("_")
            
            if len(parts) < 4:
                continue
            
            # 解析日期
            try:
                date_str = parts[0]
                date = pd.to_datetime(date_str, format="%Y%m%d")
            except ValueError:
                continue
            
            league = parts[1]
            
            # 解析對戰組合
            match_part = "_".join(parts[2:])
            match = re.match(r"\[(\d+)\](.+?)\[(\d+)\]$", match_part)
            
            if not match:
                continue
            
            home_rank = match.group(1)
            teams_str = match.group(2)
            away_rank = match.group(3)
            
            teams = teams_str.split("_vs_")
            if len(teams) != 2:
                continue
            
            home_team = teams[0]
            away_team = teams[1]
            
            # 讀取 Excel 獲取比分
            try:
                xl = pd.ExcelFile(filepath)
                
                # 嘗試從第一個工作表獲取比分
                if xl.sheet_names:
                    df = pd.read_excel(xl, sheet_name=xl.sheet_names[0])
                    
                    home_goals = None
                    away_goals = None
                    xg = None
                    xga = None
                    
                    # 搜索比分相關的欄位
                    for col in df.columns:
                        col_lower = str(col).lower()
                        if "score" in col_lower and "final" in col_lower:
                            values = df[col].dropna().tolist()
                            if len(values) >= 2:
                                try:
                                    home_goals = int(values[0])
                                    away_goals = int(values[1])
                                except:
                                    pass
                        elif "xg" in col_lower and "home" in col_lower:
                            try:
                                xg = float(df[col].dropna().iloc[0])
                            except:
                                pass
                        elif "xga" in col_lower or ("xg" in col_lower and "away" in col_lower):
                            try:
                                xga = float(df[col].dropna().iloc[0])
                            except:
                                pass
                    
                    # 從檔名提取排名作為賽季位置
                    try:
                        season_pos = int(home_rank)
                    except:
                        season_pos = None
                    
                    record = {
                        "Date": date.strftime("%Y-%m-%d"),
                        "Time": "",
                        "Div": LEAGUE_MAPPING.get(league, league),
                        "HomeTeam": normalize_team_name(home_team),
                        "AwayTeam": normalize_team_name(away_team),
                        "FTHG": home_goals,
                        "FTAG": away_goals,
                        "Season": f"{date.year}-{date.year+1}",
                        "SourceFile": filename,
                        "SourceType": "matchplayer",
                        "Matchweek": home_rank,
                        "SeasonPos": season_pos,
                        "xG": xg,
                        "xGA": xga
                    }
                    
                    # 計算結果
                    if home_goals is not None and away_goals is not None:
                        if home_goals > away_goals:
                            record["FTR"] = "H"
                        elif home_goals < away_goals:
                            record["FTR"] = "A"
                        else:
                            record["FTR"] = "D"
                    
                    all_matches.append(record)
                    
            except Exception as e:
                print(f"⚠️ 讀取 Excel 失敗: {filename} - {e}")
                
        except Exception as e:
            print(f"⚠️ 解析檔名失敗: {filename} - {e}")
    
    if all_matches:
        return pd.DataFrame(all_matches)
    return pd.DataFrame()


def normalize_team_name(name):
    """標準化球隊名稱"""
    if pd.isna(name):
        return name
    name = str(name).strip()
    
    # 常見的標準化映射 (隊名映射)
    name_mappings = {
        "Manchester City": "Man City",
        "Manchester United": "Man United",
        "Newcastle United": "Newcastle Utd",
        "Tottenham Hotspur": "Tottenham",
        "West Ham United": "West Ham",
        "Wolverhampton Wanderers": "Wolves",
        "Nottingham Forest": "Nott'ham Forest",
        "Leicester City": "Leicester",
        "Leeds United": "Leeds",
        "Sheffield United": "Sheffield Utd",
        "Brighton & Hove Albion": "Brighton",
        "AFC Bournemouth": "Bournemouth",
        "Bayern Munich": "Bayern Munich",
        "Eintracht Frankfurt": "Eint Frankfurt",
        "Borussia Dortmund": "Dortmund",
        "VfB Stuttgart": "Stuttgart",
        "Borussia M'gladbach": "Gladbach",
        "RB Leipzig": "RB Leipzig",
        "SC Freiburg": "Freiburg",
        "TSG Hoffenheim": "Hoffenheim",
        "VfL Wolfsburg": "Wolfsburg",
        "VfL Bochum": "Bochum",
        "1. FC Heidenheim": "Heidenheim",
        "1. FSV Mainz 05": "Mainz 05",
        "SV Werder Bremen": "Werder Bremen",
        "FC Augsburg": "Augsburg",
        "FC St. Pauli": "St. Pauli",
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
        "FC Internazionale": "Inter",
    }
    
    # 檢查是否有反向映射
    reverse_mappings = {
        "Man City": "Manchester City",
        "Man United": "Manchester United",
        "Newcastle Utd": "Newcastle United",
        "Newcastle": "Newcastle United",
        "Tottenham": "Tottenham Hotspur",
        "West Ham": "West Ham United",
        "Wolves": "Wolverhampton Wanderers",
        "Nott'ham Forest": "Nottingham Forest",
        "Leicester": "Leicester City",
        "Leeds": "Leeds United",
        "Sheffield Utd": "Sheffield United",
        "Brighton": "Brighton & Hove Albion",
        "Bournemouth": "AFC Bournemouth",
        "Bayern": "Bayern Munich",
        "Bayern Munich": "Bayern Munich",
        "Eint Frankfurt": "Eintracht Frankfurt",
        "Dortmund": "Borussia Dortmund",
        "Stuttgart": "VfB Stuttgart",
        "Gladbach": "Borussia M'gladbach",
        "RB Leipzig": "RB Leipzig",
        "Freiburg": "SC Freiburg",
        "Hoffenheim": "TSG Hoffenheim",
        "Wolfsburg": "VfL Wolfsburg",
        "Bochum": "VfL Bochum",
        "Heidenheim": "1. FC Heidenheim",
        "Mainz 05": "1. FSV Mainz 05",
        "Werder Bremen": "SV Werder Bremen",
        "Augsburg": "FC Augsburg",
        "St. Pauli": "FC St. Pauli",
        "Atlético": "Atlético Madrid",
        "Sevilla": "Sevilla FC",
        "Villarreal": "Villarreal CF",
        "Real Sociedad": "Real Sociedad",
        "Athletic": "Athletic Club",
        "Betis": "Real Betis",
        "Girona": "Girona FC",
        "Valencia": "Valencia CF",
        "Osasuna": "CA Osasuna",
        "Celta Vigo": "Celta de Vigo",
        "Rayo Vallecano": "Rayo Vallecano",
        "Alavés": "Deportivo Alavés",
        "Mallorca": "RCD Mallorca",
        "Getafe": "Getafe CF",
        "Leganés": "CD Leganés",
        "Valladolid": "Real Valladolid",
        "Espanyol": "RCD Espanyol",
        "Paris S-G": "Paris Saint-Germain",
        "Paris SG": "Paris Saint-Germain",
        "PSG": "Paris Saint-Germain",
        "Lyon": "Olympique Lyonnais",
        "Marseille": "Olympique de Marseille",
        "Monaco": "AS Monaco",
        "Lille": "LOSC Lille",
        "Rennes": "Stade Rennais",
        "Nice": "OGC Nice",
        "Lens": "RC Lens",
        "Nantes": "FC Nantes",
        "Reims": "Stade de Reims",
        "Montpellier": "Montpellier HSC",
        "Lorient": "FC Lorient",
        "Brest": "Stade Brestois 29",
        "Toulouse": "Toulouse FC",
        "Le Havre": "Le Havre AC",
        "Auxerre": "AJ Auxerre",
        "Angers": "Angers SCO",
        "Inter": "FC Internazionale",
        "Milan": "AC Milan",
        "Juventus": "Juventus FC",
        "Roma": "AS Roma",
        "Lazio": "SS Lazio",
        "Napoli": "SSC Napoli",
        "Atalanta": "Atalanta BC",
        "Fiorentina": "ACF Fiorentina",
        "Torino": "Torino FC",
        "Bologna": "Bologna FC",
        "Udinese": "Udinese Calcio",
    }
    
    if name in reverse_mappings:
        return reverse_mappings[name]
    
    return name


def convert_matchlog_to_history_format(df):
    """將 matchlog 數據轉換為 big_five_history 格式"""
    if df.empty:
        return pd.DataFrame()
    
    matches = []
    
    for _, row in df.iterrows():
        # 只處理聯賽
        comp = row.get("Comp", "")
        if comp not in LEAGUE_ONLY and row.get("SourceType") != "matchplayer":
            continue
            
        season = row.get("Season", "")
        match_date = row.get("Date", "")
        match_time = row.get("Time", "")
        venue = row.get("Venue", "")
        gf = row.get("GF", 0)
        ga = row.get("GA", 0)
        opponent = row.get("Opponent", "")
        team_folder = row.get("TeamFolder", "")
        
        if venue == "Home" or row.get("SourceType") == "matchplayer":
            # 主場比賽
            home_team = normalize_team_name(str(team_folder)) if team_folder else row.get("HomeTeam", "")
            away_team = normalize_team_name(str(opponent)) if opponent else row.get("AwayTeam", "")
            home_goals = int(gf) if pd.notna(gf) else row.get("FTHG", 0)
            away_goals = int(ga) if pd.notna(ga) else row.get("FTAG", 0)
        else:
            # 客場比賽
            home_team = normalize_team_name(str(opponent))
            away_team = normalize_team_name(str(team_folder))
            home_goals = int(ga) if pd.notna(ga) else row.get("FTAG", 0)
            away_goals = int(gf) if pd.notna(gf) else row.get("FTHG", 0)
        
        # 根據結果設置 Full Time Result
        ftr = row.get("FTR", "")
        if not ftr:
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
            "Div": comp if comp else row.get("Div", ""),
            "Date": match_date,
            "Time": time_str,
            "HomeTeam": home_team,
            "AwayTeam": away_team,
            "FTHG": home_goals,
            "FTAG": away_goals,
            "FTR": ftr,
            "Season": season,
            "SourceType": row.get("SourceType", "matchlog"),
            "xG": row.get("xG", None),
            "xGA": row.get("xGA", None),
        }
        matches.append(match_record)
    
    return pd.DataFrame(matches)


def find_new_matches(new_df, existing_df):
    """找出在新數據中存在但不在現有數據中的比賽"""
    if new_df.empty:
        return new_df
    
    if existing_df.empty:
        return new_df.copy()
    
    new_df = new_df.copy()
    existing_df = existing_df.copy()
    
    # 確保列是字符串類型
    new_df["MatchKey"] = new_df["Date"].astype(str).str.strip() + "_" + \
                         new_df["HomeTeam"].astype(str).str.strip() + "_" + \
                         new_df["AwayTeam"].astype(str).str.strip()
    existing_df["MatchKey"] = existing_df["Date"].astype(str).str.strip() + "_" + \
                              existing_df["HomeTeam"].astype(str).str.strip() + "_" + \
                              existing_df["AwayTeam"].astype(str).str.strip()
    
    # 轉為小寫進行比較
    new_matches = new_df[~new_df["MatchKey"].str.lower().isin(existing_df["MatchKey"].str.lower())]
    
    return new_matches.drop(columns=["MatchKey"])


def main():
    parser = argparse.ArgumentParser(description='五大聯賽數據合并工具 (含 MatchPlayerData 整合)')
    parser.add_argument('--auto-confirm', '-y', action='store_true',
                        help='自動確認並執行合并')
    parser.add_argument('--matchplayer', '-m', type=str, default=None,
                        help='MatchPlayerData 目錄路徑')
    parser.add_argument('--output', '-o', type=str, default=BIG_FIVE_HISTORY_PATH,
                        help='輸出文件路徑')
    args = parser.parse_args()

    print("=" * 60)
    print("五大聯賽數據合并工具 v2.0 (含 MatchPlayerData 整合)")
    print("=" * 60)
    
    # 1. 讀取現有的 big_five_history.csv
    print(f"\n[INFO] 讀取現有數據: {args.output}")
    if os.path.exists(args.output):
        try:
            existing_df = pd.read_csv(args.output, encoding='utf-8-sig', low_memory=False)
            print(f"   已載入 {len(existing_df)} 場比賽記錄")
        except UnicodeDecodeError:
            existing_df = pd.read_csv(args.output, encoding='latin-1', low_memory=False)
            print(f"   已載入 {len(existing_df)} 場比賽記錄")
    else:
        print(f"   [WARN] 文件不存在: {args.output}")
        existing_df = pd.DataFrame()
    
    # 2. 讀取 matchlog 數據
    print(f"\n[INFO] 讀取 matchlog 數據: {MATCH_DATA_DIR}")
    matchlog_df = read_all_matchlogs()
    if not matchlog_df.empty:
        print(f"   已載入 {len(matchlog_df)} 條 matchlog 記錄")
    else:
        print("   [WARN] 未找到 matchlog 文件或目錄不存在")
    
    # 3. 讀取 MatchPlayerData (如果指定)
    matchplayer_df = pd.DataFrame()
    if args.matchplayer:
        print(f"\n[INFO] 讀取 MatchPlayerData: {args.matchplayer}")
        matchplayer_df = read_matchplayer_data(args.matchplayer)
        if not matchplayer_df.empty:
            print(f"   已載入 {len(matchplayer_df)} 條 MatchPlayerData 記錄")
    
    # 4. 合併新數據源
    new_data = matchlog_df
    
    if not matchplayer_df.empty:
        # 轉換 MatchPlayerData 格式
        converted_mp = convert_matchlog_to_history_format(matchplayer_df)
        if not converted_mp.empty:
            print(f"   MatchPlayerData 轉換後: {len(converted_mp)} 條")
            new_data = pd.concat([new_data, converted_mp], ignore_index=True)
    
    if new_data.empty:
        print("\n⚠️ 沒有新數據可整合")
        return
    
    # 5. 轉換為歷史數據格式
    print("\n[INFO] 轉換數據格式...")
    new_history_df = convert_matchlog_to_history_format(new_data)
    if not new_history_df.empty:
        print(f"   轉換後的聯賽記錄: {len(new_history_df)} 場")
    else:
        print("   [WARN] 轉換後無有效數據")
        return
    
    # 6. 找出新的比賽
    print("\n[INFO] 比對數據...")
    new_matches = find_new_matches(new_history_df, existing_df)
    print(f"   新發現的比賽: {len(new_matches)} 場")
    
    if new_matches.empty:
        print("\n[OK] 沒有需要添加的新數據")
        return
    
    # 7. 顯示新數據的詳細信息
    print("\n[INFO] 新數據預覽:")
    print("-" * 60)
    for _, row in new_matches.head(10).iterrows():
        source = row.get("SourceType", "unknown")
        print(f"   [{source}] {row['Date']} | {row['Div']} | {row['HomeTeam']} vs {row['AwayTeam']} ({row['FTHG']}-{row['FTAG']})")
    if len(new_matches) > 10:
        print(f"   ... 以及其他 {len(new_matches) - 10} 場比賽")
    
    # 8. 添加到現有數據
    print("\n" + "=" * 60)
    
    if args.auto_confirm:
        confirm = "y"
        print(f"[AUTO] 自動確認模式: 將添加 {len(new_matches)} 場新比賽")
    else:
        confirm = input(f"確定要將 {len(new_matches)} 場新比賽添加到歷史數據嗎? (y/n): ")
    
    if confirm.lower() == "y":
        # 合并數據
        combined_df = pd.concat([existing_df, new_matches], ignore_index=True)
        
        # 排序
        combined_df["DateSort"] = pd.to_datetime(combined_df["Date"], errors='coerce')
        combined_df = combined_df.sort_values("DateSort", ascending=False)
        combined_df = combined_df.drop(columns=["DateSort"])
        
        # 保存
        combined_df.to_csv(args.output, index=False, encoding='utf-8-sig')
        print(f"\n[OK] 成功添加 {len(new_matches)} 場比賽!")
        print(f"   總記錄數: {len(combined_df)} 場")
    else:
        print("\n[INFO] 已取消")


if __name__ == "__main__":
    main()
