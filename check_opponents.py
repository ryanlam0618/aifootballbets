import pandas as pd
import glob
import os

# Check Manchester Utd opponents from big_five_data
base_path = 'c:/Users/Ryan/Documents/data/big_five_data/match_data/Premier-League/Manchester Utd'

all_mu = []
for f in glob.glob(os.path.join(base_path, '*_matchlog.csv')):
    df = pd.read_csv(f)
    all_mu.append(df)

mu_df = pd.concat(all_mu, ignore_index=True)

# Get unique opponents
print('Manchester Utd opponents from big_five_data:')
for opp in sorted(mu_df['Opponent'].unique()):
    print(f'  - {opp}')

# Check main history_data
main_df = pd.read_csv('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv')
main_df.columns = main_df.columns.str.strip().str.lower().str.replace('\ufeff', '')
mu_main = main_df[(main_df['home_team'] == 'Manchester United') | (main_df['away_team'] == 'Manchester United')]

# Get opponents from main data
main_opponents = set(mu_main['home_team'].unique()) | set(mu_main['away_team'].unique())
main_opponents.discard('Manchester United')

print('\nManchester United opponents from main data:')
for opp in sorted(main_opponents):
    print(f'  - {opp}')

# Check overlapping opponents
big5_opps = set(mu_df['Opponent'].unique())
common = big5_opps & main_opponents
print(f'\nCommon opponents: {len(common)}')
