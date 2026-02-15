#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将比赛球员数据Excel文件转换为CSV格式
按联赛和球队分类存放
"""

import os
import pandas as pd
import re
from pathlib import Path
from datetime import datetime

# 路径配置
SOURCE_DIR = r"c:\Users\Ryan\Documents\data\Football data crawling tool\比赛球员数据"
TARGET_DIR = r"c:\Users\Ryan\Documents\data\big_five_data"

# 联赛名称映射（中文 -> 英文文件夹名）
LEAGUE_MAP = {
    "英超": "Premier-League",
    "西甲": "La-Liga",
    "意甲": "Serie-A",
    "德甲": "Bundesliga",
    "法甲": "Ligue-1",
    "日职联": "J1-League",  # 日职联可能需要单独处理
}

# 球队名称映射（中文 -> 英文）
TEAM_NAME_MAP = {
    # 英超
    "利物浦": "Liverpool",
    "水晶宫": "Crystal Palace",
    "阿森纳": "Arsenal",
    "南安普敦": "Southampton",
    "布伦特福德": "Brentford",
    "托特纳姆热刺": "Tottenham",
    "布莱顿": "Brighton",
    "诺丁汉森林": "Nott'ham Forest",
    "切尔西": "Chelsea",
    "纽卡斯尔联": "Newcastle Utd",
    "埃弗顿": "Everton",
    "狼队": "Wolves",
    "曼彻斯特城": "Manchester City",
    "曼彻斯特联": "Manchester Utd",
    "阿斯顿维拉": "Aston Villa",
    "富勒姆": "Fulham",
    "伯恩茅斯": "Bournemouth",
    "莱斯特城": "Leicester City",
    "伊普斯维奇": "Ipswich Town",
    "西汉姆联": "West Ham",
    
    # 西甲
    "毕尔巴鄂竞技": "Athletic Club",
    "巴塞罗那": "Barcelona",
    "赫塔菲": "Getafe",
    "塞尔塔": "Celta Vigo",
    "皇家马德里": "Real Madrid",
    "皇家社会": "Real Sociedad",
    "比利亚雷亚尔": "Villarreal",
    "塞维利亚": "Sevilla",
    "赫罗纳": "Girona",
    "马德里竞技": "Atlético Madrid",
    "巴列卡诺": "Rayo Vallecano",
    "马洛卡": "Mallorca",
    "阿拉维斯": "Alavés",
    "奥萨苏纳": "Osasuna",
    "拉斯帕尔马斯": "Las Palmas",
    "西班牙人": "Espanyol",
    "莱加内斯": "Leganés",
    "巴拉多利德": "Valladolid",
    "巴伦西亚": "Valencia",
    "贝蒂斯": "Betis",
    
    # 意甲
    "威尼斯": "Venezia",
    "尤文图斯": "Juventus",
    "乌迪内斯": "Udinese",
    "佛罗伦萨": "Fiorentina",
    "都灵": "Torino",
    "罗马": "Roma",
    "拉齐奥": "Lazio",
    "莱切": "Lecce",
    "亚特兰大": "Atalanta",
    "帕尔马": "Parma",
    "维罗纳": "Hellas Verona",
    "科莫": "Como",
    "蒙扎": "Monza",
    "恩波利": "Empoli",
    "博洛尼亚": "Bologna",
    "热那亚": "Genoa",
    "卡利亚里": "Cagliari",
    "AC米兰": "Milan",
    "国际米兰": "Inter",
    "那不勒斯": "Napoli",
    
    # 德甲
    "圣保利": "St. Pauli",
    "波鸿": "Bochum",
    "美因茨": "Mainz 05",
    "勒沃库森": "Leverkusen",
    "海登海姆": "Heidenheim",
    "云达不莱梅": "Werder Bremen",
    
    # 法甲
    "马赛": "Marseille",
    "雷恩": "Rennes",
    "里尔": "Lille",
    "兰斯": "Reims",
    "巴黎圣日尔曼": "Paris S-G",
    "欧塞尔": "Auxerre",
    "圣埃蒂安": "Saint-Étienne",
    "图卢兹": "Toulouse",
    "昂热": "Angers",
    "里昂": "Lyon",
    "摩纳哥": "Monaco",
    "朗斯": "Lens",
    "尼斯": "Nice",
    "布雷斯特": "Brest",
    "斯特拉斯堡": "Strasbourg",
    "勒阿弗尔": "Le Havre",
    "蒙彼利埃": "Montpellier",
    "南特": "Nantes",
    
    # 日职联
    "广岛三箭": "Hiroshima Sanfrecce",
    "名古屋鲸八": "Nagoya Grampus",
    "京都不死鸟": "Kyoto Sanga",
    "大阪钢巴": "Gamba Osaka",
    "湘南海洋": "Shonan Bellmare",
    "横滨水手": "Yokohama F. Marinos",
    "FC东京": "FC Tokyo",
    "横滨FC": "Yokohama FC",
    "福冈黄蜂": "Fukuoka Sanga",
    "神户胜利船": "Kobe Vissel",
    "清水鼓动": "Shimizu S-Pulse",
    "柏太阳神": "Kashiwa Reysol",
    "冈山绿雉": "Okayama",
    "川崎前锋": "Kawasaki Frontale",
    "鹿岛鹿角": "Kashima Antlers",
    "町田泽维亚": "Machida Zelvia",
    "东京绿茵": "Tokyo Verdy",
    "新泻天鹅": "Albirex Niigata",
    "大阪樱花": "Cerezo Osaka",
    "札幌冈萨多": "Consadole Sapporo",
    "磐田喜悦": "JEF United",
    "大分三神": "Oita Trinita",
    "德岛漩涡": "Tokushima Vortis",
    "甲府风林": "Ventforet Kofu",
    "金泽萨维根": "Zweigen Kanazawa",
    "北九州向日葵": "Giravanz Kitakyushu",
    "松本山雅": "Matsumoto Yamaga",
    "水户蜀葵": "Mito HollyHock",
    "千叶市原": "JEF United Chiba",
    "枥木SC": "Tochigi SC",
    "群马草津温泉": "Thespakusatsu Gunma",
    "大宫松鼠": "Omiya Ardija",
    "岐阜FC": "FC Gifu",
    "赞岐釜玉海": "Kamatamare Sanuki",
    "长崎成功丸": "V-Varen Nagasaki",
    "熊本深红": "Kumamoto",
    "琉球FC": "FC Ryukyu",
    "藤枝MFC": "Fujieda MYFC",
    "鹿儿岛联": "Kagoshima United",
}

# 球队到联赛的映射（用于日职联球队）
TEAM_LEAGUE = {
    # 日职联
    "Hiroshima Sanfrecce": "J1-League",
    "Nagoya Grampus": "J1-League",
    "Kyoto Sanga": "J1-League",
    "Gamba Osaka": "J1-League",
    "Shonan Bellmare": "J1-League",
    "Yokohama F. Marinos": "J1-League",
    "FC Tokyo": "J1-League",
    "Yokohama FC": "J1-League",
    "Fukuoka Sanga": "J1-League",
    "Kobe Vissel": "J1-League",
    "Shimizu S-Pulse": "J1-League",
    "Kashiwa Reysol": "J1-League",
    "Okayama": "J1-League",
    "Kawasaki Frontale": "J1-League",
    "Kashima Antlers": "J1-League",
    "Machida Zelvia": "J1-League",
    "Tokyo Verdy": "J1-League",
    "Albirex Niigata": "J1-League",
    "Cerezo Osaka": "J1-League",
}


def parse_filename(filename):
    """解析文件名，提取比赛信息"""
    # 格式: 20250628_日职联_[3]广岛三箭_vs_名古屋鲸八[14].xlsx
    pattern = r"(\d{8})_(.+?)_\[(\d+)\](.+?)_vs_\[(?:\d+)\](.+?)\.xlsx"
    match = re.match(pattern, filename)
    
    if match:
        date_str = match.group(1)  # 20250628
        league_cn = match.group(2)  # 日职联
        home_rank = match.group(3)  # 3
        home_team_cn = match.group(4)  # 广岛三箭
        away_team_cn = match.group(5)  # 名古屋鲸八
        
        # 转换日期格式
        date = datetime.strptime(date_str, "%Y%m%d")
        date_formatted = date.strftime("%Y-%m-%d")
        
        return {
            "date": date_formatted,
            "league_cn": league_cn,
            "league_en": LEAGUE_MAP.get(league_cn, league_cn),
            "home_team_cn": home_team_cn.strip(),
            "away_team_cn": away_team_cn.strip(),
            "home_rank": home_rank,
        }
    return None


def get_team_league(team_en):
    """获取球队所属联赛"""
    return TEAM_LEAGUE.get(team_en, None)


def read_excel_file(filepath):
    """读取Excel文件"""
    try:
        # 读取所有sheet
        xl = pd.ExcelFile(filepath)
        sheets = {}
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name=sheet_name)
            sheets[sheet_name] = df
        return sheets
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None


def process_match_data(sheets, match_info):
    """处理比赛数据"""
    all_data = []
    
    for sheet_name, df in sheets.items():
        if df is not None and not df.empty:
            # 添加比赛信息
            df_copy = df.copy()
            df_copy["比赛日期"] = match_info["date"]
            df_copy["联赛"] = match_info["league_cn"]
            df_copy["主队"] = match_info["home_team_cn"]
            df_copy["客队"] = match_info["away_team_cn"]
            df_copy["数据来源Sheet"] = sheet_name
            
            all_data.append(df_copy)
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return None


def save_player_csv(df, team_en, league_en):
    """保存球员数据到CSV"""
    if df is None or df.empty:
        return
    
    # 创建目标目录
    if league_en == "J1-League":
        target_path = os.path.join(TARGET_DIR, "j1_league", team_en)
    else:
        target_path = os.path.join(TARGET_DIR, "match_data", league_en, team_en)
    
    os.makedirs(target_path, exist_ok=True)
    
    # 获取日期范围
    dates = df["比赛日期"].unique()
    if len(dates) == 1:
        date_str = dates[0]
    else:
        date_str = f"{min(dates)}_to_{max(dates)}"
    
    # 保存CSV
    csv_path = os.path.join(target_path, f"{team_en}_match_players_{date_str}.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"Saved: {csv_path}")
    
    return csv_path


def main():
    """主函数"""
    print("Starting data conversion...")
    print(f"Source: {SOURCE_DIR}")
    print(f"Target: {TARGET_DIR}")
    print()
    
    # 获取所有xlsx文件
    files = [f for f in os.listdir(SOURCE_DIR) if f.endswith('.xlsx')]
    print(f"Found {len(files)} Excel files")
    print()
    
    # 按球队分组数据
    team_data = {}
    
    for filename in files:
        print(f"Processing: {filename}")
        
        # 解析文件名
        match_info = parse_filename(filename)
        if not match_info:
            print(f"  ⚠️  Could not parse filename: {filename}")
            continue
        
        print(f"  Date: {match_info['date']}, League: {match_info['league_cn']}")
        print(f"  Match: {match_info['home_team_cn']} vs {match_info['away_team_cn']}")
        
        # 读取Excel文件
        filepath = os.path.join(SOURCE_DIR, filename)
        sheets = read_excel_file(filepath)
        if not sheets:
            continue
        
        # 获取主客队英文名
        home_team_en = TEAM_NAME_MAP.get(match_info["home_team_cn"], match_info["home_team_cn"])
        away_team_en = TEAM_NAME_MAP.get(match_info["away_team_cn"], match_info["away_team_cn"])
        
        # 处理主队数据
        if home_team_en not in team_data:
            team_data[home_team_en] = {
                "league": match_info["league_en"],
                "data": []
            }
        elif team_data[home_team_en]["league"] != match_info["league_en"]:
            # 联赛不匹配，警告
            print(f"  ⚠️  League mismatch for {home_team_en}")
        
        # 处理客队数据
        if away_team_en not in team_data:
            team_data[away_team_en] = {
                "league": match_info["league_en"],
                "data": []
            }
        elif team_data[away_team_en]["league"] != match_info["league_en"]:
            print(f"  ⚠️  League mismatch for {away_team_en}")
        
        # 处理每张sheet的数据
        for sheet_name, df in sheets.items():
            if df is None or df.empty:
                continue
            
            # 尝试识别球员数据行
            # 通常球员数据会有"球员"或"name"等列
            player_cols = [col for col in df.columns if "球员" in col.lower() or "name" in col.lower() or "player" in col.lower()]
            
            if not player_cols:
                continue
            
            # 添加比赛信息
            df_copy = df.copy()
            df_copy["比赛日期"] = match_info["date"]
            df_copy["联赛"] = match_info["league_cn"]
            df_copy["主队"] = match_info["home_team_cn"]
            df_copy["客队"] = match_info["away_team_cn"]
            df_copy["立场"] = "Home" if sheet_name in ["Home", "主队", match_info["home_team_cn"]] else "Away"
            df_copy["数据来源"] = filename
            
            # 根据sheet名判断是主队还是客队数据
            if any(keyword in sheet_name for keyword in [match_info["home_team_cn"], "Home", "主队"]):
                team_data[home_team_en]["data"].append(df_copy)
            elif any(keyword in sheet_name for keyword in [match_info["away_team_cn"], "Away", "客队"]):
                team_data[away_team_en]["data"].append(df_copy)
            else:
                # 如果无法判断，默认两边都保存
                team_data[home_team_en]["data"].append(df_copy)
                team_data[away_team_en]["data"].append(df_copy)
    
    print("\n" + "="*50)
    print("Saving player data...")
    print("="*50 + "\n")
    
    # 保存每个球队的数据
    for team_en, info in team_data.items():
        if not info["data"]:
            continue
        
        # 合并数据
        df = pd.concat(info["data"], ignore_index=True)
        league_en = info["league"]
        
        # 保存
        if league_en == "J1-League":
            target_path = os.path.join(TARGET_DIR, "j1_league", team_en)
        else:
            target_path = os.path.join(TARGET_DIR, "match_data", league_en, team_en)
        
        os.makedirs(target_path, exist_ok=True)
        
        # 获取日期范围
        dates = df["比赛日期"].unique()
        if len(dates) == 1:
            date_str = dates[0]
        else:
            dates_sorted = sorted(dates)
            date_str = f"{dates_sorted[0]}_to_{dates_sorted[-1]}"
        
        # 保存CSV
        csv_path = os.path.join(target_path, f"{team_en}_players_{date_str}.csv")
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"Saved: {csv_path} ({len(df)} rows)")
    
    print("\n" + "="*50)
    print("Conversion completed!")
    print("="*50)


if __name__ == "__main__":
    main()
