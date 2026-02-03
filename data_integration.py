#!/usr/bin/env python3
"""
Football Data Integration Script
Downloads data from football-data.co.uk and integrates with local data sources
"""

import urllib.request
import pandas as pd
import os
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# URLs for football-data.co.uk
# League codes: E0=Premier, D1=Bundesliga, I1=Serie A, SP1=La Liga, F1=Ligue 1
LEAGUE_URLS = {
    'Premier League': {
        '19/20': 'https://www.football-data.co.uk/mmz4281/1920/E0.csv',
        '20/21': 'https://www.football-data.co.uk/mmz4281/2021/E0.csv',
        '21/22': 'https://www.football-data.co.uk/mmz4281/2122/E0.csv',
        '22/23': 'https://www.football-data.co.uk/mmz4281/2223/E0.csv',
        '23/24': 'https://www.football-data.co.uk/mmz4281/2324/E0.csv',
        '24/25': 'https://www.football-data.co.uk/mmz4281/2425/E0.csv',
    },
    'Bundesliga': {
        '19/20': 'https://www.football-data.co.uk/mmz4281/1920/D1.csv',
        '20/21': 'https://www.football-data.co.uk/mmz4281/2021/D1.csv',
        '21/22': 'https://www.football-data.co.uk/mmz4281/2122/D1.csv',
        '22/23': 'https://www.football-data.co.uk/mmz4281/2223/D1.csv',
        '23/24': 'https://www.football-data.co.uk/mmz4281/2324/D1.csv',
        '24/25': 'https://www.football-data.co.uk/mmz4281/2425/D1.csv',
    },
    'Serie A': {
        '19/20': 'https://www.football-data.co.uk/mmz4281/1920/I1.csv',
        '20/21': 'https://www.football-data.co.uk/mmz4281/2021/I1.csv',
        '21/22': 'https://www.football-data.co.uk/mmz4281/2122/I1.csv',
        '22/23': 'https://www.football-data.co.uk/mmz4281/2223/I1.csv',
        '23/24': 'https://www.football-data.co.uk/mmz4281/2324/I1.csv',
        '24/25': 'https://www.football-data.co.uk/mmz4281/2425/I1.csv',
    },
    'La Liga': {
        '19/20': 'https://www.football-data.co.uk/mmz4281/1920/SP1.csv',
        '20/21': 'https://www.football-data.co.uk/mmz4281/2021/SP1.csv',
        '21/22': 'https://www.football-data.co.uk/mmz4281/2122/SP1.csv',
        '22/23': 'https://www.football-data.co.uk/mmz4281/2223/SP1.csv',
        '23/24': 'https://www.football-data.co.uk/mmz4281/2324/SP1.csv',
        '24/25': 'https://www.football-data.co.uk/mmz4281/2425/SP1.csv',
    },
    'Ligue 1': {
        '19/20': 'https://www.football-data.co.uk/mmz4281/1920/F1.csv',
        '20/21': 'https://www.football-data.co.uk/mmz4281/2021/F1.csv',
        '21/22': 'https://www.football-data.co.uk/mmz4281/2122/F1.csv',
        '22/23': 'https://www.football-data.co.uk/mmz4281/2223/F1.csv',
        '23/24': 'https://www.football-data.co.uk/mmz4281/2324/F1.csv',
        '24/25': 'https://www.football-data.co.uk/mmz4281/2425/F1.csv',
    },
}

# Output paths
DATA_DIR = 'c:/Users/Ryan/python/.vscode/fb_ai_bets/data'
OUTPUT_PATH = f'{DATA_DIR}/big_five_history.csv'

# Local data files - using accessible ones
PREMIER_LEAGUE_DATA = f'{DATA_DIR}/premier_league_data.csv'
J1_LEAGUE_DATA = f'{DATA_DIR}/j1_league_data.csv'

