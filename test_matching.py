import sys
sys.path.insert(0, 'c:/Users/Ryan/python/.vscode/fb_ai_bets')

from src.team_name_matcher import match_teams

print('=' * 60)
print('Testing Team Matching with Correct API IDs')
print('=' * 60)

test_cases = [
    ('Manchester City', 'Liverpool'),
    ('Real Madrid', 'Barcelona'),
    ('Bayern Munich', 'Dortmund'),
    ('Inter Milan', 'Juventus'),
    ('Paris Saint Germain', 'Marseille'),
    ('Hellas Verona', 'Pisa'),
]

for home, away in test_cases:
    print(f'\n{home} vs {away}')
    result = match_teams(home, away)
    
    print(f'   Home: {result["home"]["odds_name"]} (ID: {result["home"]["api_football_id"]}) - {result["home"]["matched"]}')
    print(f'   Away: {result["away"]["odds_name"]} (ID: {result["away"]["api_football_id"]}) - {result["away"]["matched"]}')
