"""
The Odds API Team Fetcher
Fetches current season team names and IDs for top 5 European leagues
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json
import time
from config import settings

# The Odds API endpoints for top 5 leagues
LEAGUE_KEYS = {
    'soccer_epl': 'Premier League (England)',
    'soccer_germany_bundesliga': 'Bundesliga (Germany)',
    'soccer_france_ligue_one': 'Ligue 1 (France)',
    'soccer_italy_serie_a': 'Serie A (Italy)',
    'soccer_spain_la_liga': 'La Liga (Spain)'
}

def fetch_odds_api_teams(league_key):
    """Fetch all teams from The Odds API for a given league"""
    url = f"https://api.the-odds-api.com/v4/sports/{league_key}/events"
    params = {
        'apiKey': settings.ODDS_API_KEY,
        'dateFormat': 'iso'
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            events = response.json()
            teams = {}
            for event in events:
                # Home team
                home_team = event.get('home_team', '')
                away_team = event.get('away_team', '')
                
                if home_team and home_team not in teams:
                    teams[home_team] = {
                        'name': home_team,
                        'odds_api_key': league_key,
                        'event_id': event.get('id'),
                        'commence_time': event.get('commence_time')
                    }
                
                if away_team and away_team not in teams:
                    teams[away_team] = {
                        'name': away_team,
                        'odds_api_key': league_key,
                        'event_id': event.get('id'),
                        'commence_time': event.get('commence_time')
                    }
            return teams
        else:
            print(f"   [ERROR] {league_key}: HTTP {response.status_code}")
            return {}
    except Exception as e:
        print(f"   [ERROR] {league_key}: {str(e)}")
        return {}

def fetch_all_leagues_teams():
    """Fetch teams from all top 5 leagues"""
    all_teams = {}
    
    for key, name in LEAGUE_KEYS.items():
        print(f"   [LEAGUE] Fetching teams from {name}...")
        teams = fetch_odds_api_teams(key)
        all_teams[key] = {
            'league_name': name,
            'teams': teams
        }
        print(f"      Found {len(teams)} teams")
        time.sleep(1)  # Rate limiting
    
    return all_teams

def save_teams_to_file(all_teams, filename='data/top5_leagues_teams.json'):
    """Save teams data to JSON file"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(all_teams, f, ensure_ascii=False, indent=2)
    print(f"\n   [OK] Saved {len(all_teams)} leagues to {filename}")

def load_teams_from_file(filename='data/top5_leagues_teams.json'):
    """Load teams data from JSON file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def search_team(all_teams, league_key, team_name):
    """Search for a team by name in a specific league"""
    if league_key not in all_teams:
        return None
    
    teams = all_teams[league_key].get('teams', {})
    
    # Exact match
    if team_name in teams:
        return teams[team_name]
    
    # Partial match
    for name, info in teams.items():
        if team_name.lower() in name.lower() or name.lower() in team_name.lower():
            return info
    
    return None

if __name__ == "__main__":
    # Fix unicode encoding for Windows
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
    
    print("=" * 60)
    print("The Odds API - Top 5 Leagues Team Fetcher")
    print("=" * 60)
    
    # Check for --force flag
    force_fetch = '--force' in sys.argv
    
    # Try to load existing data first
    existing = load_teams_from_file()
    
    # Check if it's The Odds API format
    is_odds_format = False
    if existing:
        # The Odds API format has league keys like 'soccer_epl'
        if any(key.startswith('soccer_') for key in existing.keys()):
            is_odds_format = True
    
    if existing and is_odds_format and not force_fetch:
        print(f"\n   [FOLDER] Found existing The Odds API data: {len(existing)} leagues")
    else:
        if existing and not is_odds_format:
            print(f"\n   [WARNING] Found old format data, re-fetching...")
        print("\n   [WEB] Fetching fresh data from The Odds API...")
        all_teams = fetch_all_leagues_teams()
        save_teams_to_file(all_teams)
    
    print("\n   [OK] Complete!")
