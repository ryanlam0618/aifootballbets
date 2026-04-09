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

# Fixtures summary universe (broader than paper-trading universe).
# Includes major cups / continental competitions that already have historical coverage
# in the local SofaScore backfill datasets.
FIXTURES_LEAGUE_UNIVERSE = [
    *LEAGUE_UNIVERSE,
    # Continental cups
    "soccer_uefa_champions_league",
    "soccer_uefa_europa_league",
    "soccer_uefa_europa_conference_league",
    "soccer_afc_champions_league",
    # Domestic cups
    "soccer_england_fa_cup",
    "soccer_england_efl_cup",
    "soccer_spain_copa_del_rey",
    "soccer_italy_coppa_italia",
    "soccer_france_coupe_de_france",
    "soccer_germany_dfb_pokal",
    "soccer_japan_j_league_cup",
    "soccer_japan_emperors_cup",
    "soccer_australia_cup",
    "soccer_china_fa_cup",
    # Other international competitions with historical coverage
    "soccer_fifa_club_world_cup",
    "soccer_intercontinental_cup",
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
    "soccer_uefa_champions_league": {
        "tournament_ids": [7],
        "category_aliases": ["europe"],
        "tournament_aliases": ["uefa champions league"],
        "league_name": "UEFA Champions League",
    },
    "soccer_uefa_europa_league": {
        "tournament_ids": [679],
        "category_aliases": ["europe"],
        "tournament_aliases": ["uefa europa league"],
        "league_name": "UEFA Europa League",
    },
    "soccer_uefa_europa_conference_league": {
        "tournament_ids": [17015],
        "category_aliases": ["europe"],
        "tournament_aliases": ["uefa conference league", "uefa europa conference league"],
        "league_name": "UEFA Europa Conference League",
    },
    "soccer_afc_champions_league": {
        "tournament_ids": [668],
        "category_aliases": ["asia"],
        "tournament_aliases": ["afc champions league two", "afc champions league"],
        "league_name": "AFC Champions League",
    },
    "soccer_england_fa_cup": {
        "tournament_ids": [19],
        "category_aliases": ["england"],
        "tournament_aliases": ["fa cup"],
        "league_name": "FA Cup",
    },
    "soccer_england_efl_cup": {
        "tournament_ids": [18],
        "category_aliases": ["england"],
        "tournament_aliases": ["efl cup", "league cup", "carabao cup"],
        "league_name": "EFL Cup",
    },
    "soccer_spain_copa_del_rey": {
        "tournament_ids": [9],
        "category_aliases": ["spain"],
        "tournament_aliases": ["copa del rey"],
        "league_name": "Copa del Rey",
    },
    "soccer_italy_coppa_italia": {
        "tournament_ids": [31],
        "category_aliases": ["italy"],
        "tournament_aliases": ["coppa italia"],
        "league_name": "Coppa Italia",
    },
    "soccer_france_coupe_de_france": {
        "tournament_ids": [36],
        "category_aliases": ["france"],
        "tournament_aliases": ["coupe de france"],
        "league_name": "Coupe de France",
    },
    "soccer_germany_dfb_pokal": {
        "tournament_ids": [54],
        "category_aliases": ["germany"],
        "tournament_aliases": ["dfb pokal"],
        "league_name": "DFB Pokal",
    },
    "soccer_japan_j_league_cup": {
        "tournament_ids": [],
        "category_aliases": ["japan"],
        "tournament_aliases": ["j.league cup", "j league cup", "j-league cup", "levain cup"],
        "league_name": "J.League Cup",
    },
    "soccer_japan_emperors_cup": {
        "tournament_ids": [638],
        "category_aliases": ["japan"],
        "tournament_aliases": ["emperor's cup", "emperors cup"],
        "league_name": "Emperor's Cup",
    },
    "soccer_australia_cup": {
        "tournament_ids": [1026],
        "category_aliases": ["australia"],
        "tournament_aliases": ["australia cup", "ffa cup"],
        "league_name": "Australia Cup",
    },
    "soccer_china_fa_cup": {
        "tournament_ids": [646],
        "category_aliases": ["china"],
        "tournament_aliases": ["fa cup", "chinese fa cup", "china fa cup"],
        "league_name": "Chinese FA Cup",
    },
    "soccer_fifa_club_world_cup": {
        "tournament_ids": [357],
        "category_aliases": ["world"],
        "tournament_aliases": ["fifa club world cup"],
        "league_name": "FIFA Club World Cup",
    },
    "soccer_intercontinental_cup": {
        "tournament_ids": [1098],
        "category_aliases": ["world"],
        "tournament_aliases": ["intercontinental cup"],
        "league_name": "Intercontinental Cup",
    },
}
