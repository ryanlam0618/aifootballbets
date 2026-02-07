import sys
sys.path.insert(0, 'c:/Users/Ryan/python/.vscode/fb_ai_bets')

import pandas as pd
from fuzzywuzzy import fuzz

print('=' * 60)
print('完整測試 Fuzzy Matching (使用完整 repo.df)')
print('=' * 60)

# Load data
df = pd.read_csv('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv')
df.columns = df.columns.str.strip().str.lower().str.replace('\ufeff', '')

# FULL team list (from repo.df)
all_teams = set(list(df['home_team'].unique()) + list(df['away_team'].unique()))
all_teams_list = list(all_teams)

print(f'完整數據庫球隊數量: {len(all_teams)}')

# ALIAS_MAP
ALIAS_MAP = {
    "manchester united": "Manchester United",
    "manchester utd": "Manchester United",
    "man utd": "Manchester United",
    "manchester city": "Manchester City",
    "man city": "Manchester City",
    "spurs": "Tottenham Hotspur",
    "tottenham": "Tottenham Hotspur",
    # ... 其他別名
}

def fuzzy_match_team(input_name, team_list, threshold=60):
    """使用模糊匹配找最佳球隊名稱"""
    clean_input = input_name.lower().strip()
    
    # 先檢查別名映射 (精確匹配)
    if clean_input in ALIAS_MAP:
        matched = ALIAS_MAP[clean_input]
        if matched in team_list:
            return matched
    
    # 檢查原始名稱是否已存在於 team_list
    if input_name in team_list:
        return input_name
    
    # 檢查小寫版本
    if clean_input in [t.lower() for t in team_list]:
        for team in team_list:
            if team.lower() == clean_input:
                return team
    
    best_match = None
    best_score = 0
    
    for team in team_list:
        clean_team = team.lower().strip()
        scores = [
            fuzz.ratio(clean_input, clean_team),
            fuzz.partial_ratio(clean_input, clean_team),
            fuzz.token_sort_ratio(clean_input, clean_team),
            fuzz.token_set_ratio(clean_input, clean_team),
        ]
        team_score = max(scores)
        if team_score > best_score:
            best_score = team_score
            best_match = team
    
    if best_score >= threshold:
        return best_match
    return input_name

# Test cases
test_cases = [
    ("Manchester United", "Manchester United"),
    ("Manchester City", "Manchester City"),
    ("Tottenham Hotspur", "Tottenham Hotspur"),
    ("tottenham", "Tottenham Hotspur"),
    ("Man Utd", "Manchester United"),
    ("Man City", "Manchester City"),
    ("Chelsea", "Chelsea"),
    ("Liverpool", "Liverpool"),
    ("Arsenal", "Arsenal"),
    ("Newcastle", "Newcastle United"),
]

print()
print('測試結果:')
print('-' * 60)
correct = 0
total = len(test_cases)

for input_name, expected in test_cases:
    result = fuzzy_match_team(input_name, all_teams_list)
    status = '[OK]' if result == expected else '[FAIL]'
    if result == expected:
        correct += 1
    print(f'{status} "{input_name}" -> "{result}"')

print()
print(f'結果: {correct}/{total} 正確')
print('=' * 60)

# Now test the actual scenario
print()
print('實際場景測試:')
print('-' * 60)
print(f'api_home: "Manchester United"')
print(f'api_away: "Tottenham Hotspur"')

target_home = fuzzy_match_team("Manchester United", all_teams_list)
target_away = fuzzy_match_team("Tottenham Hotspur", all_teams_list)

print(f'[FUZZY] "Manchester United" -> "{target_home}"')
print(f'[FUZZY] "Tottenham Hotspur" -> "{target_away}"')

# Check if teams have data in valid_df
valid_df = df.dropna(subset=['home_team', 'away_team'])
if 'xg' in valid_df.columns:
    valid_df = valid_df[valid_df['xg'].notna()]

print()
print('檢查 xG 數據:')
print(f'Manchester United 主場: {len(valid_df[valid_df["home_team"] == "Manchester United"])} 場')
print(f'Manchester United 客場: {len(valid_df[valid_df["away_team"] == "Manchester United"])} 場')
print(f'Tottenham Hotspur 主場: {len(valid_df[valid_df["home_team"] == "Tottenham Hotspur"])} 場')
print(f'Tottenham Hotspur 客場: {len(valid_df[valid_df["away_team"] == "Tottenham Hotspur"])} 場')
