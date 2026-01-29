import sys
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

# 讀取合并後的數據
df = pd.read_csv('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/big_five_history.csv', encoding='utf-8-sig', low_memory=False)

print('=' * 60)
print('數據合并結果驗證')
print('=' * 60)

print(f'\n總記錄數: {len(df)}')
print(f'\n按聯賽分布:')
print(df['Div'].value_counts())

print(f'\n按賽季分布:')
print(df['Season'].value_counts().head(10))

print(f'\n最近10場比賽:')
print(df[['Date', 'Div', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG']].head(10))

print(f'\n範例球隊名稱:')
print(df['HomeTeam'].unique()[:20])

