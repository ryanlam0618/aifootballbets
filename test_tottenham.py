import sys
sys.path.insert(0, 'c:/Users/Ryan/python/.vscode/fb_ai_bets')

import pandas as pd
from src.advanced_models import ExponentialDecayXGForecaster

# Load data
df = pd.read_csv('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv')
df.columns = df.columns.str.strip().str.lower().str.replace('\ufeff', '')

print('--- 檢查 Tottenham 在最近 200 場的數據 ---')

# Filter valid data
valid_df = df.dropna(subset=['home_team', 'away_team'])
if 'xg' in valid_df.columns:
    valid_df = valid_df[valid_df['xg'].notna()]

print(f'有效數據總數: {len(valid_df)}')

# Check last 200 rows
last_200 = valid_df.tail(200)
print(f'最近 200 場: {len(last_200)}')

# Check Tottenham in last 200
totten_home = last_200[last_200['home_team'].str.contains('tottenham', case=False, na=False)]
totten_away = last_200[last_200['away_team'].str.contains('tottenham', case=False, na=False)]

print(f'Tottenham 主場在最近 200 場: {len(totten_home)}')
print(f'Tottenham 客場在最近 200 場: {len(totten_away)}')

if len(totten_home) > 0:
    print('主場樣本:')
    print(totten_home[['home_team', 'away_team', 'xg', 'xga', 'date']].head())

if len(totten_away) > 0:
    print('客場樣本:')
    print(totten_away[['home_team', 'away_team', 'xg', 'xga', 'date']].head())

# Check ALL data for Tottenham
print()
print('--- Tottenham 在所有數據中的位置 ---')
all_totten_home = valid_df[valid_df['home_team'].str.contains('tottenham', case=False, na=False)]
all_totten_away = valid_df[valid_df['away_team'].str.contains('tottenham', case=False, na=False)]
print(f'Tottenham 總主場數: {len(all_totten_home)}')
print(f'Tottenham 總客場數: {len(all_totten_away)}')

# Check index positions
if len(all_totten_home) > 0:
    print(f'Tottenham 主場索引: {all_totten_home.index.tolist()[-5:]}')
if len(all_totten_away) > 0:
    print(f'Tottenham 客場索引: {all_totten_away.index.tolist()[-5:]}')

# Check data indices
print(f'數據索引範圍: {valid_df.index.min()} - {valid_df.index.max()}')
print(f'最近 200 場索引範圍: {last_200.index.min()} - {last_200.index.max()}')

# The issue: let's check if we should be using tail or head
print()
print('--- 使用 head(200) 測試 ---')
first_200 = valid_df.head(200)
print(f'前 200 場索引範圍: {first_200.index.min()} - {first_200.index.max()}')

totten_home_head = first_200[first_200['home_team'].str.contains('tottenham', case=False, na=False)]
totten_away_head = first_200[first_200['away_team'].str.contains('tottenham', case=False, na=False)]
print(f'Tottenham 主場在前 200: {len(totten_home_head)}')
print(f'Tottenham 客場在前 200: {len(totten_away_head)}')
