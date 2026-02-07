import pandas as pd
import numpy as np
import glob
import os

print('='*70)
print('INTEGRATING xG DATA FROM big_five_data TO history_data.csv')
print('='*70)

# Load main history data
main_df = pd.read_csv('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv')
main_df.columns = main_df.columns.str.strip().str.lower().str.replace('\ufeff', '')
print(f'\n[1] Main history_data.csv: {len(main_df)} rows')
print(f'    Existing xG data: {main_df["xg"].notna().sum()} matches')

# Load all data from big_five_data
base_path = 'c:/Users/Ryan/Documents/data/big_five_data/match_data'
all_leagues = ['Premier-League', 'La-Liga', 'Serie-A', 'Bundesliga', 'Ligue-1']
league_map = {
    'Premier-League': 'Premier League',
    'La-Liga': 'La Liga',
    'Serie-A': 'Serie A',
    'Bundesliga': 'Bundesliga',
    'Ligue-1': 'Ligue 1'
}

# Team name mapping from big_five_data to history_data.csv
TEAM_NAME_MAP = {
    # Premier League - Teams (folder names)
    'Manchester Utd': 'Manchester United',
    'Man City': 'Manchester City',
    'Spurs': 'Tottenham Hotspur',
    'Tottenham': 'Tottenham Hotspur',
    'Wolves': 'Wolverhampton Wanderers',
    'West Ham': 'West Ham United',
    'Nott\'ham Forest': 'Nottingham Forest',
    'Newcastle': 'Newcastle United',
    'Newcastle Utd': 'Newcastle United',
    'Leicester': 'Leicester City',
    'Leeds': 'Leeds United',
    'Brighton': 'Brighton & Hove Albion',
    'Crystal Palace': 'Crystal Palace',
    'AFC Bournemouth': 'AFC Bournemouth',
    'Brentford': 'Brentford',
    'Burnley': 'Burnley',
    'Fulham': 'Fulham',
    'Ipswich': 'Ipswich Town',
    'Southampton': 'Southampton',
    'Aston Villa': 'Aston Villa',
    'Arsenal': 'Arsenal',
    'Chelsea': 'Chelsea',
    'Liverpool': 'Liverpool',
    'Everton': 'Everton',
    
    # Premier League - Opponents in big_five_data
    'Bournemouth': 'AFC Bournemouth',
    'Tottenham Hotspur': 'Tottenham Hotspur',
    'Newcastle United': 'Newcastle United',
    'Nottingham Forest': 'Nottingham Forest',
    'Wolverhampton': 'Wolverhampton Wanderers',
    'West Brom': 'West Bromwich Albion',
    'Norwich': 'Norwich City',
    'Swansea': 'Swansea City',
    'Watford': 'Watford',
    'Huddersfield': 'Huddersfield Town',
    'Cardiff': 'Cardiff City',
    
    # La Liga
    'Atl Madrid': 'Ath Madrid',
    'Sevilla': 'Sevilla',
    'Real Sociedad': 'Real Sociedad',
    'Real Betis': 'Real Betis',
    'Celta Vigo': 'Celta Vigo',
    'Osasuna': 'Osasuna',
    'Valencia': 'Valencia',
    'Villarreal': 'Villarreal',
    'Espanyol': 'Espanyol',
    'Girona': 'Girona',
    'Almeria': 'Almeria',
    'Cadiz': 'Cadiz',
    'Mallorca': 'Mallorca',
    'Getafe': 'Getafe',
    'Real Madrid': 'Real Madrid',
    'Barcelona': 'Barcelona',
    'Athletic': 'Athletic Bilbao',
    'Athletic Club': 'Athletic Bilbao',
    'Betis': 'Real Betis',
    
    # Serie A
    'AC Milan': 'AC Milan',
    'Inter Milan': 'Inter Milan',
    'Atalanta': 'Atalanta BC',
    'AS Roma': 'AS Roma',
    'Lazio': 'Lazio',
    'Juventus': 'Juventus',
    'Napoli': 'SSC Napoli',
    'Fiorentina': 'Fiorentina',
    'Sampdoria': 'Sampdoria',
    'Udinese': 'Udinese',
    'Bologna': 'Bologna',
    'Torino': 'Torino',
    'Sassuolo': 'Sassuolo',
    'Empoli': 'Empoli',
    'Lecce': 'Lecce',
    'Salernitana': 'Salernitana',
    'Cremonese': 'Cremonese',
    'Monza': 'Monza',
    'Hellas Verona': 'Hellas Verona',
    'Genoa': 'Genoa',
    'Cagliari': 'Cagliari',
    'Parma': 'Parma',
    'Venezia': 'Venezia',
    'Como': 'Como',
    
    # Bundesliga
    'Bayern Munich': 'Bayern Munich',
    'Dortmund': 'Borussia Dortmund',
    'Leverkusen': 'Bayer Leverkusen',
    'RB Leipzig': 'RB Leipzig',
    'M\'gladbach': 'Borussia Mönchengladbach',
    'Frankfurt': 'Eintracht Frankfurt',
    'Wolfsburg': 'Wolfsburg',
    'Stuttgart': 'Stuttgart',
    'Freiburg': 'Freiburg',
    'Hoffenheim': 'Hoffenheim',
    'Bremen': 'Werder Bremen',
    'Augsburg': 'Augsburg',
    'Mainz': 'Mainz 05',
    'Union Berlin': 'Union Berlin',
    'Bochum': 'Bochum',
    'Hertha': 'Hertha BSC',
    'Schalke': 'Schalke 04',
    'Darmstadt': 'Darmstadt 98',
    'Heidenheim': 'Heidenheim',
    'Kiel': 'Holstein Kiel',
    'St. Pauli': 'St. Pauli',
    
    # Ligue 1
    'PSG': 'Paris SG',
    'Lyon': 'Olympique Lyonnais',
    'Marseille': 'Olympique de Marseille',
    'Monaco': 'Monaco',
    'Lille': 'Lille',
    'Nice': 'OGC Nice',
    'Rennes': 'Stade Rennais',
    'Bordeaux': 'Bordeaux',
    'Nantes': 'Nantes',
    'Montpellier': 'Montpellier',
    'Lens': 'Lens',
    'Lorient': 'Lorient',
    'Reims': 'Reims',
    'Toulouse': 'Toulouse',
    'Brest': 'Brest',
    'Strasbourg': 'Strasbourg',
    'Auxerre': 'Auxerre',
    'Angers': 'Angers',
    'Clermont': 'Clermont Foot',
}

