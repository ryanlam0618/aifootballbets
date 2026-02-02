import sys
sys.stdout.reconfigure(encoding='utf-8')
from src.injury_api import get_injury_report, get_injury_features

print('='*50)
print('Test Injury Data API (Simulation Mode)')
print('='*50)

report = get_injury_report('Liverpool', 'Arsenal', '2025-02-15')
print('Source:', report['source'])
print('Home Impact:', report['home']['total_impact'])
print('Away Impact:', report['away']['total_impact'])
print('Impact Diff:', report['impact_diff'])
print('Home Key Players:', report['home']['key_players'])

features = get_injury_features('Liverpool', 'Arsenal')
print('\nML Features:')
print('  impact_diff:', features['impact_diff'])
print('  home_impact_score:', features['home_impact_score'])
print('  away_impact_score:', features['away_impact_score'])

print('\nSimulation Mode Working!')
