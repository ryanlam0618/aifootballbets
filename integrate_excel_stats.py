#!/usr/bin/env python3
"""
Integrate additional match statistics from Excel files into history_data.csv
"""
import pandas as pd
import os
import re
from datetime import datetime

DATA_DIR = 'c:/Users/Ryan/python/.vscode/fb_ai_bets/data'
HISTORY_DATA_PATH = f'{DATA_DIR}/history_data.csv'
EXCEL_DIR = r'C:\Users\Ryan\Documents\data\Football data crawling tool\MatchPlayerData_English_v3'

# Columns to extract from Excel
TEAM_STATS_COLS = [
    'Corner', 'HalfCorner', 'YellowCard', 'RedCard', 
    'Shots', 'ShotsOnTarget', 'Attacks', 'DangerousAttacks',
    'ShotsOffTarget', 'ShotsBlocked', 'FreeKicks', 'Possession',
    'HalfPossession', 'Passes', 'PassSuccessRate', 'Fouls',
    'Offsides', 'Headers', 'HeadersSuccessful', 'Saves',
    'Tackles', 'Dribbles', 'ThrowIns', 'HitWoodwork',
    'Interceptions', 'Blocks', 'Assists', 'LongPasses', 'SuccessfulCrosses'
]

# Team name mappings
TEAM_NAME_MAPPINGS = {
    # J1 League
    'AlbirexNiigata': 'Albirex Niigata',
    'MachidaZelvia': 'Machida Zelvia',
    'TokyoVerdy': 'Tokyo Verdy',
    'KawasakiFrontale': 'Kawasaki Frontale',
    'KyotoSanga': 'Kyoto Sanga',
    'GambaOsaka': 'Gamba Osaka',
    'HiroshimaSanfrecce': 'Hiroshima Sanfrecce',
    'NagoyaGrampus': 'Nagoya Grampus',
    'KashimaAntlers': 'Kashima Antlers',
    'OkayamaGreen': 'Okayama Green',
    'ShonanBellmare': 'Shonan Bellmare',
    'YokohamaFMarinos': 'Yokohama F Marinos',
    'FCTokyo': 'FC Tokyo',
    'FCTokyo(中)': 'FC Tokyo',
    'ShimizuS-Pulse': 'Shimizu S-Pulse',
    'KashiwaReysol': 'Kashiwa Reysol',
    'AvispaFukuoka': 'Avispa Fukuoka',
    'KobeVissel': 'Vissel Kobe',
    'YokohamaFC': 'Yokohama FC',
    'UrawaRedDiamonds': 'Urawa Red Diamonds',
    'CerezoOsaka': 'Cerezo Osaka',
    'ConsadoleSapporo': 'Consadole Sapporo',
    'VegaltaSendai': 'Vegalta Sendai',
    'SaganTosu': 'Sagan Tosu',
    'OitaTrinita': 'Oita Trinita',
    # Premier League
    'AFC Bournemouth': 'AFC Bournemouth',
    'NottinghamForest': 'Nottingham Forest',
    'WestHamUnited': 'West Ham United',
    'BrightonHoveAlbion': 'Brighton & Hove Albion',
    'CrystalPalace': 'Crystal Palace',
    'WolverhamptonWanderers': 'Wolverhampton Wanderers',
    'TottenhamHotspur': 'Tottenham Hotspur',
    'ManchesterUnited': 'Manchester United',
    'NewcastleUnited': 'Newcastle United',
    'ManchesterCity': 'Manchester City',
    'LeicesterCity': 'Leicester City',
    'IpswichTown': 'Ipswich Town',
    'Southampton': 'Southampton',
    'AstonVilla': 'Aston Villa',
    'Everton': 'Everton',
    'Liverpool': 'Liverpool',
    'Chelsea': 'Chelsea',
    'Fulham': 'Fulham',
    'Brentford': 'Brentford',
    'Burnley': 'Burnley',
    'LeedsUnited': 'Leeds United',
    # La Liga
    'Villarreal': 'Villarreal',
    'AthleticBilbao': 'Athletic Bilbao',
    'Barcelona': 'Barcelona',
    '赫罗纳': 'Girona',
    'Sevilla': 'Sevilla',
    'AtleticoMadrid': 'Atletico Madrid',
    'RealMadrid': 'Real Madrid',
    'RealSociedad': 'Real Sociedad',
    'RayoVallecano': 'Rayo Vallecano',
    'Mallorca': 'RCD Mallorca',
    'Leganes': 'Leganés',
    'Valladolid': 'Valladolid',
    'Espanyol': 'Espanyol',
    'LasPalmas': 'Las Palmas',
    'Alaves': 'Deportivo Alavés',
    'Osasuna': 'Osasuna',
    'Getafe': 'Getafe',
    'CeltaVigo': 'Celta Vigo',
    '巴伦西亚': 'Valencia',
    # Serie A
    'Lazio': 'SS Lazio',
    'Lecce': 'Lecce',
    'Atalanta': 'Atalanta',
    'Parma': 'Parma',
    'Venezia': 'Venezia',
    'Juventus': 'Juventus',
    'Empoli': 'Empoli',
    'HellasVerona': 'Hellas Verona',
    'Udinese': 'Udinese',
    'Fiorentina': 'ACF Fiorentina',
    'Torino': 'Torino',
    'ASRoma': 'AS Roma',
    'ACMilan': 'AC Milan',
    'Monza': 'Monza',
    'Bologna': 'Bologna',
    'Genoa': 'Genoa',
    'Napoli': 'SSC Napoli',
    'Cagliari': 'Cagliari',
    'InterMilan': 'Inter Milan',
    'Como': 'Como',
}

