import json
import re

with open('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/top5_leagues_teams.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

def clean_team_name(name):
    clean = name.lower()
    clean = re.sub(r'[^\w\s]', '', clean)
    clean = ' '.join(clean.split())
    clean = clean.replace(' ', '').replace('-', '')
    return clean

output_lines = [
    '# ============================================',
    '# 五大聯賽球隊 (從 API 獲取)',
    '# ============================================',
    '',
    'TEAM_MAPPING_DB = {'
]

for league_name, teams in data.items():
    output_lines.append('')
    output_lines.append(f'    # {league_name}')
    output_lines.append('')
    
    for t in sorted(teams, key=lambda x: x.get('team', {}).get('name', '')):
        team_info = t.get('team', {})
        team_name = team_info.get('name', '')
        team_id = team_info.get('id', 0)
        key = clean_team_name(team_name)
        
        output_lines.append(f'    "{key}": {{"odds_name": "{team_name}", "api_football_id": {team_id}, "api_name": "{team_name.lower()}"}},')

output_lines.append('}')

# Save to file
with open('c:/Users/Ryan/python/.vscode/fb_ai_bets/data/top5_leagues_teams.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output_lines))

print('Saved to data/top5_leagues_teams.txt')

total = sum(len(teams) for teams in data.values())
print(f'Total teams: {total}')
