import sys
sys.path.insert(0, 'c:/Users/Ryan/python/.vscode/fb_ai_bets')
from src.data_modules import HistoryRepo
import pandas as pd

repo = HistoryRepo('data/history_data.csv')
print('repo.df shape:', repo.df.shape)
print('repo.df columns:', repo.df.columns.tolist())

# Check date column
if 'date' in repo.df.columns:
    print('Date column type:', repo.df['date'].dtype)
    print('Date sample:', repo.df['date'].head())
    
# Check xG column
if 'xg' in repo.df.columns:
    print('xG column type:', repo.df['xg'].dtype)
    print('xG notna count:', repo.df['xg'].notna().sum())

# Create valid_df
valid_df = repo.df.dropna(subset=['home_team', 'away_team'])
if 'xg' in valid_df.columns:
    valid_df = valid_df[valid_df['xg'].notna()]
    
print('\nvalid_df shape:', valid_df.shape)
print('valid_df head(1000) date range:')
print('  Min:', valid_df.head(1000)['date'].min())
print('  Max:', valid_df.head(1000)['date'].max())

print('\nvalid_df tail(1000) date range:')
print('  Min:', valid_df.tail(1000)['date'].min())
print('  Max:', valid_df.tail(1000)['date'].max())

# Check MU
mu_in_head = valid_df.head(1000)[(valid_df.head(1000)['home_team'] == 'Manchester United') | (valid_df.head(1000)['away_team'] == 'Manchester United')]
print('\nMU in head(1000):', len(mu_in_head))
