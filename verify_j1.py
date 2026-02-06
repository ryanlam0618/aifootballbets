#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify J1 League mapping"""

from src.team_name_matcher import get_team_info, TEAM_MAPPING_DB

# Test Machida Zelvia
info = get_team_info('Machida Zelvia')
print('Machida Zelvia:')
print('   odds_name:', info['odds_name'])
print('   api_football_id:', info['api_football_id'])
print('   api_name:', info['api_name'])
print('   matched:', info['matched'])

# Verify all 20 J1 teams are in the mapping
print()
print('=' * 60)
print('驗證 J1 League 20 隊映射:')
print('=' * 60)

j1_ids = [279, 280, 281, 282, 284, 287, 288, 289, 290, 291, 292, 293, 294, 295, 296, 302, 303, 306, 311, 316]

mapped_ids = []
for name, info in TEAM_MAPPING_DB.items():
    if info['api_football_id'] in j1_ids and info['api_football_id'] not in mapped_ids:
        mapped_ids.append(info['api_football_id'])
        print(f"  ID={info['api_football_id']:3} {info['odds_name']}")

print('=' * 60)
print(f"Mapped: {len(mapped_ids)} teams")
print(f"Expected: 20 teams")
if len(mapped_ids) == 20:
    print("SUCCESS! All 20 teams are mapped!")
else:
    print("MISSING teams!")
