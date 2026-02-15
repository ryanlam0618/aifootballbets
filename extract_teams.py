"""
Extract all team names from historical data
"""
import pandas as pd
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

# Load historical data
df = pd.read_csv('data/history_data.csv')

# Get all unique teams
teams = set(df['home_team'].unique()) | set(df['away_team'].unique())

print(f"Total teams in historical data: {len(teams)}")
print("\nAll teams (sorted):")
for t in sorted(teams):
    print(f"  - {t}")

# Create JSON file
teams_dict = {t: {"historical_name": t, "aliases": []} for t in sorted(teams)}

with open('data/historical_teams.json', 'w', encoding='utf-8') as f:
    json.dump(teams_dict, f, ensure_ascii=False, indent=2)

print(f"\nSaved to data/historical_teams.json")
