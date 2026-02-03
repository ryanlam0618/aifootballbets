#!/usr/bin/env python3
"""
Create Clean History Data - Minimal version with essential columns only
"""
import pandas as pd

INPUT_PATH = 'c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv'
OUTPUT_PATH = 'c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data_clean.csv'

def create_clean_data():
    print("=" * 60)
    print("Creating Clean History Data")
    print("=" * 60)
    
    # Load data
    print("\n[1/3] Loading data...")
    df = pd.read_csv(INPUT_PATH, low_memory=False)
    print(f"  Loaded {len(df)} rows, {len(df.columns)} columns")
    
    # Keep only essential columns
    print("\n[2/3] Selecting essential columns...")
    
    essential_cols = [
        # Identity
        'league', 'Date', 'Time', 'home_team', 'away_team',
        # Results
        'home_goals', 'away_goals', 'FTR',
        'ht_home_goals', 'ht_away_goals', 'HTR',
        # Match Stats
        'home_shots', 'away_shots',
        'home_shots_on', 'away_shots_on',
        'home_corners', 'away_corners',
        'home_fouls', 'away_fouls',
        'home_yellow', 'away_yellow',
        'home_red', 'away_red',
        # Advanced Stats (xG)
        'xG', 'xGA', 'Poss',
        # Odds
        'B365H', 'B365D', 'B365A',
        'PSH', 'PSD', 'PSA',
        # Info
        'season',
    ]
    
    # Filter to existing columns
    cols = [c for c in essential_cols if c in df.columns]
    df_clean = df[cols].copy()
    
    # Remove duplicate rows
    df_clean = df_clean.drop_duplicates()
    
    # Standardize league names
    df_clean['league'] = df_clean['league'].replace({
        'PremierLeague': 'Premier League',
        'J1League': 'J1 League',
    })
    
    # Sort by date
    df_clean = df_clean.sort_values(['Date', 'league'], ascending=[False, True])
    df_clean = df_clean.reset_index(drop=True)
    
    # Save
    print("\n[3/3] Saving...")
    df_clean.to_csv(OUTPUT_PATH, index=False)
    print(f"  Saved {len(df_clean)} matches to {OUTPUT_PATH}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    print(f"\nTotal matches: {len(df_clean)}")
    print(f"Total columns: {len(df_clean.columns)}")
    
    print("\nBy League:")
    for league in df_clean['league'].unique():
        count = len(df_clean[df_clean['league'] == league])
        xg_count = df_clean[df_clean['league'] == league]['xG'].notna().sum()
        print(f"  {league}: {count} matches ({xg_count} with xG)")
    
    print("\nColumns:")
    for i, col in enumerate(df_clean.columns, 1):
        non_null = df_clean[col].notna().sum()
        print(f"  {i:2d}. {col:20s} ({non_null:,} values)")
    
    print("\n" + "=" * 60)
    print("Sample Data:")
    print("=" * 60)
    print(df_clean[['league', 'Date', 'home_team', 'away_team', 'home_goals', 'away_goals', 'xG', 'Poss']].head(10).to_string())

if __name__ == "__main__":
    create_clean_data()
