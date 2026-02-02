import sys
sys.stdout.reconfigure(encoding='utf-8')

from config import settings
from src.data_modules import HistoryRepo

repo = HistoryRepo(settings.HISTORY_CSV_PATH)

print("Debugging get_match_context...")
print(f"repo.df type: {type(repo.df)}")
print(f"repo.df columns: {list(repo.df.columns)[:10]}")
print()

# Check what home_team column looks like
print(f"repo.df['home_team'] type: {type(repo.df['home_team'])}")
print(f"repo.df[['home_team']] type: {type(repo.df[['home_team']])}")

# Test if there's a naming issue
if 'home_team' in repo.df.columns:
    print("'home_team' column exists")
    print(f"Sample values: {repo.df['home_team'].head(3).tolist()}")
elif 'HomeTeam' in repo.df.columns:
    print("'HomeTeam' column exists (not 'home_team')")
    print(f"Sample values: {repo.df['HomeTeam'].head(3).tolist()}")
else:
    print("Neither 'home_team' nor 'HomeTeam' found!")
    print(f"Available columns: {list(repo.df.columns)[:20]}")
