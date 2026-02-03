#!/usr/bin/env python3
"""
Football Data Integration Script v2
Downloads data from football-data.co.uk and integrates with local matchlog data
"""

import urllib.request
import pandas as pd
import os
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# URLs for football-data.co.uk
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

# NEW local data directory
LOCAL_MATCH_DATA_DIR = r'C:\Users\Ryan\Documents\data\big_five_data\match_data'

# League to directory mapping
LEAGUE_DIR_MAP = {
    'Premier League': 'Premier-League',
    'Bundesliga': 'Bundesliga',
    'Serie A': 'Serie-A',
    'La Liga': 'La-Liga',
    'Ligue 1': 'Ligue-1',
}

# Team name mappings
TEAM_NAME_MAPPINGS = {
    # Premier League
    'Arsenal': 'Arsenal', 'Aston Villa': 'Aston Villa',
    'Bournemouth': 'AFC Bournemouth', 'Brentford': 'Brentford',
    'Brighton': 'Brighton & Hove Albion', 'Burnley': 'Burnley',
    'Chelsea': 'Chelsea', 'Crystal Palace': 'Crystal Palace',
    'Everton': 'Everton', 'Fulham': 'Fulham',
    'Ipswich': 'Ipswich Town', 'Leeds': 'Leeds United',
    'Leicester': 'Leicester City', 'Liverpool': 'Liverpool',
    'Man City': 'Manchester City', 'Man United': 'Manchester United',
    'Newcastle': 'Newcastle United', "Nott'm Forest": 'Nottingham Forest',
    'Southampton': 'Southampton', 'Tottenham': 'Tottenham Hotspur',
    'West Ham': 'West Ham United', 'Wolves': 'Wolverhampton Wanderers',
    # Bundesliga
    'Bayern': 'Bayern Munich', 'Dortmund': 'Borussia Dortmund',
    'Leverkusen': 'Bayer Leverkusen', "M'gladbach": "Borussia M'gladbach",
    'Köln': 'FC Koln', 'Eint Frankfurt': 'Eintracht Frankfurt',
    'Freiburg': 'SC Freiburg', 'RB Leipzig': 'RB Leipzig',
    'Stuttgart': 'VfB Stuttgart', 'Wolfsburg': 'VfL Wolfsburg',
    # Serie A
    'Juventus': 'Juventus', 'Inter': 'Inter Milan', 'Milan': 'AC Milan',
    'Roma': 'AS Roma', 'Lazio': 'SS Lazio', 'Napoli': 'SSC Napoli',
    'Atalanta': 'Atalanta', 'Torino': 'Torino', 'Fiorentina': 'ACF Fiorentina',
    'Genoa': 'Genoa', 'Udinese': 'Udinese', 'Cagliari': 'Cagliari',
    'Empoli': 'Empoli', 'Bologna': 'Bologna', 'Hellas Verona': 'Hellas Verona',
    'Lecce': 'Lecce', 'Parma': 'Parma', 'Venezia': 'Venezia',
    'Monza': 'Monza', 'Cremonese': 'Cremonese', 'Como': 'Como',
    # La Liga
    'Barcelona': 'Barcelona', 'Real Madrid': 'Real Madrid',
    'Atletico': 'Atletico Madrid', 'Sevilla': 'Sevilla',
    'Valencia': 'Valencia', 'Villarreal': 'Villarreal',
    'Real Sociedad': 'Real Sociedad', 'Athletic': 'Athletic Bilbao',
    'Betis': 'Real Betis', 'Getafe': 'Getafe', 'Celta': 'Celta Vigo',
    'Osasuna': 'Osasuna', 'Mallorca': 'RCD Mallorca',
    'Espanyol': 'Espanyol', 'Leganes': 'Leganés', 'Alaves': 'Deportivo Alavés',
    'Granada': 'Granada', 'Valladolid': 'Valladolid',
    'Rayo': 'Rayo Vallecano', 'Girona': 'Girona', 'Las Palmas': 'Las Palmas',
    # Ligue 1
    'PSG': 'Paris Saint-Germain', 'Lyon': 'Olympique Lyonnais',
    'Marseille': 'Olympique de Marseille', 'Monaco': 'Monaco',
    'Lille': 'Lille', 'Rennes': 'Rennes', 'Nice': 'OGC Nice',
    'Lens': 'RC Lens', 'Montpellier': 'Montpellier',
    'Bordeaux': 'Bordeaux', 'Nantes': 'Nantes',
    'Saint-Etienne': 'Saint-Étienne', 'Strasbourg': 'Strasbourg',
    'Reims': 'Reims', 'Brest': 'Brest', 'Metz': 'Metz',
    'Toulouse': 'Toulouse', 'Lorient': 'FC Lorient',
    'Le Havre': 'Le Havre', 'Auxerre': 'AJ Auxerre',
}

