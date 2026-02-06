#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Show all 20 J1 League teams"""

# J1 League API-Football ID: 98
api_football_teams = [
    {'id': 279, 'name': 'Consadole Sapporo'},
    {'id': 280, 'name': 'Jubilo Iwata'},
    {'id': 281, 'name': 'Kashiwa Reysol'},
    {'id': 282, 'name': 'Sanfrecce Hiroshima'},
    {'id': 284, 'name': 'Shonan Bellmare'},
    {'id': 287, 'name': 'Urawa'},
    {'id': 288, 'name': 'Nagoya Grampus'},
    {'id': 289, 'name': 'Vissel Kobe'},
    {'id': 290, 'name': 'Kashima'},
    {'id': 291, 'name': 'Cerezo Osaka'},
    {'id': 292, 'name': 'FC Tokyo'},
    {'id': 293, 'name': 'Gamba Osaka'},
    {'id': 294, 'name': 'Kawasaki Frontale'},
    {'id': 295, 'name': 'Sagan Tosu'},
    {'id': 296, 'name': 'Yokohama F. Marinos'},
    {'id': 302, 'name': 'Kyoto Sanga'},
    {'id': 303, 'name': 'Machida Zelvia'},
    {'id': 306, 'name': 'Tokyo Verdy'},
    {'id': 311, 'name': 'Albirex Niigata'},
    {'id': 316, 'name': 'Avispa Fukuoka'},
]

print('J1 League 完整 20 隊 (API-Football):')
print('=' * 50)
for i, team in enumerate(api_football_teams, 1):
    print(f"{i:2}. ID={team['id']:4} {team['name']}")
print('=' * 50)
print(f"Total: {len(api_football_teams)} teams")

# Missing from current TEAM_MAPPING_DB
missing = [
    ('machida zelvia', 303, 'Machida Zelvia'),
]
print("\n缺失的球隊 (需要添加到 TEAM_MAPPING_DB):")
for name, id, full_name in missing:
    print(f"  '{name}': odds_name='{full_name}', api_football_id={id}, api_name='{name}'")
