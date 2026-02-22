# -*- coding: utf-8 -*-
"""Quick data check script"""
import pandas as pd
import os

data_dir = r'C:\Users\Ryan\python\.vscode\fb_ai_bets\data\sofascore\5_years_data'

print("=== Shotmap Data ===")
shotmap_path = os.path.join(data_dir, 'all_shotmap.csv')
if os.path.exists(shotmap_path):
    shot_df = pd.read_csv(shotmap_path)
    print(f"Total rows: {len(shot_df)}")
    print(f"Columns: {shot_df.columns.tolist()}")
    print(f"xg not null: {shot_df['xg'].notna().sum()}")
    print(f"xgot not null: {shot_df['xgot'].notna().sum()}")
    print("\nSample rows:")
    print(shot_df.head(3))
else:
    print("Shotmap file not found!")

print("\n=== Statistics Data ===")
stats_path = os.path.join(data_dir, 'all_statistics.csv')
if os.path.exists(stats_path):
    stats_df = pd.read_csv(stats_path)
    print(f"Total rows: {len(stats_df)}")
    print(f"Unique matches: {stats_df['event_id'].nunique()}")
    print(f"Groups: {stats_df['group'].unique().tolist()}")
    print(f"Stat names sample: {stats_df['stat_name'].unique()[:20].tolist()}")
else:
    print("Statistics file not found!")
