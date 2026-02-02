import sys
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import os

DATA_DIR = r'c:\Users\Ryan\python\.vscode\fb_ai_bets\data'
BIG_FIVE_HISTORY_PATH = os.path.join(DATA_DIR, 'big_five_history.csv')

df = pd.read_csv(BIG_FIVE_HISTORY_PATH, encoding='utf-8-sig', low_memory=False)

# 標準化聯賽名稱
div_mapping = {
    'PremierLeague': 'Premier League',
    'LaLiga': 'La Liga',
    'SerieA': 'Serie A',
    'Ligue1': 'Ligue 1',
}

df['Div'] = df['Div'].replace(div_mapping)

# 重新保存
df.to_csv(BIG_FIVE_HISTORY_PATH, index=False, encoding='utf-8-sig')

print('✅ 聯賽名稱已標準化')
print()
print('📊 各聯賽統計:')
print(df['Div'].value_counts().to_string())
print()
print(f'總記錄數: {len(df)}')
