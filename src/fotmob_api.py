"""
Fotmob API - Get lineup by match ID
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json

class FotmobAPI:
    def __init__(self, match_id=None):
        self.match_id = match_id
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.fotmob.com/"
        }
    
    def get_lineup_by_match_id(self, match_id=None):
        """
        Get lineup data by Fotmob match ID
        """
        # Use provided match_id or fall back to stored match_id
        if match_id is None:
            match_id = self.match_id
        if match_id is None:
            print("   [FOTMOB] No match ID provided")
            return None
        url = f"https://www.fotmob.com/api/matchDetails?matchId={match_id}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            # Parse lineup data
            lineup = self._parse_lineup(data)
            return lineup
            
        except Exception as e:
            print(f"   [FOTMOB] Error: {str(e)}")
            return None
    
    def _parse_lineup(self, data):
        """Parse Fotmob API response to lineup format"""
        try:
            # Check if there's an error
            if 'error' in data:
                print(f"   [FOTMOB] API Error: {data.get('message', 'Unknown error')}")
                return None
            
            # Try to get match info
            match_info = data.get('matchInfo', {})
            
            # Get home team
            home_team_data = match_info.get('homeTeam', {})
            away_team_data = match_info.get('awayTeam', {})
            
            home_team = home_team_data.get('name', 'Unknown')
            away_team = away_team_data.get('name', 'Unknown')
            
            # Try to get lineups
            lineups = data.get('lineup', {})
            
            # Home team starters
            home_starters = lineups.get('home', {}).get('starters', [])
            away_starters = lineups.get('away', {}).get('starters', [])
            
            # Parse players
            def parse_players(players):
                result = []
                for p in players:
                    result.append({
                        'name': p.get('name', 'Unknown'),
                        'position': p.get('role', 'Unknown'),
                        'rating': p.get('rating', None)
                    })
                return result
            
            return {
                'home_team': {
                    'name': home_team,
                    'starters': parse_players(home_starters),
                    'bench': parse_players(lineups.get('home', {}).get('bench', [])),
                    'formation': lineups.get('home', {}).get('formation', None)
                },
                'away_team': {
                    'name': away_team,
                    'starters': parse_players(away_starters),
                    'bench': parse_players(lineups.get('away', {}).get('bench', [])),
                    'formation': lineups.get('away', {}).get('formation', None)
                },
                'match_id': self.match_id
            }
            
        except Exception as e:
            print(f"   [FOTMOB] Parse error: {str(e)}")
            return None


def get_lineup_by_match_id(match_id):
    """
    Get lineup by Fotmob match ID
    """
    api = FotmobAPI()
    return api.get_lineup_by_match_id(match_id)


if __name__ == "__main__":
    # Test with a match ID
    if len(sys.argv) > 1:
        match_id = sys.argv[1]
        lineup = get_lineup_by_match_id(match_id)
        if lineup:
            print(json.dumps(lineup, indent=2, ensure_ascii=False))
        else:
            print("No lineup found")
    else:
        print("Usage: python fotmob_api.py <match_id>")
