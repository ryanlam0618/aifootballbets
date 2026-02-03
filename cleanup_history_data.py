#!/usr/bin/env python3
"""
Data Cleanup Script - Clean and organize history_data.csv
"""
import pandas as pd
import os

INPUT_PATH = 'c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv'
OUTPUT_PATH = 'c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv'

def cleanup_data():
    print("=" * 60)
    print("Data Cleanup Script")
    print("=" * 60)
    
    # Load data
    print("\n[1/5] Loading data...")
    df = pd.read_csv(INPUT_PATH, low_memory=False)
    print(f"  Loaded {len(df)} rows, {len(df.columns)} columns")
    
    # Remove duplicate columns
    print("\n[2/5] Removing duplicate columns...")
    df = df.loc[:, ~df.columns.duplicated()]
    print(f"  After removing duplicates: {len(df.columns)} columns")
    
    # Define clean column order
    print("\n[3/5] Organizing columns...")
    
    core_cols = [
        'league', 'Date', 'Time', 'home_team', 'away_team',
        'home_goals', 'away_goals', 'FTR',
        'ht_home_goals', 'ht_away_goals', 'HTR',
    ]
    
    match_stats = [
        'home_shots', 'away_shots',
        'home_shots_on', 'away_shots_on',
        'home_corners', 'away_corners',
        'home_fouls', 'away_fouls',
        'home_yellow', 'away_yellow',
        'home_red', 'away_red',
    ]
    
    xg_cols = ['xG', 'xGA', 'Poss', 'Formation', 'OppFormation']
    
    odds_cols = [
        'B365H', 'B365D', 'B365A',
        'BWH', 'BWD', 'BWA',
        'PSH', 'PSD', 'PSA',
        'WHH', 'WHD', 'WHA',
    ]
    
    extra_info = ['Referee', 'Div', 'season', 'match_id']
    
    # Build final column list
    final_cols = []
    for col in core_cols + match_stats + xg_cols + odds_cols + extra_info:
        if col in df.columns and col not in final_cols:
            final_cols.append(col)
    
    # Add any remaining columns
    for col in df.columns:
        if col not in final_cols:
            final_cols.append(col)
    
    df = df[[c for c in final_cols if c in df.columns]]
    
    # Standardize league names
    print("\n[4/5] Standardizing data...")
    league_map = {
        'PremierLeague': 'Premier League',
        'PremierLeague': 'Premier League',
        'J1League': 'J1 League',
    }
    df['league'] = df['league'].replace(league_map)
    
    # Fix J1 League team names
    j1_mask = df['league'] == 'J1 League'
    if j1_mask.any():
        j1_teams = {
            'OkayamaGreen': 'Okayama Green',
            'KawasakiFrontale': 'Kawasaki Frontale',
            'YokohamaFMarinos': 'Yokohama F Marinos',
            'FCTokyo': 'FC Tokyo',
            'FCTokyo(中)': 'FC Tokyo',
        }
        for old, new in j1_teams.items():
            df.loc[j1_mask & (df['home_team'] == old), 'home_team'] = new
            df.loc[j1_mask & (df['away_team'] == old), 'away_team'] = new
    
    # Sort by date and league
    df = df.sort_values(['Date', 'league'], ascending=[False, True])
    df = df.reset_index(drop=True)
    
    # Save
    print("\n[5/5] Saving data...")
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"  Saved {len(df)} matches to {OUTPUT_PATH}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    print(f"\nTotal matches: {len(df)}")
    print(f"Total columns: {len(df.columns)}")
    
    print("\nBy League:")
    for league in df['league'].unique():
        count = len(df[df['league'] == league])
        xg_count = df[df['league'] == league]['xG'].notna().sum()
        print(f"  {league}: {count} matches ({xg_count} with xG)")
    
    print("\nColumn list:")
    for i, col in enumerate(df.columns, 1):
        non_null = df[col].notna().sum()
        print(f"  {i:2d}. {col:25s} ({non_null:,} non-null)")
    
    print("\n" + "=" * 60)
    print("Sample data:")
    print("=" * 60)
    print(df[['league', 'Date', 'home_team', 'away_team', 'home_goals', 'away_goals']].head(10).to_string())

if __name__ == "__main__":
    cleanup_data()
