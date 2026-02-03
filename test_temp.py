import requests

print('=== Testing FotMob Search API ===')

fotmob_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.fotmob.com/"
}

# Search for matches
search_url = "https://www.fotmob.com/api/searchAll"
params = {
    "query": "Arsenal Chelsea",
    "type": "match"
}

response = requests.get(search_url, params=params, headers=fotmob_headers, timeout=10)
print('Status:', response.status_code)
print('Headers:', response.headers)
print('\nResponse text (first 500 chars):')
print(response.text[:500])
