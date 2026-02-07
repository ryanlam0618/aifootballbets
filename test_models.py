import sys
sys.path.insert(0, 'c:/Users/Ryan/python/.vscode/fb_ai_bets')

import pandas as pd
from src.advanced_models import BayesianGoalModel, TeamFormLSTM, ExponentialDecayXGForecaster

print('=' * 60)
print('測試模型數據載入 - min_games=2')
print('=' * 60)

# Load data
df = pd.read_csv('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv')
df.columns = df.columns.str.strip().str.lower().str.replace('\ufeff', '')

# 球隊名稱正規化
def normalize_team_name(name):
    name = str(name).lower().strip()
    for suffix in [' fc', ' cf', ' sc', ' united', ' hotspur', ' rovers', ' city']:
        name = name.replace(suffix, '')
    return name.strip()

# 建立映射
team_name_map = {}
for team in list(df['home_team'].unique()) + list(df['away_team'].unique()):
    norm_name = normalize_team_name(team)
    if norm_name not in team_name_map:
        team_name_map[norm_name] = team

def find_best_match(input_name):
    input_norm = normalize_team_name(input_name)
    if input_norm in team_name_map:
        return team_name_map[input_norm]
    for norm, orig in team_name_map.items():
        if input_norm in norm or norm in input_norm:
            return orig
    return input_name

# Filter data
valid_df = df.dropna(subset=['home_team', 'away_team'])
if 'xg' in valid_df.columns:
    valid_df = valid_df[valid_df['xg'].notna()]

print(f'有效 xG 數據: {len(valid_df)} 行')

# Test Exponential Decay xG with min_games=2
print()
print('--- 指數衰減 xG (min_games=2) ---')
xg_forecaster = ExponentialDecayXGForecaster(decay_rate=0.1, recency_weight=1.5, min_games=2)

match_count = 0
for _, row in valid_df.tail(200).iterrows():
    try:
        home_xg_val = float(row.get('xg', 1.5))
        away_xg_val = float(row.get('xga', 1.0))
        
        if pd.isna(home_xg_val) or home_xg_val <= 0:
            home_xg_val = float(row['home_goals']) if pd.notna(row.get('home_goals')) else 1.5
        if pd.isna(away_xg_val) or away_xg_val <= 0:
            away_xg_val = float(row['away_goals']) if pd.notna(row.get('away_goals')) else 1.0
        
        xg_forecaster.add_match(row['home_team'], home_xg_val, True, str(row.get('date', '')))
        xg_forecaster.add_match(row['away_team'], away_xg_val, False, str(row.get('date', '')))
        match_count += 1
    except:
        continue

print(f'已載入: {match_count} 場比賽')

import datetime
ref_date = datetime.datetime.now()

home_match = find_best_match("Bournemouth")
away_match = find_best_match("Tottenham")

print(f'查詢: {home_match} (主場), {away_match} (客場)')

home_result = xg_forecaster.get_team_xg(home_match, ref_date, True)
away_result = xg_forecaster.get_team_xg(away_match, ref_date, False)

print(f'Bournemouth xG: {home_result}')
print(f'Tottenham xG: {away_result}')

# Also try Tottenham as home
totten_home_result = xg_forecaster.get_team_xg(away_match, ref_date, True)
print(f'Tottenham (主場) xG: {totten_home_result}')
