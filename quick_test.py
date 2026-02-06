#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick test for team name matching"""

from src.team_name_matcher import match_teams, get_team_info
from src.data_modules import get_api_football_id

print('測試球隊名稱匹配...')
print()

# Cerezo Osaka vs Gamba Osaka
result = match_teams('Cerezo Osaka', 'Gamba Osaka')

print('Cerezo Osaka vs Gamba Osaka')
print()
print('主隊 (Cerezo Osaka):')
print('   Odds API:', result['home']['odds_name'])
print('   API-Football ID:', result['home']['api_football_id'])
print('   API-Football Name:', result['home']['api_name'])
print()
print('客隊 (Gamba Osaka):')
print('   Odds API:', result['away']['odds_name'])
print('   API-Football ID:', result['away']['api_football_id'])
print('   API-Football Name:', result['away']['api_name'])