def standardize_team_name(name):
    """Standardize team name"""
    if pd.isna(name):
        return name
    name = str(name).strip()
    if name in TEAM_NAME_MAPPINGS:
        return TEAM_NAME_MAPPINGS[name]
    return name

def parse_match_filename(filename):
    """Extract match info from filename"""
    # Pattern: YYYYMMDD_League_[Round]HomeTeam_vs_AwayTeam[Num].xlsx
    pattern = r'(\d{8})_(\w+?)\_\[(\d+)\](.+?)_vs_(.+?)\[(\d+)\]\.xlsx'
    match = re.match(pattern, filename)
    if match:
        date_str = match.group(1)
        league = match.group(2)
        home_team = match.group(4)
        away_team = match.group(5)
        
        # Format date
        date = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
        
        # Standardize team names
        home_team = standardize_team_name(home_team)
        away_team = standardize_team_name(away_team)
        
        return {
            'date': date,
            'league': league,
            'home_team': home_team,
            'away_team': away_team,
            'match_id': f"{date}_{home_team}_{away_team}"
        }
    return None

def load_excel_match_data(filepath):
    """Load and process Excel file"""
    try:
        df = pd.read_excel(filepath)
        
        # Rename TeamName column for consistency
        df['TeamName'] = df['TeamName'].apply(standardize_team_name)
        
        # Add home/away indicator
        df['is_home'] = df.index == 0  # First row is home team
        
        return df
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def create_match_stats_dataframe(excel_dir):
    """Process all Excel files and create match stats dataframe"""
    all_stats = []
    
    for filename in os.listdir(excel_dir):
        if not filename.endswith('.xlsx'):
            continue
        
        # Parse filename
        match_info = parse_match_filename(filename)
        if not match_info:
            continue
        
        # Load Excel data
        filepath = os.path.join(excel_dir, filename)
        df = load_excel_match_data(filepath)
        if df is None or len(df) != 2:
            continue
        
        # Process home team
        home_df = df[df['is_home'] == True].copy()
        if not home_df.empty:
            home_stats = {'match_id': match_info['match_id']}
            for col in TEAM_STATS_COLS:
                if col in home_df.columns:
                    home_stats[f'home_{col}'] = home_df[col].values[0]
            all_stats.append(home_stats)
        
        # Process away team
        away_df = df[df['is_home'] == False].copy()
        if not away_df.empty:
            away_stats = {'match_id': match_info['match_id']}
            for col in TEAM_STATS_COLS:
                if col in away_df.columns:
                    away_stats[f'away_{col}'] = away_df[col].values[0]
            # Merge with home stats
            for key, val in away_stats.items():
                if key in all_stats[-1]:
                    all_stats[-1][key] = val
    
    if all_stats:
        return pd.DataFrame(all_stats)
    return None

def main():
    print("=" * 60)
    print("Excel Data Integration Script")
    print("=" * 60)
    
    # Load history data
    print("\n[1/3] Loading history_data.csv...")
    history_df = pd.read_csv(HISTORY_DATA_PATH, low_memory=False)
    print(f"  Loaded {len(history_df)} matches")
    
    # Create match_id for history data if not exists
    if 'match_id' not in history_df.columns:
        history_df['match_id'] = (
            history_df['Date'].astype(str) + '_' + 
            history_df['home_team'].astype(str) + '_' + 
            history_df['away_team'].astype(str)
        )
    print(f"  Match IDs: {history_df['match_id'].notna().sum()}")
    
    # Load Excel data
    print("\n[2/3] Processing Excel files...")
    excel_stats = create_match_stats_dataframe(EXCEL_DIR)
    if excel_stats is not None:
        print(f"  Loaded {len(excel_stats)} match statistics from Excel files")
        print(f"  Columns: {len(excel_stats.columns)} team stat columns")
    else:
        print("  No Excel data loaded")
        return
    
    # Merge with history data
    print("\n[3/3] Merging datasets...")
    
    # Count matches to be merged
    merged = history_df.merge(excel_stats, on='match_id', how='left')
    merge_count = merged['home_Corner'].notna().sum()
    print(f"  Matches to merge: {merge_count}")
    
    # Get new columns to add
    new_cols = [col for col in excel_stats.columns if col not in history_df.columns]
    print(f"  New columns to add: {len(new_cols)}")
    
    # Update history_df with new columns
    for col in new_cols:
        history_df[col] = merged[col]
    
    # Save updated file
    history_df.to_csv(HISTORY_DATA_PATH, index=False)
    print(f"\n[SUCCESS] Saved {len(history_df)} matches to {HISTORY_DATA_PATH}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    print(f"Total matches: {len(history_df)}")
    print(f"Matches with Excel stats: {history_df['home_Corner'].notna().sum()}")
    
    print("\n" + "=" * 60)
    print("New columns added:")
    print("=" * 60)
    home_cols = [c for c in new_cols if c.startswith('home_')]
    away_cols = [c for c in new_cols if c.startswith('away_')]
    print(f"Home team stats ({len(home_cols)}):")
    for col in home_cols[:10]:
        print(f"  - {col}")
    if len(home_cols) > 10:
        print(f"  ... and {len(home_cols) - 10} more")
    print(f"\nAway team stats ({len(away_cols)}):")
    for col in away_cols[:10]:
        print(f"  - {col}")
    if len(away_cols) > 10:
        print(f"  ... and {len(away_cols) - 10} more")
    
    # Sample data
    print("\n" + "=" * 60)
    print("Sample data (matches with new stats):")
    print("=" * 60)
    sample = history_df[history_df['home_Corner'].notna()][
        ['Date', 'home_team', 'away_team', 'home_Corner', 'away_Corner', 
         'home_Possession', 'away_Possession', 'home_Shots', 'away_Shots']
    ].head(5)
    print(sample.to_string())

if __name__ == "__main__":
    main()
