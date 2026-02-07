import pandas as pd

# Load the data
df = pd.read_csv('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv')
df.columns = df.columns.str.strip().str.lower().str.replace('\ufeff', '')

print('='*60)
print('Manchester United xG Data Analysis')
print('='*60)

# Manchester United matches
mu_all = df[(df['home_team'] == 'Manchester United') | (df['away_team'] == 'Manchester United')]
print('\nTotal Manchester United matches:', len(mu_all))
print('Matches with xG data:', mu_all['xg'].notna().sum())

# Check which leagues have xG data
print('\n--- Leagues with xG data ---')
df_with_xg = df[df['xg'].notna()]
leagues_with_xg = df_with_xg.groupby('league').size()
print(leagues_with_xg)

# Premier League teams with xG data
print('\n--- Premier League teams WITH xG data ---')
epl_with_xg = df_with_xg[df_with_xg['league'] == 'Premier League']['home_team'].unique()
print('Count:', len(epl_with_xg))
for team in epl_with_xg:
    print(' -', team)

# Premier League teams WITHOUT xG data (big 6)
print('\n--- Premier League BIG TEAMS without xG data ---')
big_teams = ['Manchester United', 'Manchester City', 'Liverpool', 'Chelsea', 'Arsenal', 'Tottenham Hotspur', 'Newcastle United']
for team in big_teams:
    team_matches = df[(df['home_team'] == team) | (df['away_team'] == team)]
    has_xg = team_matches['xg'].notna().sum()
    print(team + ':', has_xg, 'matches with xG')