def standardize_team_name(name):
    """Standardize team name"""
    if pd.isna(name):
        return name
    name = str(name).strip()
    if name in TEAM_NAME_MAPPINGS:
        return TEAM_NAME_MAPPINGS[name]
    return name

def parse_date(date_str):
    """Parse date to standard format"""
    if pd.isna(date_str):
        return None
    date_str = str(date_str).strip()
    for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y', '%m/%d/%Y']:
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except:
            continue
    return date_str

def download_football_data(url):
    """Download CSV data from URL"""
    try:
        response = urllib.request.urlopen(url)
        return response.read().decode('utf-8')
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return None

def download_league_data(league_name, seasons):
    """Download data for a specific league"""
    all_data = []
    for season, url in seasons.items():
        print(f"  Downloading {league_name} {season}...")
        content = download_football_data(url)
        if content:
            from io import StringIO
            df = pd.read_csv(StringIO(content))
            df['season'] = season
            df['league'] = league_name
            all_data.append(df)
            print(f"    Downloaded {len(df)} matches")
    return pd.concat(all_data, ignore_index=True) if all_data else None

def process_football_data(df):
    """Process and clean football-data.co.uk data"""
    if df is None or df.empty:
        return None
    df['Date'] = df['Date'].apply(parse_date)
    df['HomeTeam'] = df['HomeTeam'].apply(standardize_team_name)
    df['AwayTeam'] = df['AwayTeam'].apply(standardize_team_name)
    df['match_id'] = df['Date'].astype(str) + '_' + df['HomeTeam'].astype(str) + '_' + df['AwayTeam'].astype(str)
    return df

def load_matchlog_data(league_name):
    """Load matchlog data from local files"""
    league_dir = LEAGUE_DIR_MAP.get(league_name)
    if not league_dir:
        return None
    
    league_path = os.path.join(LOCAL_MATCH_DATA_DIR, league_dir)
    if not os.path.exists(league_path):
        print(f"    Warning: {league_path} not found")
        return None
    
    all_matchlogs = []
    
    # League competition names
    league_comps = {
        'Premier League': ['Premier League'],
        'Bundesliga': ['Bundesliga'],
        'Serie A': ['Serie A'],
        'La Liga': ['La Liga'],
        'Ligue 1': ['Ligue 1'],
    }
    valid_comps = league_comps.get(league_name, [])
    
    for team_dir in os.listdir(league_path):
        team_path = os.path.join(league_path, team_dir)
        if not os.path.isdir(team_path):
            continue
        
        for file in os.listdir(team_path):
            if file.endswith('_matchlog.csv'):
                file_path = os.path.join(team_path, file)
                try:
                    df = pd.read_csv(file_path)
                    # Filter for league matches only
                    if 'Comp' in df.columns and valid_comps:
                        df = df[df['Comp'].isin(valid_comps)]
                    if not df.empty:
                        df['team'] = team_dir
                        all_matchlogs.append(df)
                except Exception as e:
                    pass
    
    if not all_matchlogs:
        return None
    
    combined = pd.concat(all_matchlogs, ignore_index=True)
    
    # Standardize opponent names
    if 'Opponent' in combined.columns:
        combined['Opponent'] = combined['Opponent'].apply(standardize_team_name)
    
    # Create match ID (home team perspective)
    combined['match_id'] = combined['Date'].astype(str) + '_' + \
                           combined['team'].astype(str) + '_' + \
                           combined['Opponent'].astype(str)
    
    return combined

def merge_formation_data(football_df, matchlog_df):
    """Merge formation, xG and possession data from matchlogs"""
    if football_df is None or matchlog_df is None:
        return football_df
    
    # Columns to merge
    extra_cols = ['match_id', 'xG', 'xGA', 'Poss', 'Formation', 'OppFormation']
    available_cols = [col for col in extra_cols if col in matchlog_df.columns]
    available_cols = [col for col in available_cols if col not in football_df.columns or football_df[col].isna().all()]
    
    if not available_cols:
        return football_df
    
    merge_df = matchlog_df[['match_id'] + available_cols].drop_duplicates(subset=['match_id'])
    
    # Drop rows where xG is NaN (they might be away team perspective)
    merge_df = merge_df.dropna(subset=['xG'])
    
    football_df = football_df.merge(merge_df, on='match_id', how='left')
    
    return football_df

