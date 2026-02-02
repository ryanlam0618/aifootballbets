import sys
sys.stdout.reconfigure(encoding='utf-8')

print('='*60)
print('Test API-Football Injury Data')
print('='*60)

from src.injury_api import APIFootballIntegration

api = APIFootballIntegration()

# Test teams
teams = [
    'Liverpool',
    'Arsenal',
    'Manchester City',
    'Chelsea',
]

print('\nTesting API Connection...\n')

for team in teams:
    print(f'{team}:')
    result = api.get_team_injuries(team)
    
    if 'error' in result:
        print(f'  Error: {result["error"]}')
    else:
        print(f'  Team ID: {result.get("team_id", "N/A")}')
        print(f'  Injuries: {result.get("total", 0)}')
        if result.get('data'):
            for injury in result['data'][:5]:
                print(f'    - {injury["player"]}: {injury["description"]} ({injury["status"]})')
        else:
            print('  No current injuries')
    print()

print('='*60)