all_new_data = []

for league in all_leagues:
    league_path = os.path.join(base_path, league)
    if not os.path.exists(league_path):
        continue
    
    print(f'\n[2] Processing {league}...')
    
    # Get all team folders
    team_folders = [f for f in os.listdir(league_path) if os.path.isdir(os.path.join(league_path, f))]
    
    for team in team_folders:
        team_path = os.path.join(league_path, team)
        
        # Get all matchlog files
        for filepath in glob.glob(os.path.join(team_path, '*_matchlog.csv')):
            try:
                df = pd.read_csv(filepath)
                
                # Process each match
                for _, row in df.iterrows():
                    # Determine if home or away
                    venue = str(row.get('Venue', '')).lower()
                    is_home = 'home' in venue or venue == 'h'
                    
                    # Map team names
                    original_team = row.get('Team', team)
                    original_opponent = row.get('Opponent', '')
                    
                    team_name = TEAM_NAME_MAP.get(original_team, original_team)
                    opponent = TEAM_NAME_MAP.get(original_opponent, original_opponent)
                    
                    # Convert xG to float
                    try:
                        xg = float(row.get('xG', np.nan))
                    except:
                        xg = np.nan
                    
                    try:
                        xga = float(row.get('xGA', np.nan))
                    except:
                        xga = np.nan
                    
                    try:
                        gf = int(row.get('GF', 0))
                    except:
                        gf = 0
                    
                    try:
                        ga = int(row.get('GA', 0))
                    except:
                        ga = 0
                    
                    # Create record
                    record = {
                        'league': league_map.get(league, league),
                        'date': row.get('Date', ''),
                        'time': row.get('Time', ''),
                        'home_team': team_name if is_home else opponent,
                        'away_team': opponent if is_home else team_name,
                        'home_goals': gf if is_home else ga,
                        'away_goals': ga if is_home else gf,
                        'ftr': 'H' if gf > ga else ('D' if gf == ga else 'A'),
                        'xg': xg if is_home else xga,
                        'xga': xga if is_home else xg,
                        'season': row.get('Season', ''),
                    }
                    
                    all_new_data.append(record)
                    
            except Exception as e:
                continue

