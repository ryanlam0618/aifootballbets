import sys
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd

DATA_DIR = r'c:\Users\Ryan\python\.vscode\fb_ai_bets\data'
df = pd.read_csv(f'{DATA_DIR}/big_five_history.csv', encoding='utf-8-sig', low_memory=False)

print('=' * 60)
print('Database Statistics Summary')
print('=' * 60)

print(f'\nTotal Matches: {len(df):,}')

print('\nLeagues:')
for league, count in df['Div'].value_counts().items():
    print(f'   {league}: {count:,}')

print('\nAvailable Columns:')
print(df.columns.tolist())

print('\nNew Fields Sample (MatchPlayerData):')
new_cols = ['HT_HG', 'HT_AG', 'HomeCorners', 'AwayCorners', 'HomeShots', 'AwayShots', 'HomeShotsOn', 'AwayShotsOn']
sample = df[df['SourceType'] == 'matchplayer'][new_cols].head(3)
print(sample.to_string())

print('\nDone!')