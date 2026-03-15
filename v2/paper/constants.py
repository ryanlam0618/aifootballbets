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

# ESPN league path mapping for scoreboard endpoint
# https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates=YYYYMMDD
ESPN_LEAGUE_MAP = {
    "soccer_epl": ("soccer", "eng.1"),
    "soccer_spain_la_liga": ("soccer", "esp.1"),
    "soccer_italy_serie_a": ("soccer", "ita.1"),
    "soccer_germany_bundesliga": ("soccer", "ger.1"),
    "soccer_france_ligue_one": ("soccer", "fra.1"),
    "soccer_japan_j_league": ("soccer", "jpn.1"),
    "soccer_south_korea_kleague1": ("soccer", "kor.1"),
    "soccer_australia_aleague": ("soccer", "aus.1"),
    "soccer_china_superleague": ("soccer", "chn.1"),
}
