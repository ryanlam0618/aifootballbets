#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
球隊名稱匹配器 - 整合 The Odds API 和 API-Football
使用 Gemini API 進行智能匹配
"""

import sys
import os
import json
import re
from typing import Dict, Optional, Tuple
from difflib import SequenceMatcher

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings

sys.stdout.reconfigure(encoding='utf-8')


# ============================================
# 本地球隊名稱映射 (從 API 獲取)
# ============================================

# The Odds API 名稱 -> API-Football ID 和 名稱
# 數據來源: API-Football v3 (2024/25 賽季)
TEAM_MAPPING_DB = {
    # ============================================
    # 日本 J1 League (League ID: 98)
    # ============================================
    "avispa fukuoka": {"odds_name": "Avispa Fukuoka", "api_football_id": 316, "api_name": "avispa fukuoka"},
    "cerezo osaka": {"odds_name": "Cerezo Osaka", "api_football_id": 291, "api_name": "cerezo osaka"},
    "fc tokyo": {"odds_name": "FC Tokyo", "api_football_id": 292, "api_name": "fc tokyo"},
    "gamba osaka": {"odds_name": "Gamba Osaka", "api_football_id": 293, "api_name": "gamba osaka"},
    "kashima antlers": {"odds_name": "Kashima Antlers", "api_football_id": 290, "api_name": "kashima"},
    "kashiwa reysol": {"odds_name": "Kashiwa Reysol", "api_football_id": 281, "api_name": "kashiwa reysol"},
    "kawasaki frontale": {"odds_name": "Kawasaki Frontale", "api_football_id": 294, "api_name": "kawasaki frontale"},
    "kyoto sanga": {"odds_name": "Kyoto Sanga", "api_football_id": 302, "api_name": "kyoto sanga"},
    "machida zelvia": {"odds_name": "Machida Zelvia", "api_football_id": 303, "api_name": "machida zelvia"},
    "nagoya grampus": {"odds_name": "Nagoya Grampus", "api_football_id": 288, "api_name": "nagoya grampus"},
    "sagan tosu": {"odds_name": "Sagan Tosu", "api_football_id": 295, "api_name": "sagan tosu"},
    "sanfrecce hiroshima": {"odds_name": "Sanfrecce Hiroshima", "api_football_id": 282, "api_name": "sanfrecce hiroshima"},
    "shimizu s-pulse": {"odds_name": "Shimizu S-Pulse", "api_football_id": 283, "api_name": "shimizu s-pulse"},
    "shonan bellmare": {"odds_name": "Shonan Bellmare", "api_football_id": 284, "api_name": "shonan bellmare"},
    "tokyo verdy": {"odds_name": "Tokyo Verdy", "api_football_id": 306, "api_name": "tokyo verdy"},
    "urawa red diamonds": {"odds_name": "Urawa Red Diamonds", "api_football_id": 287, "api_name": "urawa"},
    "vissel kobe": {"odds_name": "Vissel Kobe", "api_football_id": 289, "api_name": "vissel kobe"},
    "yokohama f. marinhos": {"odds_name": "Yokohama F. Marinos", "api_football_id": 296, "api_name": "yokohama f. marinhos"},
    
    # ============================================
    # 日本 J2 League (League ID: 99)
    # ============================================
    "albirex niigata": {"odds_name": "Albirex Niigata", "api_football_id": 311, "api_name": "albirex niigata"},
    "blaublitz akita": {"odds_name": "Blaublitz Akita", "api_football_id": 4315, "api_name": "blaublitz akita"},
    "ehime fc": {"odds_name": "Ehime FC", "api_football_id": 318, "api_name": "ehime fc"},
    "fagiano okayama": {"odds_name": "Fagiano Okayama", "api_football_id": 310, "api_name": "fagiano okayama"},
    "fujieda myfc": {"odds_name": "Fujieda MYFC", "api_football_id": 4317, "api_name": "fujieda myfc"},
    "jef united chiba": {"odds_name": "JEF United Chiba", "api_football_id": 301, "api_name": "jef united chiba"},
    "jubilo iwata": {"odds_name": "Jubilo Iwata", "api_football_id": 280, "api_name": "jubilo iwata"},
    "mito hollyh": {"odds_name": "Mito HollyHock", "api_football_id": 305, "api_name": "mito hollyhock"},
    "montedio yamagata": {"odds_name": "Montedio Yamagata", "api_football_id": 312, "api_name": "montedio yamagata"},
    "oita trinita": {"odds_name": "Oita Trinita", "api_football_id": 298, "api_name": "oita trinita"},
    "renofa yamaguchi": {"odds_name": "Renofa Yamaguchi", "api_football_id": 309, "api_name": "renofa yamaguchi"},
    "roasso kumamoto": {"odds_name": "Roasso Kumamoto", "api_football_id": 314, "api_name": "roasso kumamoto"},
    "thespakusatsu gunma": {"odds_name": "Thespakusatsu Gunma", "api_football_id": 756, "api_name": "thespakusatsu gunma"},
    "tochigi sc": {"odds_name": "Tochigi SC", "api_football_id": 315, "api_name": "tochigi sc"},
    "tokushima vortis": {"odds_name": "Tokushima Vortis", "api_football_id": 299, "api_name": "tokushima vortis"},
    "v-varen nagasaki": {"odds_name": "V-Varen Nagasaki", "api_football_id": 285, "api_name": "v-varen nagasaki"},
    "vegalta sendai": {"odds_name": "Vegalta Sendai", "api_football_id": 286, "api_name": "vegalta sendai"},
    "ventforet kofu": {"odds_name": "Ventforet Kofu", "api_football_id": 308, "api_name": "ventforet kofu"},
    "yokohama fc": {"odds_name": "Yokohama FC", "api_football_id": 307, "api_name": "yokohama fc"},
    
    # ============================================
    # Premier League (England) - League ID: 39
    # 數據來源: API-Football v3
    # ============================================
    "arsenal": {"odds_name": "Arsenal", "api_football_id": 42, "api_name": "arsenal"},
    "aston villa": {"odds_name": "Aston Villa", "api_football_id": 66, "api_name": "aston villa"},
    "bournemouth": {"odds_name": "Bournemouth", "api_football_id": 35, "api_name": "bournemouth"},
    "brentford": {"odds_name": "Brentford", "api_football_id": 55, "api_name": "brentford"},
    "brighton": {"odds_name": "Brighton", "api_football_id": 51, "api_name": "brighton"},
    "chelsea": {"odds_name": "Chelsea", "api_football_id": 49, "api_name": "chelsea"},
    "crystal palace": {"odds_name": "Crystal Palace", "api_football_id": 52, "api_name": "crystal palace"},
    "everton": {"odds_name": "Everton", "api_football_id": 45, "api_name": "everton"},
    "fulham": {"odds_name": "Fulham", "api_football_id": 36, "api_name": "fulham"},
    "ipswich": {"odds_name": "Ipswich", "api_football_id": 57, "api_name": "ipswich"},
    "leicester": {"odds_name": "Leicester", "api_football_id": 46, "api_name": "leicester"},
    "liverpool": {"odds_name": "Liverpool", "api_football_id": 40, "api_name": "liverpool"},
    "manchester city": {"odds_name": "Manchester City", "api_football_id": 50, "api_name": "manchester city"},
    "manchester united": {"odds_name": "Manchester United", "api_football_id": 33, "api_name": "manchester united"},
    "newcastle": {"odds_name": "Newcastle", "api_football_id": 34, "api_name": "newcastle"},
    "nottingham forest": {"odds_name": "Nottingham Forest", "api_football_id": 65, "api_name": "nottingham forest"},
    "southampton": {"odds_name": "Southampton", "api_football_id": 41, "api_name": "southampton"},
    "tottenham": {"odds_name": "Tottenham", "api_football_id": 47, "api_name": "tottenham"},
    "west ham": {"odds_name": "West Ham", "api_football_id": 48, "api_name": "west ham"},
    "wolves": {"odds_name": "Wolves", "api_football_id": 39, "api_name": "wolves"},
    
    # ============================================
    # La Liga (Spain) - League ID: 140
    # 數據來源: API-Football v3
    # ============================================
    "alaves": {"odds_name": "Alaves", "api_football_id": 542, "api_name": "alaves"},
    "athletic club": {"odds_name": "Athletic Club", "api_football_id": 531, "api_name": "athletic club"},
    "atletico madrid": {"odds_name": "Atletico Madrid", "api_football_id": 530, "api_name": "atletico madrid"},
    "barcelona": {"odds_name": "Barcelona", "api_football_id": 529, "api_name": "barcelona"},
    "celta vigo": {"odds_name": "Celta Vigo", "api_football_id": 538, "api_name": "celta vigo"},
    "espanyol": {"odds_name": "Espanyol", "api_football_id": 540, "api_name": "espanyol"},
    "getafe": {"odds_name": "Getafe", "api_football_id": 546, "api_name": "getafe"},
    "girona": {"odds_name": "Girona", "api_football_id": 547, "api_name": "girona"},
    "las palmas": {"odds_name": "Las Palmas", "api_football_id": 534, "api_name": "las palmas"},
    "leganes": {"odds_name": "Leganes", "api_football_id": 537, "api_name": "leganes"},
    "mallorca": {"odds_name": "Mallorca", "api_football_id": 798, "api_name": "mallorca"},
    "osasuna": {"odds_name": "Osasuna", "api_football_id": 727, "api_name": "osasuna"},
    "rayo vallecano": {"odds_name": "Rayo Vallecano", "api_football_id": 728, "api_name": "rayo vallecano"},
    "real betis": {"odds_name": "Real Betis", "api_football_id": 543, "api_name": "real betis"},
    "real madrid": {"odds_name": "Real Madrid", "api_football_id": 541, "api_name": "real madrid"},
    "real sociedad": {"odds_name": "Real Sociedad", "api_football_id": 548, "api_name": "real sociedad"},
    "sevilla": {"odds_name": "Sevilla", "api_football_id": 536, "api_name": "sevilla"},
    "valencia": {"odds_name": "Valencia", "api_football_id": 532, "api_name": "valencia"},
    "valladolid": {"odds_name": "Valladolid", "api_football_id": 720, "api_name": "valladolid"},
    "villarreal": {"odds_name": "Villarreal", "api_football_id": 533, "api_name": "villarreal"},
    
    # ============================================
    # Bundesliga (Germany) - League ID: 78
    # 數據來源: API-Football v3
    # ============================================
    "1. fc heidenheim": {"odds_name": "1. FC Heidenheim", "api_football_id": 180, "api_name": "1. fc heidenheim"},
    "1899 hoffenheim": {"odds_name": "1899 Hoffenheim", "api_football_id": 167, "api_name": "1899 hoffenheim"},
    "bayer leverkusen": {"odds_name": "Bayer Leverkusen", "api_football_id": 168, "api_name": "bayer leverkusen"},
    "bayern munchen": {"odds_name": "Bayern Munchen", "api_football_id": 157, "api_name": "bayern munchen"},
    "borussia dortmund": {"odds_name": "Borussia Dortmund", "api_football_id": 165, "api_name": "borussia dortmund"},
    "borussia monchengladbach": {"odds_name": "Borussia Monchengladbach", "api_football_id": 163, "api_name": "borussia monchengladbach"},
    "eintracht frankfurt": {"odds_name": "Eintracht Frankfurt", "api_football_id": 169, "api_name": "eintracht frankfurt"},
    "fc augsburg": {"odds_name": "FC Augsburg", "api_football_id": 170, "api_name": "fc augsburg"},
    "fc st. pauli": {"odds_name": "FC St. Pauli", "api_football_id": 186, "api_name": "fc st. pauli"},
    "fsv mainz 05": {"odds_name": "FSV Mainz 05", "api_football_id": 164, "api_name": "fsv mainz 05"},
    "holstein kiel": {"odds_name": "Holstein Kiel", "api_football_id": 191, "api_name": "holstein kiel"},
    "rb leipzig": {"odds_name": "RB Leipzig", "api_football_id": 173, "api_name": "rb leipzig"},
    "sc freiburg": {"odds_name": "SC Freiburg", "api_football_id": 160, "api_name": "sc freiburg"},
    "sv elversberg": {"odds_name": "SV Elversberg", "api_football_id": 1660, "api_name": "sv elversberg"},
    "union berlin": {"odds_name": "Union Berlin", "api_football_id": 182, "api_name": "union berlin"},
    "vfb stuttgart": {"odds_name": "VfB Stuttgart", "api_football_id": 172, "api_name": "vfb stuttgart"},
    "vfl bochum": {"odds_name": "VfL Bochum", "api_football_id": 176, "api_name": "vfl bochum"},
    "vfl wolfsburg": {"odds_name": "VfL Wolfsburg", "api_football_id": 161, "api_name": "vfl wolfsburg"},
    "werder bremen": {"odds_name": "Werder Bremen", "api_football_id": 162, "api_name": "werder bremen"},
    
    # ============================================
    # Serie A (Italy) - League ID: 135
    # 數據來源: API-Football v3
    # ============================================
    "ac milan": {"odds_name": "AC Milan", "api_football_id": 489, "api_name": "ac milan"},
    "as roma": {"odds_name": "AS Roma", "api_football_id": 497, "api_name": "as roma"},
    "atalanta": {"odds_name": "Atalanta", "api_football_id": 499, "api_name": "atalanta"},
    "bologna": {"odds_name": "Bologna", "api_football_id": 500, "api_name": "bologna"},
    "cagliari": {"odds_name": "Cagliari", "api_football_id": 490, "api_name": "cagliari"},
    "como": {"odds_name": "Como", "api_football_id": 895, "api_name": "como"},
    "empoli": {"odds_name": "Empoli", "api_football_id": 511, "api_name": "empoli"},
    "fiorentina": {"odds_name": "Fiorentina", "api_football_id": 502, "api_name": "fiorentina"},
    "genoa": {"odds_name": "Genoa", "api_football_id": 495, "api_name": "genoa"},
    "inter": {"odds_name": "Inter", "api_football_id": 505, "api_name": "inter"},
    "juventus": {"odds_name": "Juventus", "api_football_id": 496, "api_name": "juventus"},
    "lazio": {"odds_name": "Lazio", "api_football_id": 487, "api_name": "lazio"},
    "lecce": {"odds_name": "Lecce", "api_football_id": 867, "api_name": "lecce"},
    "monza": {"odds_name": "Monza", "api_football_id": 1579, "api_name": "monza"},
    "napoli": {"odds_name": "Napoli", "api_football_id": 492, "api_name": "napoli"},
    "parma": {"odds_name": "Parma", "api_football_id": 523, "api_name": "parma"},
    "torino": {"odds_name": "Torino", "api_football_id": 503, "api_name": "torino"},
    "udinese": {"odds_name": "Udinese", "api_football_id": 494, "api_name": "udinese"},
    "venezia": {"odds_name": "Venezia", "api_football_id": 517, "api_name": "venezia"},
    "verona": {"odds_name": "Verona", "api_football_id": 504, "api_name": "verona"},
    
    # ============================================
    # Ligue 1 (France) - League ID: 61
    # 數據來源: API-Football v3
    # ============================================
    "angers": {"odds_name": "Angers", "api_football_id": 77, "api_name": "angers"},
    "auxerre": {"odds_name": "Auxerre", "api_football_id": 108, "api_name": "auxerre"},
    "le havre": {"odds_name": "Le Havre", "api_football_id": 111, "api_name": "le havre"},
    "lens": {"odds_name": "Lens", "api_football_id": 116, "api_name": "lens"},
    "lille": {"odds_name": "Lille", "api_football_id": 79, "api_name": "lille"},
    "lyon": {"odds_name": "Lyon", "api_football_id": 80, "api_name": "lyon"},
    "marseille": {"odds_name": "Marseille", "api_football_id": 81, "api_name": "marseille"},
    "metz": {"odds_name": "Metz", "api_football_id": 112, "api_name": "metz"},
    "monaco": {"odds_name": "Monaco", "api_football_id": 91, "api_name": "monaco"},
    "montpellier": {"odds_name": "Montpellier", "api_football_id": 82, "api_name": "montpellier"},
    "nantes": {"odds_name": "Nantes", "api_football_id": 83, "api_name": "nantes"},
    "nice": {"odds_name": "Nice", "api_football_id": 84, "api_name": "nice"},
    "paris saint germain": {"odds_name": "Paris Saint Germain", "api_football_id": 85, "api_name": "paris saint germain"},
    "reims": {"odds_name": "Reims", "api_football_id": 93, "api_name": "reims"},
    "rennes": {"odds_name": "Rennes", "api_football_id": 94, "api_name": "rennes"},
    "saint etienne": {"odds_name": "Saint Etienne", "api_football_id": 1063, "api_name": "saint etienne"},
    "stade brestois 29": {"odds_name": "Stade Brestois 29", "api_football_id": 106, "api_name": "stade brestois 29"},
    "strasbourg": {"odds_name": "Strasbourg", "api_football_id": 95, "api_name": "strasbourg"},
    "toulouse": {"odds_name": "Toulouse", "api_football_id": 96, "api_name": "toulouse"},
    
    # ============================================
    # Serie B (Italy) - Key Teams
    # ============================================
    "pisa": {"odds_name": "Pisa", "api_football_id": 113, "api_name": "pisa"},
    "brescia": {"odds_name": "Brescia", "api_football_id": 488, "api_name": "brescia"},
    "palermo": {"odds_name": "Palermo", "api_football_id": 475, "api_name": "palermo"},
    "bari": {"odds_name": "Bari", "api_football_id": 460, "api_name": "bari"},
    
    # ============================================
    # Common Aliases (常見別名)
    # ============================================
    # English
    "manchester city": {"odds_name": "Manchester City", "api_football_id": 50, "api_name": "manchester city"},
    "manchester c": {"odds_name": "Manchester City", "api_football_id": 50, "api_name": "manchester city"},
    "mancity": {"odds_name": "Manchester City", "api_football_id": 50, "api_name": "manchester city"},
    "manchester united": {"odds_name": "Manchester United", "api_football_id": 33, "api_name": "manchester united"},
    "manchester u": {"odds_name": "Manchester United", "api_football_id": 33, "api_name": "manchester united"},
    "manutd": {"odds_name": "Manchester United", "api_football_id": 33, "api_name": "manchester united"},
    "liverpool": {"odds_name": "Liverpool", "api_football_id": 40, "api_name": "liverpool"},
    "arsenal": {"odds_name": "Arsenal", "api_football_id": 42, "api_name": "arsenal"},
    "chelsea": {"odds_name": "Chelsea", "api_football_id": 49, "api_name": "chelsea"},
    "tottenham": {"odds_name": "Tottenham", "api_football_id": 47, "api_name": "tottenham"},
    "tottenham hotspur": {"odds_name": "Tottenham", "api_football_id": 47, "api_name": "tottenham"},
    "newcastle": {"odds_name": "Newcastle", "api_football_id": 34, "api_name": "newcastle"},
    "newcastle united": {"odds_name": "Newcastle", "api_football_id": 34, "api_name": "newcastle"},
    "west ham": {"odds_name": "West Ham", "api_football_id": 48, "api_name": "west ham"},
    "west ham united": {"odds_name": "West Ham", "api_football_id": 48, "api_name": "west ham"},
    "wolves": {"odds_name": "Wolves", "api_football_id": 39, "api_name": "wolves"},
    "wolverhampton": {"odds_name": "Wolves", "api_football_id": 39, "api_name": "wolves"},
    "brighton": {"odds_name": "Brighton", "api_football_id": 51, "api_name": "brighton"},
    "brighton and hove albion": {"odds_name": "Brighton", "api_football_id": 51, "api_name": "brighton"},
    "fulham": {"odds_name": "Fulham", "api_football_id": 36, "api_name": "fulham"},
    "crystal palace": {"odds_name": "Crystal Palace", "api_football_id": 52, "api_name": "crystal palace"},
    "everton": {"odds_name": "Everton", "api_football_id": 45, "api_name": "everton"},
    "brentford": {"odds_name": "Brentford", "api_football_id": 55, "api_name": "brentford"},
    "bournemouth": {"odds_name": "Bournemouth", "api_football_id": 35, "api_name": "bournemouth"},
    "afc bournemouth": {"odds_name": "Bournemouth", "api_football_id": 35, "api_name": "bournemouth"},
    "aston villa": {"odds_name": "Aston Villa", "api_football_id": 66, "api_name": "aston villa"},
    "leicester": {"odds_name": "Leicester", "api_football_id": 46, "api_name": "leicester"},
    "leicester city": {"odds_name": "Leicester", "api_football_id": 46, "api_name": "leicester"},
    "nottingham forest": {"odds_name": "Nottingham Forest", "api_football_id": 65, "api_name": "nottingham forest"},
    "ipswich": {"odds_name": "Ipswich", "api_football_id": 57, "api_name": "ipswich"},
    "ipswich town": {"odds_name": "Ipswich", "api_football_id": 57, "api_name": "ipswich"},
    "southampton": {"odds_name": "Southampton", "api_football_id": 41, "api_name": "southampton"},
    
    # Spanish
    "real madrid": {"odds_name": "Real Madrid", "api_football_id": 541, "api_name": "real madrid"},
    "barcelona": {"odds_name": "Barcelona", "api_football_id": 529, "api_name": "barcelona"},
    "barca": {"odds_name": "Barcelona", "api_football_id": 529, "api_name": "barcelona"},
    "atletico madrid": {"odds_name": "Atletico Madrid", "api_football_id": 530, "api_name": "atletico madrid"},
    "atletico": {"odds_name": "Atletico Madrid", "api_football_id": 530, "api_name": "atletico madrid"},
    "sevilla": {"odds_name": "Sevilla", "api_football_id": 536, "api_name": "sevilla"},
    "valencia": {"odds_name": "Valencia", "api_football_id": 532, "api_name": "valencia"},
    "villarreal": {"odds_name": "Villarreal", "api_football_id": 533, "api_name": "villarreal"},
    "real sociedad": {"odds_name": "Real Sociedad", "api_football_id": 548, "api_name": "real sociedad"},
    "athletic": {"odds_name": "Athletic Club", "api_football_id": 531, "api_name": "athletic club"},
    "athletic bilbao": {"odds_name": "Athletic Club", "api_football_id": 531, "api_name": "athletic club"},
    "betis": {"odds_name": "Real Betis", "api_football_id": 543, "api_name": "real betis"},
    "real betis": {"odds_name": "Real Betis", "api_football_id": 543, "api_name": "real betis"},
    
    # German
    "bayern munich": {"odds_name": "Bayern Munchen", "api_football_id": 157, "api_name": "bayern munchen"},
    "bayern": {"odds_name": "Bayern Munchen", "api_football_id": 157, "api_name": "bayern munchen"},
    "borussia dortmund": {"odds_name": "Borussia Dortmund", "api_football_id": 165, "api_name": "borussia dortmund"},
    "dortmund": {"odds_name": "Borussia Dortmund", "api_football_id": 165, "api_name": "borussia dortmund"},
    "leverkusen": {"odds_name": "Bayer Leverkusen", "api_football_id": 168, "api_name": "bayer leverkusen"},
    "bayer leverkusen": {"odds_name": "Bayer Leverkusen", "api_football_id": 168, "api_name": "bayer leverkusen"},
    "rb leipzig": {"odds_name": "RB Leipzig", "api_football_id": 173, "api_name": "rb leipzig"},
    "leipzig": {"odds_name": "RB Leipzig", "api_football_id": 173, "api_name": "rb leipzig"},
    "eintracht frankfurt": {"odds_name": "Eintracht Frankfurt", "api_football_id": 169, "api_name": "eintracht frankfurt"},
    "frankfurt": {"odds_name": "Eintracht Frankfurt", "api_football_id": 169, "api_name": "eintracht frankfurt"},
    "wolfsburg": {"odds_name": "VfL Wolfsburg", "api_football_id": 161, "api_name": "vfl wolfsburg"},
    "vfl wolfsburg": {"odds_name": "VfL Wolfsburg", "api_football_id": 161, "api_name": "vfl wolfsburg"},
    "stuttgart": {"odds_name": "VfB Stuttgart", "api_football_id": 172, "api_name": "vfb stuttgart"},
    "vfb stuttgart": {"odds_name": "VfB Stuttgart", "api_football_id": 172, "api_name": "vfb stuttgart"},
    "freiburg": {"odds_name": "SC Freiburg", "api_football_id": 160, "api_name": "sc freiburg"},
    "sc freiburg": {"odds_name": "SC Freiburg", "api_football_id": 160, "api_name": "sc freiburg"},
    "borussia monchengladbach": {"odds_name": "Borussia Monchengladbach", "api_football_id": 163, "api_name": "borussia monchengladbach"},
    "gladbach": {"odds_name": "Borussia Monchengladbach", "api_football_id": 163, "api_name": "borussia monchengladbach"},
    
    # Italian
    "inter": {"odds_name": "Inter", "api_football_id": 505, "api_name": "inter"},
    "inter milan": {"odds_name": "Inter", "api_football_id": 505, "api_name": "inter"},
    "ac milan": {"odds_name": "AC Milan", "api_football_id": 489, "api_name": "ac milan"},
    "milan": {"odds_name": "AC Milan", "api_football_id": 489, "api_name": "ac milan"},
    "juventus": {"odds_name": "Juventus", "api_football_id": 496, "api_name": "juventus"},
    "napoli": {"odds_name": "Napoli", "api_football_id": 492, "api_name": "napoli"},
    "roma": {"odds_name": "AS Roma", "api_football_id": 497, "api_name": "as roma"},
    "as roma": {"odds_name": "AS Roma", "api_football_id": 497, "api_name": "as roma"},
    "lazio": {"odds_name": "Lazio", "api_football_id": 487, "api_name": "lazio"},
    "atalanta": {"odds_name": "Atalanta", "api_football_id": 499, "api_name": "atalanta"},
    "fiorentina": {"odds_name": "Fiorentina", "api_football_id": 502, "api_name": "fiorentina"},
    "bologna": {"odds_name": "Bologna", "api_football_id": 500, "api_name": "bologna"},
    "torino": {"odds_name": "Torino", "api_football_id": 503, "api_name": "torino"},
    "udinese": {"odds_name": "Udinese", "api_football_id": 494, "api_name": "udinese"},
    "sampdoria": {"odds_name": "Sampdoria", "api_football_id": 497, "api_name": "sampdoria"},
    "genoa": {"odds_name": "Genoa", "api_football_id": 495, "api_name": "genoa"},
    "cagliari": {"odds_name": "Cagliari", "api_football_id": 490, "api_name": "cagliari"},
    "hellas verona": {"odds_name": "Verona", "api_football_id": 504, "api_name": "verona"},
    "verona": {"odds_name": "Verona", "api_football_id": 504, "api_name": "verona"},
    "lecce": {"odds_name": "Lecce", "api_football_id": 867, "api_name": "lecce"},
    "empoli": {"odds_name": "Empoli", "api_football_id": 511, "api_name": "empoli"},
    "monza": {"odds_name": "Monza", "api_football_id": 1579, "api_name": "monza"},
    "como": {"odds_name": "Como", "api_football_id": 895, "api_name": "como"},
    "parma": {"odds_name": "Parma", "api_football_id": 523, "api_name": "parma"},
    
    # French
    "paris saint germain": {"odds_name": "Paris Saint Germain", "api_football_id": 85, "api_name": "paris saint germain"},
    "psg": {"odds_name": "Paris Saint Germain", "api_football_id": 85, "api_name": "paris saint germain"},
    "marseille": {"odds_name": "Marseille", "api_football_id": 81, "api_name": "marseille"},
    "lyon": {"odds_name": "Lyon", "api_football_id": 80, "api_name": "lyon"},
    "olympique lyonnais": {"odds_name": "Lyon", "api_football_id": 80, "api_name": "lyon"},
    "lille": {"odds_name": "Lille", "api_football_id": 79, "api_name": "lille"},
    "monaco": {"odds_name": "Monaco", "api_football_id": 91, "api_name": "monaco"},
    "as monaco": {"odds_name": "Monaco", "api_football_id": 91, "api_name": "monaco"},
    "rennes": {"odds_name": "Rennes", "api_football_id": 94, "api_name": "rennes"},
    "nice": {"odds_name": "Nice", "api_football_id": 84, "api_name": "nice"},
    "paris saint germain": {"odds_name": "Paris Saint Germain", "api_football_id": 85, "api_name": "paris saint germain"},
    "reims": {"odds_name": "Reims", "api_football_id": 93, "api_name": "reims"},
    "rennes": {"odds_name": "Rennes", "api_football_id": 94, "api_name": "rennes"},
    "nantes": {"odds_name": "Nantes", "api_football_id": 83, "api_name": "nantes"},
    "montpellier": {"odds_name": "Montpellier", "api_football_id": 82, "api_name": "montpellier"},
    "strasbourg": {"odds_name": "Strasbourg", "api_football_id": 95, "api_name": "strasbourg"},
    "reims": {"odds_name": "Reims", "api_football_id": 93, "api_name": "reims"},
    "toulouse": {"odds_name": "Toulouse", "api_football_id": 96, "api_name": "toulouse"},
    "lens": {"odds_name": "Lens", "api_football_id": 116, "api_name": "lens"},
}


def normalize_team_name(name: str) -> str:
    """標準化球隊名稱"""
    name = name.lower().strip()
    name = re.sub(r'[^\w\s]', '', name)
    name = name.replace(' fc', '').replace(' united', '').replace(' club', '')
    name = name.replace('-', ' ').replace('_', ' ')
    name = ' '.join(name.split())
    return name


def fuzzy_match(team_name: str, candidates: list, threshold: float = 0.6) -> Optional[str]:
    """模糊匹配球隊名稱"""
    normalized_input = normalize_team_name(team_name)
    best_match = None
    best_score = 0

    for candidate in candidates:
        normalized_candidate = normalize_team_name(candidate)

        if normalized_input == normalized_candidate:
            return candidate

        score = SequenceMatcher(None, normalized_input, normalized_candidate).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_match = candidate

    return best_match


def get_team_info(team_name: str) -> Dict:
    """獲取球隊的完整信息（整合兩個 API）"""
    normalized = normalize_team_name(team_name)

    if normalized in TEAM_MAPPING_DB:
        info = TEAM_MAPPING_DB[normalized]
        return {
            "odds_name": info["odds_name"],
            "api_football_id": info["api_football_id"],
            "api_name": info["api_name"],
            "matched": True,
            "source": "local"
        }

    for key, info in TEAM_MAPPING_DB.items():
        if info["api_name"] == normalized:
            return {
                "odds_name": info["odds_name"],
                "api_football_id": info["api_football_id"],
                "api_name": info["api_name"],
                "matched": True,
                "source": "local"
            }
        try:
            if info["api_football_id"] == int(normalized):
                return {
                    "odds_name": info["odds_name"],
                    "api_football_id": info["api_football_id"],
                    "api_name": info["api_name"],
                    "matched": True,
                    "source": "local"
                }
        except ValueError:
            continue

    return {
        "odds_name": team_name,
        "api_football_id": None,
        "api_name": team_name.lower(),
        "matched": False,
        "source": "gemini_needed"
    }


def call_gemini_match(home_team: str, away_team: str) -> Dict[str, Dict]:
    """使用 Gemini API 匹配球隊名稱"""
    gemini_key = getattr(settings, 'GEMINI_API_KEY', '')

    if not gemini_key:
        print("[WARNING] Gemini API Key 未設定，無法進行智能匹配")
        return {}

    prompt = f"""Match these football teams to the API-Football database:
