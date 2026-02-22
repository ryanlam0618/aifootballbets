# -*- coding: utf-8 -*-
"""Quick check shotmap outcomes"""
import pandas as pd
df = pd.read_csv(r'C:\Users\Ryan\python\.vscode\fb_ai_bets\data\sofascore\5_years_data\all_shotmap.csv')

with open(r'C:\Users\Ryan\python\.vscode\fb_ai_bets\scripts\output.txt', 'w', encoding='utf-8') as f:
    f.write('Outcome values: ' + str(df['outcome'].unique()) + '\n')
    goals = df[df['outcome'] == 'goal']
    f.write('Goal count: ' + str(len(goals)) + '\n')
    f.write(goals[['event_id', 'home_team', 'away_team', 'is_home']].head().to_string())
