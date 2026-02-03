#!/usr/bin/env python3
"""
Data Cleanup Script
Removes duplicate columns and consolidates data in big_five_history.csv
"""
import pandas as pd
import os

INPUT_PATH = 'c:/Users/Ryan/python/.vscode/fb_ai_bets/data/big_five_history.csv'
OUTPUT_PATH = 'c:/Users/Ryan/python/.vscode/fb_ai_bets/data/big_five_history.csv'

# Columns to keep (in order)
PRIMARY_COLUMNS = [
    'league',           # League name
    'Date',             # Match date
    'Time',             # Match time
    'home_team',        # Home team name
    'away_team',        # Away team name
    'home_goals',       # Home team goals
    'away_goals',      # Away team goals
    'FTR',             # Full Time Result (H/D/A)
    'ht_home_goals',   # Half time home goals
    'ht_away_goals',   # Half time away goals
    'HTR',             # Half Time Result
]

# Stats columns
STATS_COLUMNS = [
    'home_shots',       # Home shots
    'away_shots',       # Away shots
    'home_shots_on',    # Home shots on target
    'away_shots_on',    # Away shots on target
    'home_corners',     # Home corners
    'away_corners',     # Away corners
    'home_fouls',       # Home fouls
    'away_fouls',       # Away fouls
    'home_yellow',      # Home yellow cards
    'away_yellow',      # Away yellow cards
    'home_red',         # Home red cards
    'away_red',         # Away red cards
]

# xG columns
XG_COLUMNS = [
    'xG',              # Expected goals (home)
    'xGA',             # Expected goals against
]

# Odds columns - keep only main bookmakers
ODDS_COLUMNS = [
    'B365H', 'B365D', 'B365A',  # Bet365
    'BWH', 'BWD', 'BWA',        # BetWin
    'PSH', 'PSD', 'PSA',        # Pinnacle
    'WHH', 'WHD', 'WHA',       # William Hill
]

# Asian Handicap columns
AH_COLUMNS = [
    'AHh',              # Asian Handicap home
    'B365AHH', 'B365AHA',  # Bet365 AH
    'PAHH', 'PAHA',         # Pinnacle AH
]

# Over/Under columns
OU_COLUMNS = [
    'B365>2.5', 'B365<2.5',  # Bet365 O/U
    'Avg>2.5', 'Avg<2.5',    # Average O/U
]

# Additional columns
EXTRA_COLUMNS = [
    'Referee',         # Referee name
    'Div',             # Division code
]

def cleanup_data():
    """Clean up the big_five_history.csv file"""
    print("=" * 60)
    print("Data Cleanup Script")
    print("=" * 60)
    
    # Load the data
    print("\n[1/3] Loading data...")
    df = pd.read_csv(INPUT_PATH)
    print(f"  Loaded {len(df)} rows and {len(df.columns)} columns")
    
    # Remove duplicate columns (keep first occurrence)
    print("\n[2/3] Removing duplicate columns...")
    df = df.loc[:, ~df.columns.duplicated()]
    print(f"  After removing duplicates: {len(df.columns)} columns")
    
    # Define the final column order
    final_columns = []
    for col in PRIMARY_COLUMNS:
        if col in df.columns:
            final_columns.append(col)
    
    for col in STATS_COLUMNS:
        if col in df.columns:
            final_columns.append(col)
    
    for col in XG_COLUMNS:
        if col in df.columns:
            final_columns.append(col)
    
    for col in ODDS_COLUMNS:
        if col in df.columns:
            final_columns.append(col)
    
    for col in AH_COLUMNS:
        if col in df.columns:
            final_columns.append(col)
    
    for col in OU_COLUMNS:
        if col in df.columns:
            final_columns.append(col)
    
    for col in EXTRA_COLUMNS:
        if col in df.columns:
            final_columns.append(col)
    
    # Add any remaining columns
    for col in df.columns:
        if col not in final_columns:
            final_columns.append(col)
    
    # Filter to existing columns
    final_columns = [col for col in final_columns if col in df.columns]
    
    # Select and reorder columns
    df = df[final_columns]
    
    # Fix league names
    print("\n[3/3] Standardizing league names...")
    league_mapping = {
        'PremierLeague': 'Premier League',
        'premier_league': 'Premier League',
        'premierleague': 'Premier League',
    }
    df['league'] = df['league'].replace(league_mapping)
    
    # Sort by date and league
    df = df.sort_values(['Date', 'league'], ascending=[False, True])
    
    # Reset index
    df = df.reset_index(drop=True)
    
    # Save to CSV
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\n[SUCCESS] Saved {len(df)} matches to {OUTPUT_PATH}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("Summary by League:")
    print("=" * 60)
    for league in df['league'].unique():
        count = len(df[df['league'] == league])
        print(f"  {league}: {count} matches")
    
    print("\n" + "=" * 60)
    print("Final Columns:")
    print("=" * 60)
    for i, col in enumerate(df.columns, 1):
        print(f"  {i}. {col}")
    
    print("\n" + "=" * 60)
    print("Sample Data:")
    print("=" * 60)
    print(df[['league', 'Date', 'home_team', 'away_team', 'home_goals', 'away_goals', 'FTR']].head(10))

if __name__ == "__main__":
    cleanup_data()