- Home: "{home_team}"
- Away: "{away_team}"

Return ONLY valid JSON (no markdown):
{{{{
  "home": {{{{
    "odds_name": "matched name",
    "api_football_id": ID,
    "api_name": "api-football-name",
    "confidence": 0.0-1.0
  }}}},
  "away": {{{{
    "odds_name": "matched name",
    "api_football_id": ID,
    "api_name": "api-football-name",
    "confidence": 0.0-1.0
  }}}}
}}}}
If no good match, set api_football_id to null and confidence to 0.
"""

    import urllib.request
    import urllib.error
    import ssl

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={gemini_key}"
    data = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        context = ssl.create_default_context()
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        response = urllib.request.urlopen(req, timeout=15, context=context)
        result = json.loads(response.read().decode('utf-8'))

        if 'candidates' in result:
            content = result['candidates'][0]['content']['parts'][0]['text']
            content = content.strip().replace('```json', '').replace('```', '')
            return json.loads(content)

    except Exception as e:
        print(f"[ERROR] Gemini API Error: {e}")

    return {}


def match_teams(home_team: str, away_team: str) -> Dict:
    """整合匹配函數 - 先用本地映射，必要時用 Gemini"""
    result = {
        "home": get_team_info(home_team),
        "away": get_team_info(away_team),
        "gemini_used": False
    }

    if not result["home"]["matched"] or not result["away"]["matched"]:
        print("[API] 使用 Gemini API 進行智能匹配...")
        gemini_result = call_gemini_match(home_team, away_team)

        if gemini_result:
            if not result["home"]["matched"] and "home" in gemini_result:
                result["home"].update(gemini_result["home"])
                result["home"]["source"] = "gemini"
            if not result["away"]["matched"] and "away" in gemini_result:
                result["away"].update(gemini_result["away"])
                result["away"]["source"] = "gemini"
            result["gemini_used"] = True

    return result


if __name__ == "__main__":
    print("=" * 60)
    print("球隊名稱匹配測試")
    print("=" * 60)

    test_cases = [
        ("Cerezo Osaka", "Gamba Osaka"),
        ("Hellas Verona", "Pisa"),
        ("Inter Milan", "Juventus"),
        ("Manchester City", "Arsenal"),
        ("Real Madrid", "Barcelona"),
        ("Bayern Munich", "Dortmund"),
    ]

    for home, away in test_cases:
        print(f"\n{home} vs {away}")
        result = match_teams(home, away)

        print(f"   主隊:")
        print(f"      Odds API: {result['home']['odds_name']}")
        print(f"      API-Football ID: {result['home']['api_football_id']}")
        print(f"      Matched: {result['home']['matched']} ({result['home']['source']})")

        print(f"   客隊:")
        print(f"      Odds API: {result['away']['odds_name']}")
        print(f"      API-Football ID: {result['away']['api_football_id']}")
        print(f"      Matched: {result['away']['matched']} ({result['away']['source']})")
