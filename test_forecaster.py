import sys
sys.path.insert(0, 'c:/Users/Ryan/python/.vscode/fb_ai_bets')
from src.advanced_models import ExponentialDecayXGForecaster
import pandas as pd
import datetime

df = pd.read_csv('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv')
df.columns = df.columns.str.strip().str.lower().str.replace('\ufeff', '')
df['date'] = pd.to_datetime(df['date'], errors='coerce')

valid_df = df[df['xg'].notna()]
recent = valid_df.head(1000)

print('Testing ExponentialDecayXGForecaster...')
forecaster = ExponentialDecayXGForecaster(decay_rate=0.1, min_games=2)

mu_count = 0
for _, row in recent.iterrows():
    try:
        home_xg = float(row['xg'])
        away_xg = float(row['xga'])
        forecaster.add_match(row['home_team'], home_xg, True, str(row['date']))
        forecaster.add_match(row['away_team'], away_xg, False, str(row['date']))
        if row['home_team'] == 'Manchester United' or row['away_team'] == 'Manchester United':
            mu_count += 1
    except:
        pass

print(f'MU matches processed: {mu_count}')
result = forecaster.get_team_xg('Manchester United', datetime.datetime.now(), True)
print(f'Result for Man Utd: {result}')

# Check what's in the forecaster
print(f'\nTeams in forecaster: {list(forecaster.team_data.keys())[:10]}...')
