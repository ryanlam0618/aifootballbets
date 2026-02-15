"""
Debug Fotmob API response
"""
import requests
import json

match_id = "48032"
url = f"https://www.fotmob.com/api/matchDetails?matchId={match_id}"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.fotmob.com/"
}

response = requests.get(url, headers=headers, timeout=30)
print(f"Status: {response.status_code}")

data = response.json()

# Print top-level keys
print(f"\nTop-level keys: {list(data.keys())}")

# Check for lineup
if 'lineup' in data:
    print(f"\nLineup keys: {list(data['lineup'].keys())}")
    for team in ['home', 'away']:
        if team in data['lineup']:
            print(f"\n{team}: {list(data['lineup'][team].keys())}")

# Check for matchInfo
if 'matchInfo' in data:
    print(f"\nMatchInfo keys: {list(data['matchInfo'].keys())}")
    if 'homeTeam' in data['matchInfo']:
        print(f"Home team: {data['matchInfo']['homeTeam']}")
