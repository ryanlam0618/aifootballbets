import sys
sys.path.insert(0, 'c:/Users/Ryan/python/.vscode/fb_ai_bets')

import pandas as pd
from fuzzywuzzy import fuzz

print('=' * 60)
print('DEBUG valid_df teams')
print('=' * 60)

# Load data
df = pd.read_csv('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv')
df.columns = df.columns.str.strip().str.lower().str.replace('\ufeff', '')

# Filter for xG data (same as app.py)
valid_df = df.dropna(subset=['home_team', 'away_team'])
if 'xg' in valid_df.columns:
    valid_df = valid_df[valid_df['xg'].notna()]

print(f'有效數據總數: {len(valid_df)}')

# Get unique teams from valid_df
all_teams = set(list(valid_df['home_team'].unique()) + list(valid_df['away_team'].unique()))
all_teams_list = list(all_teams)

print(f'有效球隊數量: {len(all_teams_list)}')

# Check Manchester teams
print()
print('檢查 valid_df 中的 Manchester 球隊:')
manchester_teams = [t for t in all_teams_list if 'manchester' in t.lower()]
print(f'找到: {manchester_teams}')

# Check if "Manchester United" exists
print()
print(f'"Manchester United" in valid_df teams: {"Manchester United" in all_teams_list}')

# Check the actual case
print()
print('所有包含 "manchester" 的球隊:')
for t in all_teams_list:
    if 'manchester' in t.lower():
        print(f'  "{t}"')

# Test fuzzy matching with valid_df teams
print()
print('Fuzzy matching 測試:')
input_name = "Manchester United"
clean_input = input_name.lower().strip()

for team in all_teams_list:
    if 'manchester' in team.lower():
        score = fuzz.ratio(clean_input, team.lower())
        print(f'  "{input_name}" vs "{team}": ratio={score}')

# Check if team_list is empty or missing Manchester United
print()
print('檢查 team_list 內容:')
print(f'type: {type(all_teams_list)}')
print(f'前 10 個: {all_teams_list[:10]}')
