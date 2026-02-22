# -*- coding: utf-8 -*-
"""
SofaScore 5年數據整合腳本
將 all_statistics.csv 和 all_shotmap.csv 轉換為統一的 history_data.csv
"""
import pandas as pd
import numpy as np
import os
from datetime import datetime

# 設定路徑
DATA_DIR = r'C:\Users\Ryan\python\.vscode\fb_ai_bets\data\sofascore\5_years_data'
OUTPUT_DIR = r'C:\Users\Ryan\python\.vscode\fb_ai_bets\data'
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'history_data.csv')

# 統計數據映射表 (stat_name -> output column)
STAT_MAPPING = {
    'Ball possession': ('poss', 'poss'),
    'Total shots': ('home_shots', 'away_shots'),
    'Shots on target': ('home_shots_on', 'away_shots_on'),
    'Corner kicks': ('home_corners', 'away_corners'),
    'Yellow cards': ('home_yellow', 'away_yellow'),
    'Red cards': ('home_red', 'away_red'),
    'Fouls': ('home_fouls', 'away_fouls'),
    'Shots inside box': ('home_shots_inside_box', 'away_shots_inside_box'),
    'Shots outside box': ('home_shots_outside_box', 'away_shots_outside_box'),
    'Goalkeeper saves': ('home_saves', 'away_saves'),
    'Offsides': ('home_offsides', 'away_offsides'),
    'Passes': ('home_passes', 'away_passes'),
    'Accurate passes': ('home_passes_accurate', 'away_passes_accurate'),
    'Big chances': ('home_big_chances', 'away_big_chances'),
    'Big chances missed': ('home_big_chances_missed', 'away_big_chances_missed'),
    'Total clears': ('home_clears', 'away_clears'),
    'Goals': ('home_goals', 'away_goals'),  # 從 statistics 获取
}

# 聯賽名稱映射
LEAGUE_MAPPING = {
    'Premier League': 'Premier League',
    'LaLiga': 'La Liga',
    'Serie A': 'Serie A',
    'Bundesliga': 'Bundesliga',
    'Ligue 1': 'Ligue 1',
    'J1 League': 'J1 League',
    'K League 1': 'K League 1',
    'A-League Men': 'A-League',
}


def extract_match_stats(stats_df):
    """
    從 all_statistics.csv 提取每場比賽的統計數據
    """
    print("正在處理 statistics 數據...")
    
    # 只取 Match overview 組的數據（包含進球、角球等核心數據）
    overview_stats = stats_df[stats_df['group'] == 'Match overview'].copy()
    
    # 創建一個空的結果 DataFrame
    matches = stats_df.groupby('event_id').first()[['match_date', 'tournament_name', 'category_name', 'home_team', 'away_team']].reset_index()
    print(f"  找到 {len(matches)} 場比賽")
    
    # 對每個 stat_name 進行透視
    result_df = matches.copy()
    
    # 處理每種統計類型 (移除 Goals因為從 shotmap 獲取)
    stat_mapping_no_goals = {k: v for k, v in STAT_MAPPING.items() if k != 'Goals'}
    for stat_name, (home_col, away_col) in stat_mapping_no_goals.items():
        stat_data = overview_stats[overview_stats['stat_name'] == stat_name][['event_id', 'home_value', 'away_value']].copy()
        
        if len(stat_data) > 0:
            # 轉換數值
            stat_data['home_value'] = pd.to_numeric(stat_data['home_value'], errors='coerce')
            stat_data['away_value'] = pd.to_numeric(stat_data['away_value'], errors='coerce')
            
            # 合併
            stat_data = stat_data.rename(columns={'home_value': home_col, 'away_value': away_col})
            result_df = result_df.merge(stat_data[['event_id', home_col, away_col]], on='event_id', how='left')
    
    print(f"  處理完成，{len(result_df)} 條記錄")
    return result_df


