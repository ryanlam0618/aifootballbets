import sys
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

# 讀取合并後的數據
df = pd.read_csv('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/big_five_history.csv', encoding='utf-8-sig', low_memory=False)

# 檢查特定球隊的名稱變化
teams_to_check = ['Augsburg', 'Tottenham', 'Man City', 'Bayern', 'Barcelona', 'PSG', 'Inter']

print('隊名格式檢查:')
print('=' * 60)

for team in teams_to_check:
    home_matches = df[df['HomeTeam'].str.contains(team, case=False, na=False)]['HomeTeam'].unique()
    away_matches = df[df['AwayTeam'].str.contains(team, case=False, na=False)]['AwayTeam'].unique()
    all_matches = list(home_matches) + list(away_matches)
    if len(all_matches) > 0:
        print(f'{team}: {set(all_matches)}')
    else:
        print(f'{team}: 沒有找到')

