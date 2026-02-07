import pandas as pd

df = pd.read_csv('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv')
df.columns = df.columns.str.strip().str.lower().str.replace('\ufeff', '')

print('xG column exists:', 'xg' in df.columns)

# Check all teams in the database
all_teams = set(df['home_team'].unique()) | set(df['away_team'].unique())
print('Total unique teams:', len(all_teams))

# Check Manchester teams
print()
print('Manchester teams in database:')
for t in all_teams:
    if 'manchester' in t.lower():
        print(f'  "{t}"')

# Check if xG column has data
print()
print('xG data summary:')
print(f'  Rows with xG data: {df["xg"].notna().sum()}')
print(f'  Rows without xG data: {df["xg"].isna().sum()}')

# Check Manchester United xG data
print()
print('Manchester United xG data:')
mu_home = df[(df['home_team'] == 'Manchester United') & (df['xg'].notna())]
mu_away = df[(df['away_team'] == 'Manchester United') & (df['xg'].notna())]
print(f'  Home matches with xG: {len(mu_home)}')
print(f'  Away matches with xG: {len(mu_away)}')

# Check a few rows of Manchester United
print()
print('Sample Manchester United data (with xG):')
sample = df[(df['home_team'] == 'Manchester United') | (df['away_team'] == 'Manchester United')]
if len(sample) > 0:
    print(sample[['home_team', 'away_team', 'xg', 'xga', 'home_goals', 'away_goals']].head(10))
else:
    print('  No data found')
