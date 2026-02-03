#!/usr/bin/env python3
"""
Data Cleanup Script - Version 2
Removes duplicate columns, fixes team names, and consolidates data
"""
import pandas as pd
import os

INPUT_PATH = 'c:/Users/Ryan/python/.vscode/fb_ai_bets/data/big_five_history.csv'
OUTPUT_PATH = 'c:/Users/Ryan/python/.vscode/fb_ai_bets/data/big_five_history.csv'

# Team name mappings to standardize names
TEAM_NAME_MAPPINGS = {
    'Kawasaki Frontale': 'Kawasaki Frontale',
    'KawasakiFrontale': 'Kawasaki Frontale',
    'Yokohama F. Marinos': 'Yokohama F Marinos',
    'YokohamaFMarinos': 'Yokohama F Marinos',
    'FC Tokyo': 'FC Tokyo',
    'FCTokyo': 'FC Tokyo',
    'Tokyo': 'FC Tokyo',
    'Cerezo Osaka': 'Cerezo Osaka',
    'CerezoOsaka': 'Cerezo Osaka',
    'Gamba Osaka': 'Gamba Osaka',
    'GambaOsaka': 'Gamba Osaka',
    'Kashima Antlers': 'Kashima Antlers',
    'KashimaAntlers': 'Kashima Antlers',
    'Urawa Red Diamonds': 'Urawa Red Diamonds',
    'UrawaRedDiamonds': 'Urawa Red Diamonds',
    'Hiroshima Sanfrecce': 'Hiroshima Sanfrecce',
    'HiroshimaSanfrecce': 'Hiroshima Sanfrecce',
    'Nagoya Grampus': 'Nagoya Grampus',
    'NagoyaGrampus': 'Nagoya Grampus',
    'Kashiwa Reysol': 'Kashiwa Reysol',
    'KashiwaReysol': 'Kashiwa Reysol',
    'Shimizu S-Pulse': 'Shimizu S-Pulse',
    'ShimizuS-Pulse': 'Shimizu S-Pulse',
    'Consadole Sapporo': 'Consadole Sapporo',
    'ConsadoleSapporo': 'Consadole Sapporo',
    'Vegalta Sendai': 'Vegalta Sendai',
    'VegaltaSendai': 'Vegalta Sendai',
    'Sagan Tosu': 'Sagan Tosu',
    'SaganTosu': 'Sagan Tosu',
    'Vissel Kobe': 'Vissel Kobe',
    'KobeVissel': 'Vissel Kobe',
    'Shonan Bellmare': 'Shonan Bellmare',
    'ShonanBellmare': 'Shonan Bellmare',
    'Yokohama FC': 'Yokohama FC',
    'YokohamaFC': 'Yokohama FC',
    'Albirex Niigata': 'Albirex Niigata',
    'AlbirexNiigata': 'Albirex Niigata',
    'Tokyo Verdy': 'Tokyo Verdy',
    'TokyoVerdy': 'Tokyo Verdy',
    'Avispa Fukuoka': 'Avispa Fukuoka',
    'AvispaFukuoka': 'Avispa Fukuoka',
    'Oita Trinita': 'Oita Trinita',
    'OitaTrinita': 'Oita Trinita',
    'Kyoto Sanga': 'Kyoto Sanga',
    'KyotoSanga': 'Kyoto Sanga',
    'Machida Zelvia': 'Machida Zelvia',
    'MachidaZelvia': 'Machida Zelvia',
    'Okayama': 'Okayama Green',
    'Okayama FC': 'Okayama Green',
    'FCTokyo(中)': 'FC Tokyo',
}

def standardize_team_name(name):
    """Standardize team name using mappings"""
    if pd.isna(name):
        return name
    name = str(name).strip()
    if name in TEAM_NAME_MAPPINGS:
        return TEAM_NAME_MAPPINGS[name]
    return name

def cleanup_data():
    """Clean up the big_five_history.csv file"""
    print("=" * 60)
    print("Data Cleanup Script - Version 2")
    print("=" * 60)
    
    # Load the data
    print("\n[1/5] Loading data...")
    df = pd.read_csv(INPUT_PATH)
    print(f"  Loaded {len(df)} rows and {len(df.columns)} columns")
    
    # Remove columns that are entirely empty or mostly empty
    print("\n[2/5] Removing empty columns...")
    cols_to_drop = []
    for col in df.columns:
        non_null_ratio = df[col].notna().sum() / len(df)
        if non_null_ratio < 0.01:  # Less than 1% non-null
            cols_to_drop.append(col)
    
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
        print(f"  Removed {len(cols_to_drop)} mostly empty columns")
    
    # Rename columns with suffixes (.1, .2, etc.) to their base names
    print("\n[3/5] Fixing duplicate column names...")
    new_columns = {}
    for i, col in enumerate(df.columns):
        base_name = col.split('.')[0] if '.' in col else col
        if base_name in new_columns:
            # This is a duplicate, don't rename it
            continue
        new_columns[col] = base_name
    
    df = df.rename(columns=new_columns)
    print(f"  After fixing: {len(df.columns)} columns")
    
    # Fix J1 League team names
    print("\n[4/5] Standardizing team names...")
    j1_mask = df['league'] == 'J1 League'
    j1_count = j1_mask.sum()
    if j1_count > 0:
        # Check for date column (J1 data might have team names in date column)
        if 'date' in df.columns:
            # The date column might contain team names - check if date is actually team name
            sample_dates = df.loc[j1_mask, 'date'].dropna().head(10)
            if len(sample_dates) > 0:
                # If dates don't look like dates (they have team names), swap columns
                if not any('-' in str(d) for d in sample_dates):
                    print("  Swapping date and home_team columns for J1 League data...")
                    df.loc[j1_mask, 'date'] = df.loc[j1_mask, 'Date']
                    df.loc[j1_mask, 'Date'] = df.loc[j1_mask, 'date'].values
        
        # Standardize team names
        if 'home_team' in df.columns:
            df.loc[j1_mask, 'home_team'] = df.loc[j1_mask, 'home_team'].apply(standardize_team_name)
        if 'away_team' in df.columns:
            df.loc[j1_mask, 'away_team'] = df.loc[j1_mask, 'away_team'].apply(standardize_team_name)
        print(f"  Standardized {j1_count} J1 League team names")
    
    # Fix league names
    print("  Fixing league names...")
    league_mapping = {
        'PremierLeague': 'Premier League',
        'premier_league': 'Premier League',
        'premierleague': 'Premier League',
        'J1League': 'J1 League',
    }
    df['league'] = df['league'].replace(league_mapping)
    
    # Drop rows with missing essential data
    print("\n[5/5] Final cleanup...")
    essential_cols = ['Date', 'home_team', 'away_team', 'home_goals', 'away_goals']
    available_essential = [col for col in essential_cols if col in df.columns]
    
    # Check for rows where essential data is missing
    missing_mask = df[available_essential].isna().any(axis=1)
    missing_count = missing_mask.sum()
    if missing_count > 0:
        print(f"  Removing {missing_count} rows with missing essential data")
        df = df[~missing_mask]
    
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
    print("Final Columns (first 30):")
    print("=" * 60)
    for i, col in enumerate(df.columns[:30], 1):
        print(f"  {i}. {col}")
    if len(df.columns) > 30:
        print(f"  ... and {len(df.columns) - 30} more columns")
    
    print("\n" + "=" * 60)
    print("Sample Data (first 10 rows):")
    print("=" * 60)
    print(df[['league', 'Date', 'home_team', 'away_team', 'home_goals', 'away_goals', 'FTR']].head(10))

if __name__ == "__main__":
    cleanup_data()