# Team name mappings to standardize names across data sources
TEAM_NAME_MAPPINGS = {
    # Premier League
    'Arsenal': 'Arsenal',
    'Aston Villa': 'Aston Villa',
    'Bournemouth': 'AFC Bournemouth',
    'Brentford': 'Brentford',
    'Brighton': 'Brighton & Hove Albion',
    'Burnley': 'Burnley',
    'Chelsea': 'Chelsea',
    'Crystal Palace': 'Crystal Palace',
    'Everton': 'Everton',
    'Fulham': 'Fulham',
    'Ipswich': 'Ipswich Town',
    'Leeds': 'Leeds United',
    'Leicester': 'Leicester City',
    'Liverpool': 'Liverpool',
    'Man City': 'Manchester City',
    'Man United': 'Manchester United',
    'Manchester City': 'Manchester City',
    'Manchester United': 'Manchester United',
    'Newcastle': 'Newcastle United',
    'Newcastle Utd': 'Newcastle United',
    "Nott'm Forest": 'Nottingham Forest',
    'Southampton': 'Southampton',
    'Tottenham': 'Tottenham Hotspur',
    'West Ham': 'West Ham United',
    'Wolves': 'Wolverhampton Wanderers',
    # Bundesliga
    'Bayern': 'Bayern Munich',
    'Bayern Munich': 'Bayern Munich',
    'Dortmund': 'Borussia Dortmund',
    'Leverkusen': 'Bayer Leverkusen',
    "M'gladbach": "Borussia M'gladbach",
    'Gladbach': "Borussia M'gladbach",
    'Köln': 'FC Koln',
    'FC Koln': 'FC Koln',
    'Koln': 'FC Koln',
    'Eint Frankfurt': 'Eintracht Frankfurt',
    'Frankfurt': 'Eintracht Frankfurt',
    'Freiburg': 'SC Freiburg',
    'RB Leipzig': 'RB Leipzig',
    'Stuttgart': 'VfB Stuttgart',
    'Wolfsburg': 'VfL Wolfsburg',
    'Hoffenheim': 'TSG Hoffenheim',
    'Hertha': 'Hertha Berlin',
    'Union Berlin': 'Union Berlin',
    'Augsburg': 'FC Augsburg',
    'Bochum': 'VfL Bochum',
    'Mainz': 'Mainz 05',
    'Werder': 'Werder Bremen',
    'Heidenheim': '1. FC Heidenheim',
    'St. Pauli': 'St. Pauli',
    'Kiel': 'Holstein Kiel',
    # Serie A
    'Juventus': 'Juventus',
    'Inter': 'Inter Milan',
    'Inter Milan': 'Inter Milan',
    'Milan': 'AC Milan',
    'AC Milan': 'AC Milan',
    'Roma': 'AS Roma',
    'AS Roma': 'AS Roma',
    'Lazio': 'SS Lazio',
    'Napoli': 'SSC Napoli',
    'Atalanta': 'Atalanta',
    'Torino': 'Torino',
    'Sassuolo': 'US Sassuolo',
    'Fiorentina': 'ACF Fiorentina',
    'Genoa': 'Genoa',
    'Udinese': 'Udinese',
    'Cagliari': 'Cagliari',
    'Empoli': 'Empoli',
    'Bologna': 'Bologna',
    'Hellas Verona': 'Hellas Verona',
    'Lecce': 'Lecce',
    'Sampdoria': 'Sampdoria',
    'Parma': 'Parma',
    'Venezia': 'Venezia',
    'Monza': 'Monza',
    'Cremonese': 'Cremonese',
    'Crotone': 'Crotone',
    'Salernitana': 'Salernitana',
    'Spezia': 'Spezia',
    'Como': 'Como',
    # La Liga
    'Barcelona': 'Barcelona',
    'Real Madrid': 'Real Madrid',
    'Atletico': 'Atletico Madrid',
    'Atlético Madrid': 'Atletico Madrid',
    'Sevilla': 'Sevilla',
    'Valencia': 'Valencia',
    'Villarreal': 'Villarreal',
    'Real Sociedad': 'Real Sociedad',
    'Athletic': 'Athletic Bilbao',
    'Athletic Bilbao': 'Athletic Bilbao',
    'Betis': 'Real Betis',
    'Real Betis': 'Real Betis',
    'Getafe': 'Getafe',
    'Celta': 'Celta Vigo',
    'Celta Vigo': 'Celta Vigo',
    'Osasuna': 'Osasuna',
    'Mallorca': 'RCD Mallorca',
    'Espanyol': 'Espanyol',
    'Leganes': 'Leganés',
    'Leganés': 'Leganés',
    'Alaves': 'Deportivo Alavés',
    'Alavés': 'Deportivo Alavés',
    'Levante': 'Levante',
    'Granada': 'Granada',
    'Real Valladolid': 'Valladolid',
    'Valladolid': 'Valladolid',
    'Eibar': 'Eibar',
    'Cadiz': 'Cadiz',
    'Cádiz': 'Cadiz',
    'Huesca': 'Huesca',
    'Rayo': 'Rayo Vallecano',
    'Rayo Vallecano': 'Rayo Vallecano',
    'Girona': 'Girona',
    'Las Palmas': 'Las Palmas',
    'Elche': 'Elche',
    # Ligue 1
    'PSG': 'Paris Saint-Germain',
    'Paris S-G': 'Paris Saint-Germain',
    'Paris Saint-Germain': 'Paris Saint-Germain',
    'Lyon': 'Olympique Lyonnais',
    'Olympique Lyonnais': 'Olympique Lyonnais',
    'Marseille': 'Olympique de Marseille',
    'Olympique de Marseille': 'Olympique de Marseille',
    'Monaco': 'Monaco',
    'AS Monaco': 'Monaco',
    'Lille': 'Lille',
    'Rennes': 'Rennes',
    'Stade Rennais': 'Rennes',
    'Nice': 'OGC Nice',
    'OGC Nice': 'OGC Nice',
    'Lens': 'RC Lens',
    'RC Lens': 'RC Lens',
    'Montpellier': 'Montpellier',
    'Montpellier HSC': 'Montpellier',
    'Bordeaux': 'Bordeaux',
    'Nantes': 'Nantes',
    'Saint-Etienne': 'Saint-Étienne',
    'Saint Etienne': 'Saint-Étienne',
    'Strasbourg': 'Strasbourg',
    'RC Strasbourg': 'Strasbourg',
    'Reims': 'Reims',
    'Stade de Reims': 'Reims',
    'Angers': 'Angers',
    'Brest': 'Brest',
    'Stade Brestois': 'Brest',
    'Metz': 'Metz',
    'Toulouse': 'Toulouse',
    'Toulouse FC': 'Toulouse',
    'Nimes': 'Nimes',
    'Dijon': 'Dijon',
    'Lorient': 'FC Lorient',
    'Le Havre': 'Le Havre',
    'Auxerre': 'AJ Auxerre',
    # J1 League
    'Kawasaki Frontale': 'Kawasaki Frontale',
    'KawasakiFrontale': 'Kawasaki Frontale',
    'Yokohama F. Marinos': 'Yokohama F Marinos',
    'YokohamaFMarinos': 'Yokohama F Marinos',
    'FC Tokyo': 'FC Tokyo',
    'FCTokyo': 'FC Tokyo',
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
}