def clean_and_format_dataset(df):
    """Clean and format final dataset"""
    if df is None or df.empty:
        return None
    
    # Define column order
    core_cols = ['league', 'Date', 'Time', 'HomeTeam', 'AwayTeam', 
                 'FTHG', 'FTAG', 'FTR', 'HTHG', 'HTAG', 'HTR']
    stats_cols = ['HS', 'AS', 'HST', 'AST', 'HC', 'AC', 'HF', 'AF', 'HY', 'AY', 'HR', 'AR']
    extra_cols = ['xG', 'xGA', 'Poss', 'Formation', 'OppFormation']
    odds_cols = ['B365H', 'B365D', 'B365A', 'BWH', 'BWD', 'BWA', 'PSH', 'PSD', 'PSA', 'WHH', 'WHD', 'WHA']
    other_cols = ['Referee', 'Div', 'season']
    
    # Build final columns
    final_cols = []
    for col in core_cols + stats_cols + extra_cols + odds_cols + other_cols:
        if col in df.columns:
            final_cols.append(col)
    
    # Add remaining columns
    for col in df.columns:
        if col not in final_cols:
            final_cols.append(col)
    
    df = df[[col for col in final_cols if col in df.columns]]
    
    # Rename columns
    rename_map = {
        'HomeTeam': 'home_team', 'AwayTeam': 'away_team',
        'FTHG': 'home_goals', 'FTAG': 'away_goals',
        'HTHG': 'ht_home_goals', 'HTAG': 'ht_away_goals',
        'HS': 'home_shots', 'AS': 'away_shots',
        'HST': 'home_shots_on', 'AST': 'away_shots_on',
        'HC': 'home_corners', 'AC': 'away_corners',
        'HF': 'home_fouls', 'AF': 'away_fouls',
        'HY': 'home_yellow', 'AY': 'away_yellow',
        'HR': 'home_red', 'AR': 'away_red',
    }
    df = df.rename(columns=rename_map)
    
    # Remove rows with missing essential data
    essential = ['Date', 'home_team', 'away_team', 'home_goals', 'away_goals']
    available_essential = [c for c in essential if c in df.columns]
    df = df.dropna(subset=available_essential)
    
    # Sort by date
    df = df.sort_values('Date', ascending=False).reset_index(drop=True)
    
    return df

def main():
    print("=" * 60)
    print("Football Data Integration Script v2")
    print("=" * 60)
    
    football_data = {}
    matchlog_data = {}
    
    # Download football-data.co.uk data
    print("\n[1/3] Downloading data from football-data.co.uk...")
    for league_name, seasons in LEAGUE_URLS.items():
        df = download_league_data(league_name, seasons)
        if df is not None:
            football_data[league_name] = process_football_data(df)
    
    # Load matchlog data
    print("\n[2/3] Loading matchlog data from local files...")
    for league_name in LEAGUE_URLS.keys():
        print(f"  Processing {league_name}...")
        matchlog_df = load_matchlog_data(league_name)
        if matchlog_df is not None:
            matchlog_data[league_name] = matchlog_df
            print(f"    Loaded {len(matchlog_df)} match records")
    
    # Merge data
    print("\n[3/3] Merging datasets...")
    for league_name in football_data.keys():
        if league_name in matchlog_data:
            before = len(football_data[league_name])
            football_data[league_name] = merge_formation_data(
                football_data[league_name], 
                matchlog_data[league_name]
            )
            after = football_data[league_name]['xG'].notna().sum()
            print(f"  {league_name}: Merged xG/Possession data for {after} matches")
    
    # Combine all leagues
    all_data = pd.concat(football_data.values(), ignore_index=True)
    
    # Clean and format
    final_df = clean_and_format_dataset(all_data)
    
    # Save
    final_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\n[SUCCESS] Saved {len(final_df)} matches to {OUTPUT_PATH}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary by League:")
    print("=" * 60)
    for league in final_df['league'].unique():
        count = len(final_df[final_df['league'] == league])
        xg_count = final_df[final_df['league'] == league]['xG'].notna().sum()
        print(f"  {league}: {count} matches ({xg_count} with xG data)")
    
    print("\n" + "=" * 60)
    print("Final Columns:")
    print("=" * 60)
    print(final_df.columns.tolist())
    
    print("\n" + "=" * 60)
    print("Sample Data:")
    print("=" * 60)
    print(final_df[['league', 'Date', 'home_team', 'away_team', 'home_goals', 'away_goals', 'xG', 'Poss', 'Formation']].head(10))

if __name__ == "__main__":
    main()
