#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MatchPlayerData Excel 文件整合工具

將 MatchPlayerData_English_v3 中的 Excel 文件整合為統一的 CSV 格式

用法:
    python import_matchplayer_data.py [--source SOURCE_FOLDER] [--output OUTPUT_CSV]
"""

import os
import sys
import re
import glob
import argparse
import pandas as pd
from datetime import datetime

# 強制設定輸出編碼
sys.stdout.reconfigure(encoding='utf-8')

# 路徑設定
DEFAULT_SOURCE = r"c:/Users/Ryan/Documents/data/Football data crawling tool/MatchPlayerData_English_v3"
DEFAULT_OUTPUT = r"c:/Users/Ryan/python/.vscode/fb_ai_bets/data/matchplayer_data.csv"


def parse_filename(filename):
    """
    解析檔名結構
    例：20250525_PremierLeague_[1]Liverpool_vs_CrystalPalace[12].xlsx
    
    返回:
        dict: 包含 date, league, home_team, away_team, home_rank, away_rank
    """
    # 移除副檔名
    name = filename.replace(".xlsx", "")
    
    # 分割檔名
    parts = name.split("_")
    
    if len(parts) < 4:
        return None
    
    try:
        date_str = parts[0]
        date = datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        return None
    
    league = parts[1]
    
    # 解析對戰組合部分
    # 格式：[輪次]主隊_vs_客隊[排名]
    match_part = "_".join(parts[2:])
    
    # 使用正則表達式解析
    pattern = r"\[(\d+)\](.+?)\[(\d+)\]$"
    match = re.match(pattern, match_part)
    
    if not match:
        # 嘗試更寬鬆的匹配
        pattern2 = r"\[(\d+)\](.+)"
        match2 = re.match(pattern2, match_part)
        if match2:
            home_rank = match2.group(1)
            rest = match2.group(2)
            teams = rest.split("_vs_")
            if len(teams) >= 2:
                # 從最後一個部分提取 away_rank
                away_part = teams[-1]
                away_match = re.search(r"\[(\d+)\]$", away_part)
                if away_match:
                    away_rank = away_match.group(1)
                    away_team = re.sub(r"\[\d+\]$", "", away_part)
                    home_team = "_vs_".join(teams[:-1])
                    return {
                        "date": date,
                        "league": league,
                        "home_team": home_team,
                        "away_team": away_team,
                        "home_rank": int(home_rank) if home_rank.isdigit() else None,
                        "away_rank": int(away_rank) if away_rank.isdigit() else None,
                        "source_file": filename
                    }
        return None
    
    home_rank = match.group(1)
    teams_str = match.group(2)
    away_rank = match.group(3)
    
    # 分割主隊和客隊
    teams = teams_str.split("_vs_")
    if len(teams) != 2:
        return None
    
    home_team = teams[0]
    away_team = teams[1]
    
    return {
        "date": date,
        "league": league,
        "home_team": home_team,
        "away_team": away_team,
        "home_rank": int(home_rank) if home_rank.isdigit() else None,
        "away_rank": int(away_rank) if away_rank.isdigit() else None,
        "source_file": filename
    }


def extract_excel_data(filepath):
    """
    從 Excel 文件中提取數據
    
    返回:
        dict: 包含 match_info, statistics
    """
    try:
        # 讀取 Excel 文件的所有工作表
        xl = pd.ExcelFile(filepath)
        
        result = {
            "match_info": {},
            "statistics": {}
        }
        
        # 解析 MatchInfo 工作表 (比分信息)
        if "MatchInfo" in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name="MatchInfo")
            if not df.empty:
                for _, row in df.iterrows():
                    for col in df.columns:
                        key = str(col)
                        value = row[col]
                        if pd.notna(value):
                            result["match_info"][key] = value
        
        # 解析 MatchStats 工作表 (統計數據)
        if "MatchStats" in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name="MatchStats")
            if not df.empty:
                # 將統計數據按球隊組織
                for _, row in df.iterrows():
                    team_name = row.get('TeamName', 'Unknown')
                    result["statistics"][team_name] = {
                        'corners': row.get('Corner', 0),
                        'half_corners': row.get('HalfCorner', 0),
                        'yellow_cards': row.get('YellowCard', 0),
                        'red_cards': row.get('RedCard', 0),
                        'shots': row.get('Shots', 0),
                        'shots_on_target': row.get('ShotsOnTarget', 0),
                        'attacks': row.get('Attacks', 0),
                        'dangerous_attacks': row.get('DangerousAttacks', 0),
                        'shots_off_target': row.get('ShotsOffTarget', 0),
                    }
        
        return result
    
    except Exception as e:
        print(f"⚠️ 讀取 Excel 錯誤: {filepath} - {e}")
        return None


def process_matchplayer_data(source_folder, output_csv, leagues=None):
    """
    處理 MatchPlayerData 文件夾中的所有 Excel 文件
    
    Args:
        source_folder: 源文件夾路徑
        output_csv: 輸出 CSV 文件路徑
        leagues: 過濾的聯賽列表 (None 表示所有聯賽)
    """
    print("=" * 60)
    print("MatchPlayerData 整合工具")
    print("=" * 60)
    
    if not os.path.exists(source_folder):
        print(f"❌ 源文件夾不存在: {source_folder}")
        return
    
    # 獲取所有 Excel 文件
    excel_files = glob.glob(os.path.join(source_folder, "*.xlsx"))
    print(f"\n📂 找到 {len(excel_files)} 個 Excel 文件")
    
    # 統計信息
    stats = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "by_league": {}
    }
    
    all_records = []
    
    for filepath in sorted(excel_files):
        filename = os.path.basename(filepath)
        stats["total"] += 1

        # 解析檔名
        parsed = parse_filename(filename)
        
        if not parsed:
            print(f"⚠️ 無法解析檔名: {filename}")
            stats["failed"] += 1
            continue
        
        # 過濾聯賽
        if leagues and parsed["league"] not in leagues:
            continue
        
        # 初始化聯賽統計
        league = parsed["league"]
        if league not in stats["by_league"]:
            stats["by_league"][league] = 0
        
        # 提取 Excel 數據
        excel_data = extract_excel_data(filepath)
        
        # 創建記錄
        record = {
            "date": parsed["date"].strftime("%Y-%m-%d"),
            "league": parsed["league"],
            "home_team": parsed["home_team"],
            "away_team": parsed["away_team"],
            "home_rank": parsed["home_rank"],
            "away_rank": parsed["away_rank"],
            "source_file": filename
        }
        
        # 從 Excel 中提取額外數據
        if excel_data and excel_data.get("match_info"):
            info = excel_data["match_info"]
            
            # 提取比分 - 嘗試多種欄位名稱
            score_keys = ['Full Score', 'FullScore', 'Score', 'Final Score', 'FT Score']
            for key in score_keys:
                if key in info:
                    score_str = str(info[key])
                    if "-" in score_str:
                        scores = score_str.split("-")
                        if len(scores) == 2:
                            try:
                                record["home_goals"] = int(scores[0].strip())
                                record["away_goals"] = int(scores[1].strip())
                                break
                            except ValueError:
                                pass
            
            # 提取半場比分
            ht_keys = ['Half Score', 'HalfScore', 'HT Score', 'HalfTime Score']
            for key in ht_keys:
                if key in info:
                    ht_str = str(info[key])
                    if "-" in ht_str:
                        scores = ht_str.split("-")
                        if len(scores) == 2:
                            try:
                                record["ht_home_goals"] = int(scores[0].strip())
                                record["ht_away_goals"] = int(scores[1].strip())
                                break
                            except ValueError:
                                pass
            
            # 提取聯賽名稱 (覆蓋從檔名解析的值)
            if 'League' in info:
                record["league"] = info['League']
            
            # 提取日期 (覆蓋從檔名解析的值)
            if 'Date' in info:
                date_val = info['Date']
                if isinstance(date_val, str):
                    try:
                        record["date"] = pd.to_datetime(date_val).strftime("%Y-%m-%d")
                    except:
                        pass
        
        # 提取統計數據
        if excel_data and excel_data.get("statistics"):
            team_stats = excel_data["statistics"]
            for team_name, team_data in team_stats.items():
                if record["home_team"] in team_name or team_name in record["home_team"]:
                    record["home_corners"] = team_data.get('corners', 0)
                    record["home_shots"] = team_data.get('shots', 0)
                    record["home_shots_on"] = team_data.get('shots_on_target', 0)
                elif record["away_team"] in team_name or team_name in record["away_team"]:
                    record["away_corners"] = team_data.get('corners', 0)
                    record["away_shots"] = team_data.get('shots', 0)
                    record["away_shots_on"] = team_data.get('shots_on_target', 0)
        
        # 計算結果
        if "home_goals" in record and "away_goals" in record:
            if record["home_goals"] > record["away_goals"]:
                record["result"] = "H"
            elif record["home_goals"] < record["away_goals"]:
                record["result"] = "A"
            else:
                record["result"] = "D"
        
        # 統計
        stats["by_league"][league] += 1
        
        all_records.append(record)
        stats["success"] += 1
    
    # 創建 DataFrame
    if all_records:
        df = pd.DataFrame(all_records)
        
        # 排序
        df = df.sort_values("date", ascending=False)
        
        # 保存
        os.makedirs(os.path.dirname(output_csv), exist_ok=True)
        df.to_csv(output_csv, index=False, encoding='utf-8-sig')
        
        print(f"\n✅ 整合完成！")
        print(f"   總文件數: {stats['total']}")
        print(f"   成功處理: {stats['success']}")
        print(f"   失敗: {stats['failed']}")
        print(f"   輸出文件: {output_csv}")
        print(f"   記錄數: {len(df)}")
        
        print(f"\n📊 按聯賽統計:")
        for league, count in sorted(stats["by_league"].items()):
            print(f"   {league}: {count} 場")
        
        return df
    else:
        print("⚠️ 沒有找到有效數據")
        return None


def analyze_player_data(source_folder):
    """
    分析球員數據結構
    """
    print("\n" + "=" * 60)
    print("球員數據結構分析")
    print("=" * 60)
    
    # 找幾個樣本文件
    sample_files = sorted(glob.glob(os.path.join(source_folder, "*.xlsx")))[:3]
    
    for filepath in sample_files[:5]:
        filename = os.path.basename(filepath)
        print(f"\n📄 {filename}")
        
        try:
            xl = pd.ExcelFile(filepath)
            print(f"   工作表: {xl.sheet_names}")
            
            for sheet_name in xl.sheet_names[:2]:  # 只看前兩個工作表
                df = pd.read_excel(xl, sheet_name=sheet_name)
                print(f"   📋 {sheet_name}: {df.shape[0]} 行, {df.shape[1]} 列")
                if not df.empty:
                    print(f"      欄位: {list(df.columns[:10])}")
        except Exception as e:
            print(f"   ⚠️ 讀取錯誤: {e}")


def main():
    parser = argparse.ArgumentParser(description='MatchPlayerData 整合工具')
    parser.add_argument('--source', '-s', default=DEFAULT_SOURCE,
                        help='源文件夾路徑')
    parser.add_argument('--output', '-o', default=DEFAULT_OUTPUT,
                        help='輸出 CSV 文件路徑')
    parser.add_argument('--leagues', '-l', default=None,
                        help='過濾的聯賽 (逗號分隔)')
    parser.add_argument('--analyze', '-a', action='store_true',
                        help='分析數據結構後退出')
    
    args = parser.parse_args()
    
    # 處理聯賽過濾
    leagues = None
    if args.leagues:
        leagues = args.leagues.split(",")
    
    # 分析模式
    if args.analyze:
        analyze_player_data(args.source)
        return
    
    # 執行整合
    df = process_matchplayer_data(args.source, args.output, leagues)
    
    if df is not None:
        print(f"\n📈 數據預覽:")
        print(df.head(10).to_string())


if __name__ == "__main__":
    main()