print(f'\n[3] Total new xG data records: {len(all_new_data)}')

if all_new_data:
    new_df = pd.DataFrame(all_new_data)
    
    # Check Manchester United
    mu_new = new_df[(new_df['home_team'] == 'Manchester United') | (new_df['away_team'] == 'Manchester United')]
    print(f'    Manchester United: {len(mu_new)} matches with {mu_new["xg"].notna().sum()} xG records')
    
    # Check Newcastle
    newcastle_new = new_df[(new_df['home_team'] == 'Newcastle United') | (new_df['away_team'] == 'Newcastle United')]
    print(f'    Newcastle United: {len(newcastle_new)} matches with {newcastle_new["xg"].notna().sum()} xG records')
    
    # Strategy: Update xG values where they are NaN in main_df
    print(f'\n[4] Updating history_data.csv with new xG values...')
    
    # Create a merge key
    def create_match_key(row):
        return f"{str(row['date'])}_{row['home_team']}_{row['away_team']}"
    
    new_df['match_key'] = new_df.apply(create_match_key, axis=1)
    main_df['match_key'] = main_df.apply(create_match_key, axis=1)
    
    # Find matches in main_df that have NaN xG
    nan_xg_matches = main_df[main_df['xg'].isna()]['match_key'].tolist()
    print(f'    Matches in main_df with NaN xG: {len(nan_xg_matches)}')
    
    # Filter new_df to only include matches with NaN xG
    new_df_to_update = new_df[new_df['match_key'].isin(nan_xg_matches)]
    print(f'    Matches from big_five_data to add: {len(new_df_to_update)}')
    
    # Update main_df
    update_count = 0
    for _, new_row in new_df_to_update.iterrows():
        idx = main_df[main_df['match_key'] == new_row['match_key']].index
        if len(idx) > 0:
            main_df.loc[idx[0], 'xg'] = new_row['xg']
            main_df.loc[idx[0], 'xga'] = new_row['xga']
            update_count += 1
    
    print(f'    Updated records: {update_count}')
    
    # Final statistics
    print(f'\n[5] Final Statistics:')
    print(f'    Total matches: {len(main_df)}')
    print(f'    Matches with xG: {main_df["xg"].notna().sum()}')
    print(f'    Matches without xG: {main_df["xg"].isna().sum()}')
    
    # Check big 6 Premier League teams
    print(f'\n[6] Premier League Big 6 xG coverage:')
    big_6 = ['Manchester United', 'Manchester City', 'Liverpool', 'Chelsea', 'Arsenal', 'Tottenham Hotspur']
    for team in big_6:
        team_matches = main_df[(main_df['home_team'] == team) | (main_df['away_team'] == team)]
        has_xg = team_matches['xg'].notna().sum()
        total = len(team_matches)
        print(f'    {team}: {has_xg}/{total} ({100*has_xg/total:.1f}%)')
    
    # Save updated file
    print(f'\n[7] Saving updated history_data.csv...')
    output_path = 'c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv'
    main_df.drop('match_key', axis=1, errors='ignore').to_csv(output_path, index=False)
    print(f'    Saved to: {output_path}')
    
    print('\n' + '='*70)
    print('INTEGRATION COMPLETE!')
    print('='*70)