def download_football_data(url):
    """Download CSV data from URL"""
    try:
        response = urllib.request.urlopen(url)
        content = response.read().decode('utf-8')
        return content
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return None


def standardize_team_name(name):
    """Standardize team name using mappings"""
    if pd.isna(name):
        return name
    name = str(name).strip()
    # Try exact match first
    if name in TEAM_NAME_MAPPINGS:
        return TEAM_NAME_MAPPINGS[name]
    # Try case-insensitive match
    name_lower = name.lower()
    for key, value in TEAM_NAME_MAPPINGS.items():
        if key.lower() == name_lower:
            return value
    return name


def parse_date(date_str):
    """Parse date string to standard format"""
    if pd.isna(date_str):
        return None
    date_str = str(date_str).strip()
    try:
        # Try different date formats
        for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y', '%m/%d/%Y']:
            try:
                return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
            except:
                continue
        return date_str
    except:
        return date_str


def download_league_data(league_name, seasons):
    """Download data for a specific league and seasons"""
    all_data = []
    
    for season, url in seasons.items():
        print(f"Downloading {league_name} {season}...")
        content = download_football_data(url)
        
        if content:
            from io import StringIO
            df = pd.read_csv(StringIO(content))
            df['season'] = season
            df['league'] = league_name
            all_data.append(df)
            print(f"  Downloaded {len(df)} matches")
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return None


