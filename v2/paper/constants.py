from __future__ import annotations

# Combined league universe (single strategy pool, not split by league)
LEAGUE_UNIVERSE = [
    # Big-5
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    # APAC
    "soccer_japan_j_league",
    "soccer_south_korea_kleague1",
    "soccer_australia_aleague",
    "soccer_china_superleague",
]

# SofaScore league matching config for scheduled-events data.
# Matching order in provider:
# 1) tournament uniqueTournament.id (if listed)
# 2) normalized tournament.name aliases within category aliases
SOFASCORE_LEAGUE_MAP = {
    "soccer_epl": {
        "tournament_ids": [17],
        "category_aliases": ["england"],
        "tournament_aliases": ["premier league"],
        "league_name": "Premier League",
    },
    "soccer_spain_la_liga": {
        "tournament_ids": [8],
        "category_aliases": ["spain"],
        "tournament_aliases": ["laliga", "la liga"],
        "league_name": "LaLiga",
    },
    "soccer_italy_serie_a": {
        "tournament_ids": [23],
        "category_aliases": ["italy"],
        "tournament_aliases": ["serie a"],
        "league_name": "Serie A",
    },
    "soccer_germany_bundesliga": {
        "tournament_ids": [35],
        "category_aliases": ["germany"],
        "tournament_aliases": ["bundesliga"],
        "league_name": "Bundesliga",
    },
    "soccer_france_ligue_one": {
        "tournament_ids": [34],
        "category_aliases": ["france"],
        "tournament_aliases": ["ligue 1"],
        "league_name": "Ligue 1",
    },
    "soccer_japan_j_league": {
        "tournament_ids": [196],
        "category_aliases": ["japan"],
        "tournament_aliases": ["j1 league", "j league"],
        "league_name": "J1 League",
    },
    "soccer_south_korea_kleague1": {
        "tournament_ids": [292],
        "category_aliases": ["south korea", "republic of korea", "korea republic"],
        "tournament_aliases": ["k-league 1", "kleague 1", "k league 1"],
        "league_name": "K League 1",
    },
    "soccer_australia_aleague": {
        "tournament_ids": [283],
        "category_aliases": ["australia"],
        "tournament_aliases": ["a-league men", "a-league"],
        "league_name": "A-League Men",
    },
    "soccer_china_superleague": {
        "tournament_ids": [649],
        "category_aliases": ["china"],
        "tournament_aliases": ["csl", "super league", "chinese super league"],
        "league_name": "Chinese Super League",
    },
}
