# -*- coding: utf-8 -*-
"""Verify history_data.csv"""
import pandas as pd
df = pd.read_csv(r'C:\Users\Ryan\python\.vscode\fb_ai_bets\data\history_data.csv')

with open(r'C:\Users\Ryan\python\.vscode\fb_ai_bets\scripts\verify.txt', 'w', encoding='utf-8') as f:
    f.write('Columns: ' + str(df.columns.tolist()) + '\n\n')
    f.write('Sample with goals:\n')
    sample = df[df['home_goals'] > 0].head(5)
    f.write(sample.to_string())
    f.write('\n\nGoals stats:\n')
    f.write('Total home goals: ' + str(df['home_goals'].sum()) + '\n')
    f.write('Total away goals: ' + str(df['away_goals'].sum()) + '\n')
    f.write('Matches with goals: ' + str(len(df[(df['home_goals'] > 0) | (df['away_goals'] > 0)])) + '\n')