def process_football_data(df):
    """Process and clean football-data.co.uk data"""
    if df is None or df.empty:
        return None
    
    # Standardize column names
    df['Date'] = df['Date'].apply(parse_date)
    df['HomeTeam'] = df['HomeTeam'].apply(standardize_team_name)
    df['AwayTeam'] = df['AwayTeam'].apply(standardize_team_name)
    
    # Create unique match ID
    df['match_id'] = df['Date'].astype(str) + '_' + df['HomeTeam'].astype(str) + '_' + df['AwayTeam'].astype(str)
    
    return df


def load_premier_league_data(filepath):
    """Load additional Premier League data from local CSV"""
    if not os.path.exists(filepath):
        print(f"  Warning: Premier League data not found at {filepath}")
        return None
    
    try:
        df = pd.read_csv(filepath)
        
        # Keep only unique columns
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Standardize team names
        df['home_team'] = df['home_team'].apply(standardize_team_name)
        df['away_team'] = df['away_team'].apply(standardize_team_name)
        
        # Create match ID
        df['match_id'] = df['date'].astype(str) + '_' + df['home_team'].astype(str) + '_' + df['away_team'].astype(str)
        
        # Add xG data if available (from source_file)
        df['xG'] = None
        df['xGA'] = None
        
        return df
    except Exception as e:
        print(f"  Error loading Premier League data: {e}")
        return None


