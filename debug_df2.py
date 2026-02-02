import sys
sys.stdout.reconfigure(encoding='utf-8')

from config import settings
from src.data_modules import HistoryRepo

repo = HistoryRepo(settings.HISTORY_CSV_PATH)

print("Debugging DataFrame structure...")
print(f"repo.df type: {type(repo.df)}")
print(f"repo.df shape: {repo.df.shape}")
print()

# Check for duplicate columns
print("Column info:")
for i, col in enumerate(repo.df.columns):
    col_type = type(repo.df[col])
    print(f"  {i}: '{col}' -> {col_type}")

# Check if 'home_team' appears multiple times
home_team_count = repo.df.columns.tolist().count('home_team')
print(f"\n'home_team' appears {home_team_count} time(s) in columns")

# Check the actual type of df['home_team']
result = repo.df['home_team']
print(f"\nrepo.df['home_team'] type: {type(result)}")
print(f"repo.df['home_team'] shape: {result.shape if hasattr(result, 'shape') else 'N/A'}")
print(f"repo.df['home_team'] columns: {result.columns if hasattr(result, 'columns') else 'N/A'}")

# Try accessing with .iloc
print(f"\nTrying .iloc[:, col_idx] approach:")
col_idx = list(repo.df.columns).index('home_team')
print(f"Column index for 'home_team': {col_idx}")
series_result = repo.df.iloc[:, col_idx]
print(f"repo.df.iloc[:, {col_idx}] type: {type(series_result)}")