def extract_shotmap_aggregates(shotmap_df):
    """
    從 all_shotmap.csv 聚合 xG 數據和進球數
    """
    print("正在處理 shotmap 數據...")
    
    # 處理 xG 數據
    shotmap_df = shotmap_df.copy()
    shotmap_df['xg'] = pd.to_numeric(shotmap_df['xg'], errors='coerce')
    shotmap_df['xgot'] = pd.to_numeric(shotmap_df['xgot'], errors='coerce')
    
    # 計算進球數
    shotmap_df['is_goal'] = (shotmap_df['outcome'] == 'goal').astype(int)
    
    # 聚合函數
    agg_funcs = {
        'xg': ['sum', 'mean', 'count'],  # 總xG, 平均xG, 射門次數
        'xgot': ['sum', 'mean'],
        'is_goal': 'sum',  # 進球數
    }
    
    # 按 event_id 和 is_home 分組
    home_shots = shotmap_df[shotmap_df['is_home'] == True].groupby('event_id').agg(agg_funcs)
    away_shots = shotmap_df[shotmap_df['is_home'] == False].groupby('event_id').agg(agg_funcs)
    
    # 扁平化列名
    home_shots.columns = ['home_' + '_'.join(col).strip() for col in home_shots.columns.values]
    away_shots.columns = ['away_' + '_'.join(col).strip() for col in away_shots.columns.values]
    
    # 合併
    shot_agg = home_shots.join(away_shots, how='outer').reset_index()
    
    # 重命名列
    shot_agg = shot_agg.rename(columns={
        'home_xg_sum': 'home_xg_total',
        'home_xg_mean': 'home_xg_avg',
        'home_xg_count': 'home_shots_total',
        'home_xgot_sum': 'home_xgot_total',
        'home_xgot_mean': 'home_xgot_avg',
        'home_is_goal_sum': 'home_goals',  # 從 shotmap 提取進球數
        'away_xg_sum': 'away_xg_total',
        'away_xg_mean': 'away_xg_avg',
        'away_xg_count': 'away_shots_total',
        'away_xgot_sum': 'away_xgot_total',
        'away_xgot_mean': 'away_xgot_avg',
        'away_is_goal_sum': 'away_goals',  # 從 shotmap 提取進球數
    })
    
    # 填充 NaN 為 0
    numeric_cols = [c for c in shot_agg.columns if c != 'event_id']
    shot_agg[numeric_cols] = shot_agg[numeric_cols].fillna(0)
    
    print(f"  處理完成，{len(shot_agg)} 條記錄")
    return shot_agg


def get_season(date_str):
    """
    從日期推斷賽季
    """
    try:
        date = pd.to_datetime(date_str)
        year = date.year
        month = date.month
        
        # 8月-12月為該賽季的上半年
        # 1月-7月為該賽季的下半年
        if month >= 8:
            return f"{year}-{year+1}"
        else:
            return f"{year-1}-{year}"
    except:
        return None


def main():
    print("=" * 60)
    print("SofaScore 5年數據整合")
    print("=" * 60)
    
    # 讀取數據
    stats_path = os.path.join(DATA_DIR, 'all_statistics.csv')
    shotmap_path = os.path.join(DATA_DIR, 'all_shotmap.csv')
    
    print(f"\n讀取數據文件...")
    stats_df = pd.read_csv(stats_path)
    shotmap_df = pd.read_csv(shotmap_path)
    print(f"  Statistics: {len(stats_df)} 行")
    print(f"  Shotmap: {len(shotmap_df)} 行")
    
    # 提取比賽統計
    match_stats = extract_match_stats(stats_df)
    
    # 提取 xG 聚合數據
    shot_agg = extract_shotmap_aggregates(shotmap_df)
    
    # 合併數據
    print("\n合併數據...")
    result = match_stats.merge(shot_agg, on='event_id', how='left')
    
    # 添加聯賽名稱映射
    result['league'] = result['tournament_name'].map(LEAGUE_MAPPING).fillna(result['tournament_name'])
    
    # 添加賽季
    result['season'] = result['match_date'].apply(get_season)
    
    # 整理列順序
    final_columns = [
        'league', 'match_date', 'home_team', 'away_team',
        'home_goals', 'away_goals',  # 從 shotmap 提取
        'home_shots', 'away_shots',
        'home_shots_on', 'away_shots_on',
        'home_corners', 'away_corners',
        'home_yellow', 'away_yellow',
        'home_red', 'away_red',
        'home_fouls', 'away_fouls',
        'home_poss', 'away_poss',
        'home_shots_inside_box', 'away_shots_inside_box',
        'home_shots_outside_box', 'away_shots_outside_box',
        'home_saves', 'away_saves',
        # xG 數據
        'home_xg_total', 'away_xg_total',
        'home_xg_avg', 'away_xg_avg',
        'home_shots_total', 'away_shots_total',
        'home_xgot_total', 'away_xgot_total',
        'home_xgot_avg', 'away_xgot_avg',
        # 元數據
        'season', 'event_id', 'tournament_name'
    ]
    
    # 只保留存在的列
    final_columns = [c for c in final_columns if c in result.columns]
    result = result[final_columns]
    
    # 填充缺失值
    numeric_cols = result.select_dtypes(include=[np.number]).columns
    result[numeric_cols] = result[numeric_cols].fillna(0)
    
    # 排序
    result = result.sort_values('match_date')
    
    # 保存
    print(f"\n保存到 {OUTPUT_FILE}...")
    result.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    
    print(f"\n完成！")
    print(f"  總記錄數: {len(result)}")
    print(f"  聯賽數: {result['league'].nunique()}")
    print(f"  球隊數: {len(set(result['home_team'].unique()) | set(result['away_team'].unique()))}")
    print(f"  賽季數: {result['season'].nunique()}")
    print(f"  日期範圍: {result['match_date'].min()} ~ {result['match_date'].max()}")
    
    # 顯示樣本
    print("\n前5條記錄:")
    print(result.head())


if __name__ == '__main__':
    main()