def load_j1_league_data(filepath):
    """Load and process J1 League data from local CSV"""
    if not os.path.exists(filepath):
        print(f"  Warning: J1 League data not found at {filepath}")
        return None
    
    try:
        df = pd.read_csv(filepath)
        
        # Keep only unique columns
        df = df.loc[:, ~df.columns.duplicated()]
        
        df['league'] = 'J1 League'
        df['season'] = '2024-2025'
        df['Date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        
        # Standardize team names
        df['home_team'] = df['home_team'].apply(standardize_team_name)
        df['away_team'] = df['away_team'].apply(standardize_team_name)
        
        # Create match ID
        df['match_id'] = df['Date'].astype(str) + '_' + df['home_team'].astype(str) + '_' + df['away_team'].astype(str)
        
        return df
    except Exception as e:
        print(f"  Error loading J1 League data: {e}")
        return None


def create_final_dataset(football_dfs, local_data):
    """Create final merged dataset"""
    all_data = []
    
    # Add football-data.co.uk data
    for league, df in football_dfs.items():
        if df is not None:
            # Keep only unique columns
            df = df.loc[:, ~df.columns.duplicated()]
            all_data.append(df)
    
    # Add local data
    if 'premier_league' in local_data and local_data['premier_league'] is not None:
        local_df = local_data['premier_league']
        local_df = local_df.loc[:, ~local_df.columns.duplicated()]
        all_data.append(local_df)
    
    if 'j1_league' in local_data and local_data['j1_league'] is not None:
        local_df = local_data['j1_league']
        local_df = local_df.loc[:, ~local_df.columns.duplicated()]
        all_data.append(local_df)
    
    if not all_data:
        return None
    
    # Combine all data
    combined = pd.concat(all_data, ignore_index=True)
    
    # Remove duplicates based on match_id
    combined = combined.drop_duplicates(subset=['match_id'], keep='first')
    
    return combined


def clean_and_format_dataset(df):
    """Final cleaning and formatting of dataset"""
    if df is None or df.empty:
        return None
    
    # Define final column order
    core_columns = [
        'league', 'Date', 'Time', 'HomeTeam', 'AwayTeam', 
        'FTHG', 'FTAG', 'FTR',  # Full time goals and result
        'HTHG', 'HTAG', 'HTR',  # Half time goals and result
    ]
    
    stats_columns = [
        'HS', 'AS', 'HST', 'AST',  # Shots and shots on target
        'HC', 'AC',  # Corners
        'HF', 'AF',  # Fouls
        'HY', 'AY', 'HR', 'AR',  # Yellow and red cards
    ]
    
    odds_columns = [
        'B365H', 'B365D', 'B365A',  # Bet365 odds
        'BWH', 'BWD', 'BWA',  # BetWin odds
        'IWH', 'IWD', 'IWA',  # Interwetten odds
        'PSH', 'PSD', 'PSA',  # Pinnacle odds
        'WHH', 'WHD', 'WHA',  # William Hill odds
        'VCH', 'VCD', 'VCA',  # VC Bet odds
    ]
    
    additional_columns = [
        'Referee',  # Referee
        'Div',  # Division
    ]
    
    xg_columns = ['xG', 'xGA']
    
    # Build final column list
    final_columns = []
    for col in core_columns:
        if col in df.columns:
            final_columns.append(col)
    
    for col in stats_columns:
        if col in df.columns:
            final_columns.append(col)
    
    for col in odds_columns:
        if col in df.columns:
            final_columns.append(col)
    
    for col in additional_columns:
        if col in df.columns:
            final_columns.append(col)
    
    for col in xg_columns:
        if col in df.columns:
            final_columns.append(col)
    
    # Add remaining columns
    for col in df.columns:
        if col not in final_columns and col not in ['match_id', 'season', 'home_rank', 'away_rank', 'source_file']:
            final_columns.append(col)
    
    # Filter to existing columns
    final_columns = [col for col in final_columns if col in df.columns]
    
    # Select and reorder columns
    df = df[final_columns]
    
    # Rename columns to cleaner names
    rename_map = {
        'HomeTeam': 'home_team',
        'AwayTeam': 'away_team',
        'FTHG': 'home_goals',
        'FTAG': 'away_goals',
        'HTHG': 'ht_home_goals',
        'HTAG': 'ht_away_goals',
        'HS': 'home_shots',
        'AS': 'away_shots',
        'HST': 'home_shots_on',
        'AST': 'away_shots_on',
        'HC': 'home_corners',
        'AC': 'away_corners',
        'HF': 'home_fouls',
        'AF': 'away_fouls',
        'HY': 'home_yellow',
        'AY': 'away_yellow',
        'HR': 'home_red',
        'AR': 'away_red',
    }
    
    df = df.rename(columns=rename_map)
    
    # Sort by date and league
    df = df.sort_values(['Date', 'league'], ascending=[False, True])
    
    # Reset index
    df = df.reset_index(drop=True)
    
    return df


def main():
    """Main function to run the data integration"""
    print("=" * 60)
    print("Football Data Integration Script")
    print("=" * 60)
    
    football_data = {}
    local_data = {}
    
    # Download football-data.co.uk data
    print("\n[1/4] Downloading data from football-data.co.uk...")
    for league_name, seasons in LEAGUE_URLS.items():
        df = download_league_data(league_name, seasons)
        if df is not None:
            df = process_football_data(df)
            football_data[league_name] = df
            print(f"  {league_name}: {len(df)} total matches")
    
    # Load local data
    print("\n[2/4] Loading local data files...")
    
    print("  Loading Premier League data...")
    pl_df = load_premier_league_data(PREMIER_LEAGUE_DATA)
    if pl_df is not None:
        local_data['premier_league'] = pl_df
        print(f"    Loaded {len(pl_df)} matches")
    
    print("  Loading J1 League data...")
    j1_df = load_j1_league_data(J1_LEAGUE_DATA)
    if j1_df is not None:
        local_data['j1_league'] = j1_df
        print(f"    Loaded {len(j1_df)} matches")
    
    # Skip complex merge - directly combine all data
    print("\n[3/4] Combining datasets...")
    
    # Create final dataset
    print("\n[4/4] Creating final dataset...")
    final_df = create_final_dataset(football_data, local_data)
    
    if final_df is not None:
        # Clean and format
        final_df = clean_and_format_dataset(final_df)
        
        # Save to CSV
        final_df.to_csv(OUTPUT_PATH, index=False)
        print(f"\n[SUCCESS] Saved {len(final_df)} matches to {OUTPUT_PATH}")
        
        # Print summary
        print("\n" + "=" * 60)
        print("Summary by League:")
        print("=" * 60)
        for league in final_df['league'].unique():
            count = len(final_df[final_df['league'] == league])
            print(f"  {league}: {count} matches")
        
        print("\n" + "=" * 60)
        print("Final columns:")
        print("=" * 60)
        print(final_df.columns.tolist())
        
        print("\n" + "=" * 60)
        print("Sample data (first 5 rows):")
        print("=" * 60)
        print(final_df.head())
    else:
        print("\n[ERROR] No data to save")


if __name__ == "__main__":
    main()
