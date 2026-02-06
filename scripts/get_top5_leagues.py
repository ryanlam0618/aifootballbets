#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""獲取五大聯賽球隊列表 - The Odds API"""

import sys
import os
import requests
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings

sys.stdout.reconfigure(encoding='utf-8')

ODDS_API_KEY = getattr(settings, 'ODDS_API_KEY', '')
BASE_URL = "https://api.the-odds-api.com/v4/sports"

LEAGUES = {
    "1": {"name": "Premier League (England)", "key": "soccer_epl"},
    "2": {"name": "La Liga (Spain)", "key": "soccer_spain_la_liga"},
    "3": {"name": "Bundesliga (Germany)", "key": "soccer_germany_bundesliga"},
    "4": {"name": "Serie A (Italy)", "key": "soccer_italy_serie_a"},
    "5": {"name": "Ligue 1 (France)", "key": "soccer_france_ligue_one"},
}


def get_teams(league_key):
    try:
        r = requests.get(f"{BASE_URL}/{league_key}/odds",
            params={'apiKey': ODDS_API_KEY, 'regions': 'eu,uk', 'markets': 'h2h'},
            timeout=10)
        if r.status_code == 200:
            teams = set()
            for m in r.json():
                teams.add(m.get('home_team', ''))
                teams.add(m.get('away_team', ''))
            return sorted(list(teams))
        return []
    except:
        return []


def main():
    print("=" * 70)
    print("五大聯賽球隊列表 (The Odds API)")
    print("=" * 70)

    if not ODDS_API_KEY:
        print("Error: ODDS_API_KEY not set")
        return

    all_data = {}

    for key, league in LEAGUES.items():
        print(f"\n{league['name']}")
        print("-" * 50)
        teams = get_teams(league["key"])
        if teams:
            all_data[league["name"]] = teams
            print(f"  {len(teams)} teams:")
            for i, t in enumerate(teams, 1):
                print(f"    {i:2}. {t}")
        else:
            print("  Failed to get teams")

    path = os.path.join(os.path.dirname(__file__), "..", "data", "archive", "top5_leagues_teams.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {path}")


if __name__ == "__main__":
    main()
