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
# 本地球隊名稱映射 (快速匹配)
# ============================================

# The Odds API 名稱 -> API-Football ID 和 名稱
TEAM_MAPPING_DB = {
    # J1 League
    "avispa fukuoka": {"odds_name": "Avispa Fukuoka", "api_football_id": 316, "api_name": "avispa fukuoka"},
    "cerezo osaka": {"odds_name": "Cerezo Osaka", "api_football_id": 291, "api_name": "cerezo osaka"},
    "fc tokyo": {"odds_name": "FC Tokyo", "api_football_id": 292, "api_name": "fc tokyo"},
    "fagiano okayama": {"odds_name": "Fagiano Okayama", "api_football_id": 310, "api_name": "fagiano okayama"},
    "gamba osaka": {"odds_name": "Gamba Osaka", "api_football_id": 293, "api_name": "gamba osaka"},
    "jef united chiba": {"odds_name": "JEF United Chiba", "api_football_id": 301, "api_name": "jef united chiba"},
    "kashima antlers": {"odds_name": "Kashima Antlers", "api_football_id": 290, "api_name": "kashima"},
    "kashiwa reysol": {"odds_name": "Kashiwa Reysol", "api_football_id": 281, "api_name": "kashiwa reysol"},
    "kawasaki frontale": {"odds_name": "Kawasaki Frontale", "api_football_id": 294, "api_name": "kawasaki frontale"},
    "mito hollyhock": {"odds_name": "Mito HollyHock", "api_football_id": 305, "api_name": "mito hollyhock"},
    "nagoya grampus": {"odds_name": "Nagoya Grampus", "api_football_id": 288, "api_name": "nagoya grampus"},
    "shimizu s-pulse": {"odds_name": "Shimizu S Pulse", "api_football_id": 283, "api_name": "shimizu s-pulse"},
    "shimizu s pulse": {"odds_name": "Shimizu S Pulse", "api_football_id": 283, "api_name": "shimizu s-pulse"},
    "tokyo verdy": {"odds_name": "Tokyo Verdy", "api_football_id": 306, "api_name": "tokyo verdy"},
    "urawa red diamonds": {"odds_name": "Urawa Red Diamonds", "api_football_id": 287, "api_name": "urawa"},
    "urawa": {"odds_name": "Urawa Red Diamonds", "api_football_id": 287, "api_name": "urawa"},
    "consadole sapporo": {"odds_name": "Consadole Sapporo", "api_football_id": 279, "api_name": "consadole sapporo"},
    "jubilo iwata": {"odds_name": "Jubilo Iwata", "api_football_id": 280, "api_name": "jubilo iwata"},
    "sanfrecce hiroshima": {"odds_name": "Sanfrecce Hiroshima", "api_football_id": 282, "api_name": "sanfrecce hiroshima"},
    "shonan bellmare": {"odds_name": "Shonan Bellmare", "api_football_id": 284, "api_name": "shonan bellmare"},
    "vissel kobe": {"odds_name": "Vissel Kobe", "api_football_id": 289, "api_name": "vissel kobe"},
    "yokohama f. marinos": {"odds_name": "Yokohama F. Marinos", "api_football_id": 296, "api_name": "yokohama f. marinos"},
    "yokohama marinos": {"odds_name": "Yokohama F. Marinos", "api_football_id": 296, "api_name": "yokohama f. marinos"},
    "sagan tosu": {"odds_name": "Sagan Tosu", "api_football_id": 295, "api_name": "sagan tosu"},
    "kyoto sanga": {"odds_name": "Kyoto Sanga", "api_football_id": 302, "api_name": "kyoto sanga"},
    "machida zelvia": {"odds_name": "Machida Zelvia", "api_football_id": 303, "api_name": "machida zelvia"},
    "albirex niigata": {"odds_name": "Albirex Niigata", "api_football_id": 311, "api_name": "albirex niigata"},
    # J2 League
    "v-varen nagasaki": {"odds_name": "V-Varen Nagasaki", "api_football_id": 285, "api_name": "v-varen nagasaki"},
    "vegalta sendai": {"odds_name": "Vegalta Sendai", "api_football_id": 286, "api_name": "vegalta sendai"},
    "oita trinita": {"odds_name": "Oita Trinita", "api_football_id": 298, "api_name": "oita trinita"},
    "tokushima vortis": {"odds_name": "Tokushima Vortis", "api_football_id": 299, "api_name": "tokushima vortis"},
    "yokohama fc": {"odds_name": "Yokohama FC", "api_football_id": 307, "api_name": "yokohama fc"},
    "ventforet kofu": {"odds_name": "Ventforet Kofu", "api_football_id": 308, "api_name": "ventforet kofu"},
    "renofa yamaguchi": {"odds_name": "Renofa Yamaguchi", "api_football_id": 309, "api_name": "renofa yamaguchi"},
    "montedio yamagata": {"odds_name": "Montedio Yamagata", "api_football_id": 312, "api_name": "montedio yamagata"},
    "roasso kumamoto": {"odds_name": "Roasso Kumamoto", "api_football_id": 314, "api_name": "roasso kumamoto"},
    "tochigi sc": {"odds_name": "Tochigi SC", "api_football_id": 315, "api_name": "tochigi sc"},
    "ehime fc": {"odds_name": "Ehime FC", "api_football_id": 318, "api_name": "ehime fc"},
    "thespakusatsu gunma": {"odds_name": "Thespakusatsu Gunma", "api_football_id": 756, "api_name": "thespakusatsu gunma"},
    "blaublitz akita": {"odds_name": "Blaublitz Akita", "api_football_id": 4315, "api_name": "blaublitz akita"},
    "fujieda myfc": {"odds_name": "Fujieda MYFC", "api_football_id": 4317, "api_name": "fujieda myfc"},
# English Premier League
    "liverpool": {"odds_name": "Liverpool", "api_football_id": 40, "api_name": "liverpool"},
    "arsenal": {"odds_name": "Arsenal", "api_football_id": 42, "api_name": "arsenal"},
    "manchester city": {"odds_name": "Manchester City", "api_football_id": 65, "api_name": "manchester city"},
    "chelsea": {"odds_name": "Chelsea", "api_football_id": 49, "api_name": "chelsea"},
    "tottenham": {"odds_name": "Tottenham Hotspur", "api_football_id": 63, "api_name": "tottenham"},
    "manchester united": {"odds_name": "Manchester United", "api_football_id": 66, "api_name": "manchester united"},
    "newcastle": {"odds_name": "Newcastle United", "api_football_id": 67, "api_name": "newcastle"},
    "aston villa": {"odds_name": "Aston Villa", "api_football_id": 58, "api_name": "aston villa"},
    "manchester city": {"odds_name": "Manchester City", "api_football_id": 65, "api_name": "manchester city"},
    "brighton and hove albion": {"odds_name": "Brighton and Hove Albion", "api_football_id": 51, "api_name": "brighton"},
    "brighton": {"odds_name": "Brighton and Hove Albion", "api_football_id": 51, "api_name": "brighton"},
    "west ham": {"odds_name": "West Ham United", "api_football_id": 62, "api_name": "west ham"},
    "west ham united": {"odds_name": "West Ham United", "api_football_id": 62, "api_name": "west ham"},
    "fulham": {"odds_name": "Fulham", "api_football_id": 36, "api_name": "fulham"},
    "wolves": {"odds_name": "Wolverhampton Wanderers", "api_football_id": 39, "api_name": "wolverhampton"},
    "wolverhampton wanderers": {"odds_name": "Wolverhampton Wanderers", "api_football_id": 39, "api_name": "wolverhampton"},
    "crystal palace": {"odds_name": "Crystal Palace", "api_football_id": 52, "api_name": "crystal palace"},
    "bournemouth": {"odds_name": "Bournemouth", "api_football_id": 35, "api_name": "bournemouth"},
    "afc bournemouth": {"odds_name": "Bournemouth", "api_football_id": 35, "api_name": "bournemouth"},
    "brentford": {"odds_name": "Brentford", "api_football_id": 55, "api_name": "brentford"},
    "everton": {"odds_name": "Everton", "api_football_id": 45, "api_name": "everton"},
    "leeds": {"odds_name": "Leeds United", "api_football_id": 61, "api_name": "leeds"},
    "leeds united": {"odds_name": "Leeds United", "api_football_id": 61, "api_name": "leeds"},
    "nottingham forest": {"odds_name": "Nottingham Forest", "api_football_id": 71, "api_name": "nottingham forest"},
    "sunderland": {"odds_name": "Sunderland", "api_football_id": 74, "api_name": "sunderland"},
    "burnley": {"odds_name": "Burnley", "api_football_id": 44, "api_name": "burnley"},
    "leicester": {"odds_name": "Leicester City", "api_football_id": 46, "api_name": "leicester"},
    "leicester city": {"odds_name": "Leicester City", "api_football_id": 46, "api_name": "leicester"},

    # La Liga (Spain)
    "real madrid": {"odds_name": "Real Madrid", "api_football_id": 541, "api_name": "real madrid"},
    "barcelona": {"odds_name": "Barcelona", "api_football_id": 529, "api_name": "barcelona"},
    "atletico madrid": {"odds_name": "Atlético Madrid", "api_football_id": 530, "api_name": "atletico madrid"},
    "sevilla": {"odds_name": "Sevilla", "api_football_id": 536, "api_name": "sevilla"},
    "valencia": {"odds_name": "Valencia", "api_football_id": 532, "api_name": "valencia"},
    "villarreal": {"odds_name": "Villarreal", "api_football_id": 533, "api_name": "villarreal"},
    "real sociedad": {"odds_name": "Real Sociedad", "api_football_id": 548, "api_name": "real sociedad"},
    "athletic bilbao": {"odds_name": "Athletic Bilbao", "api_football_id": 531, "api_name": "athletic bilbao"},
    "betis": {"odds_name": "Real Betis", "api_football_id": 543, "api_name": "real betis"},
    "real betis": {"odds_name": "Real Betis", "api_football_id": 543, "api_name": "real betis"},
    "celta vigo": {"odds_name": "Celta Vigo", "api_football_id": 538, "api_name": "celta vigo"},
    "getafe": {"odds_name": "Getafe", "api_football_id": 545, "api_name": "getafe"},
    "espanyol": {"odds_name": "Espanyol", "api_football_id": 583, "api_name": "espanyol"},
    "mallorca": {"odds_name": "Mallorca", "api_football_id": 798, "api_name": "mallorca"},
    "osasuna": {"odds_name": "CA Osasuna", "api_football_id": 804, "api_name": "osasuna"},
    "rayo vallecano": {"odds_name": "Rayo Vallecano", "api_football_id": 538, "api_name": "rayo vallecano"},
    "girona": {"odds_name": "Girona", "api_football_id": 547, "api_name": "girona"},
    "alaves": {"odds_name": "Alavés", "api_football_id": 532, "api_name": "alavés"},
    "alavés": {"odds_name": "Alavés", "api_football_id": 532, "api_name": "alavés"},
    "levante": {"odds_name": "Levante", "api_football_id": 550, "api_name": "levante"},
    "elche": {"odds_name": "Elche CF", "api_football_id": 796, "api_name": "elche"},
    "oviedo": {"odds_name": "Oviedo", "api_football_id": 810, "api_name": "oviedo"},

    # Bundesliga (Germany)
    "bayern munich": {"odds_name": "Bayern Munich", "api_football_id": 157, "api_name": "bayern munich"},
    "borussia dortmund": {"odds_name": "Borussia Dortmund", "api_football_id": 165, "api_name": "borussia dortmund"},
    "rb leipzig": {"odds_name": "RB Leipzig", "api_football_id": 168, "api_name": "rb leipzig"},
    "leverkusen": {"odds_name": "Bayer Leverkusen", "api_football_id": 168, "api_name": "bayer leverkusen"},
    "bayer leverkusen": {"odds_name": "Bayer Leverkusen", "api_football_id": 168, "api_name": "bayer leverkusen"},
    "eintracht frankfurt": {"odds_name": "Eintracht Frankfurt", "api_football_id": 161, "api_name": "eintracht frankfurt"},
    "dortmund": {"odds_name": "Borussia Dortmund", "api_football_id": 165, "api_name": "borussia dortmund"},
    "borussia monchengladbach": {"odds_name": "Borussia Mönchengladbach", "api_football_id": 163, "api_name": "borussia mönchengladbach"},
    "mönchengladbach": {"odds_name": "Borussia Mönchengladbach", "api_football_id": 163, "api_name": "borussia mönchengladbach"},
    "wolfsburg": {"odds_name": "VfL Wolfsburg", "api_football_id": 170, "api_name": "wolfsburg"},
    "vfl wolfsburg": {"odds_name": "VfL Wolfsburg", "api_football_id": 170, "api_name": "wolfsburg"},
    "stuttgart": {"odds_name": "VfB Stuttgart", "api_football_id": 172, "api_name": "stuttgart"},
    "vfb stuttgart": {"odds_name": "VfB Stuttgart", "api_football_id": 172, "api_name": "stuttgart"},
    "freiburg": {"odds_name": "SC Freiburg", "api_football_id": 173, "api_name": "freiburg"},
    "sc freiburg": {"odds_name": "SC Freiburg", "api_football_id": 173, "api_name": "freiburg"},
    "hoffenheim": {"odds_name": "TSG Hoffenheim", "api_football_id": 192, "api_name": "hoffenheim"},
    "tsg hoffenheim": {"odds_name": "TSG Hoffenheim", "api_football_id": 192, "api_name": "hoffenheim"},
    "mainz": {"odds_name": "FSV Mainz 05", "api_football_id": 169, "api_name": "mainz"},
    "fsv mainz": {"odds_name": "FSV Mainz 05", "api_football_id": 169, "api_name": "mainz"},
    "cologne": {"odds_name": "1. FC Köln", "api_football_id": 192, "api_name": "1. fc köln"},
    "1. fc köln": {"odds_name": "1. FC Köln", "api_football_id": 192, "api_name": "1. fc köln"},
    "augsburg": {"odds_name": "Augsburg", "api_football_id": 170, "api_name": "augsburg"},
    "union berlin": {"odds_name": "Union Berlin", "api_football_id": 191, "api_name": "union berlin"},
    "hamburger sv": {"odds_name": "Hamburger SV", "api_football_id": 182, "api_name": "hamburger sv"},
    "werder bremen": {"odds_name": "Werder Bremen", "api_football_id": 162, "api_name": "werder bremen"},
    "bremen": {"odds_name": "Werder Bremen", "api_football_id": 162, "api_name": "werder bremen"},
    "heidenheim": {"odds_name": "1. FC Heidenheim", "api_football_id": 205, "api_name": "heidenheim"},
    "1. fc heidenheim": {"odds_name": "1. FC Heidenheim", "api_football_id": 205, "api_name": "heidenheim"},
    "st. pauli": {"odds_name": "FC St. Pauli", "api_football_id": 188, "api_name": "st. pauli"},
    "fc st. pauli": {"odds_name": "FC St. Pauli", "api_football_id": 188, "api_name": "st. pauli"},

    # Serie A (Italy)
    "inter milan": {"odds_name": "Inter Milan", "api_football_id": 505, "api_name": "inter"},
    "inter": {"odds_name": "Inter Milan", "api_football_id": 505, "api_name": "inter"},
    "ac milan": {"odds_name": "AC Milan", "api_football_id": 503, "api_name": "milan"},
    "milan": {"odds_name": "AC Milan", "api_football_id": 503, "api_name": "milan"},
    "juventus": {"odds_name": "Juventus", "api_football_id": 495, "api_name": "juventus"},
    "napoli": {"odds_name": "Napoli", "api_football_id": 492, "api_name": "napoli"},
    "roma": {"odds_name": "AS Roma", "api_football_id": 487, "api_name": "roma"},
    "as roma": {"odds_name": "AS Roma", "api_football_id": 487, "api_name": "roma"},
    "lazio": {"odds_name": "Lazio", "api_football_id": 487, "api_name": "lazio"},
    "atalanta": {"odds_name": "Atalanta BC", "api_football_id": 499, "api_name": "atalanta"},
    "atalanta bc": {"odds_name": "Atalanta BC", "api_football_id": 499, "api_name": "atalanta"},
    "lille": {"odds_name": "Lille", "api_football_id": 79, "api_name": "lille"},
    "paris saint germain": {"odds_name": "Paris Saint Germain", "api_football_id": 85, "api_name": "paris saint-germain"},
    "psg": {"odds_name": "Paris Saint Germain", "api_football_id": 85, "api_name": "paris saint-germain"},
    "olympique lyonnais": {"odds_name": "Lyon", "api_football_id": 78, "api_name": "lyon"},
    "lyon": {"odds_name": "Lyon", "api_football_id": 78, "api_name": "lyon"},
    "marseille": {"odds_name": "Marseille", "api_football_id": 77, "api_name": "marseille"},
    "om": {"odds_name": "Marseille", "api_football_id": 77, "api_name": "marseille"},
    "monaco": {"odds_name": "AS Monaco", "api_football_id": 76, "api_name": "monaco"},
    "as monaco": {"odds_name": "AS Monaco", "api_football_id": 76, "api_name": "monaco"},
    "rennes": {"odds_name": "Rennes", "api_football_id": 87, "api_name": "rennes"},
    "stade rennais": {"odds_name": "Rennes", "api_football_id": 87, "api_name": "rennes"},
}


def normalize_team_name(name: str) -> str:
    """標準化球隊名稱"""
    # 移除常見後綴和特殊字符
    name = name.lower().strip()
    name = re.sub(r'[^\w\s]', '', name)  # 移除特殊字符
    # 注意：不要移除 'city'，因為很多球隊名稱包含 'city'
    name = name.replace(' fc', '').replace(' united', '').replace(' club', '')
    name = name.replace('-', ' ').replace('_', ' ')
    name = ' '.join(name.split())  # 移除多餘空格
    return name


def fuzzy_match(team_name: str, candidates: list, threshold: float = 0.6) -> Optional[str]:
    """模糊匹配球隊名稱"""
    normalized_input = normalize_team_name(team_name)
    best_match = None
    best_score = 0

    for candidate in candidates:
        normalized_candidate = normalize_team_name(candidate)

        # 直接匹配
        if normalized_input == normalized_candidate:
            return candidate

        # 模糊匹配
        score = SequenceMatcher(None, normalized_input, normalized_candidate).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_match = candidate

    return best_match


def get_team_info(team_name: str) -> Dict:
    """
    獲取球隊的完整信息（整合兩個 API）
    返回: {odds_name, api_football_id, api_name, matched}
    """
    normalized = normalize_team_name(team_name)

    # 1. 快速本地匹配
    if normalized in TEAM_MAPPING_DB:
        info = TEAM_MAPPING_DB[normalized]
        return {
            "odds_name": info["odds_name"],
            "api_football_id": info["api_football_id"],
            "api_name": info["api_name"],
            "matched": True,
            "source": "local"
        }

    # 2. 反向查找 (API-Football 名稱 -> 找 The Odds API)
    for key, info in TEAM_MAPPING_DB.items():
        if info["api_name"] == normalized:
            return {
                "odds_name": info["odds_name"],
                "api_football_id": info["api_football_id"],
                "api_name": info["api_name"],
                "matched": True,
                "source": "local"
            }
        # 嘗試將字符串轉換為整數（如果它是數字字符串）
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

    # 3. 需要 Gemini API 匹配
    return {
        "odds_name": team_name,
        "api_football_id": None,
        "api_name": team_name.lower(),
        "matched": False,
        "source": "gemini_needed"
    }


# ============================================
# Gemini API 智能匹配
# ============================================

def call_gemini_match(home_team: str, away_team: str) -> Dict[str, Dict]:
    """
    使用 Gemini API 匹配球隊名稱
    返回: {home: {odds_name, api_football_id, api_name}, away: {...}}
    """
    gemini_key = getattr(settings, 'GEMINI_API_KEY', '')

    if not gemini_key:
        print("⚠️  Gemini API Key 未設定，無法進行智能匹配")
        return {}

    prompt = f"""
You are a football team name matcher. I need to match team names between two APIs:

**The Odds API** (format: "Team Name FC" or "Full Name")
**API-Football** (format: lowercase, no special characters)

Please match these teams and return JSON:

Input:
- Home Team: "{home_team}"
- Away Team: "{away_team}"

Available API-Football teams (Japan J1 + J2):
{json.dumps([v for k, v in TEAM_MAPPING_DB.items() if v["api_football_id"] in [279, 280, 281, 282, 283, 284, 285, 286, 287, 288, 289, 290, 291, 292, 293, 294, 295, 296, 297, 298, 299, 300, 301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 311, 312, 313, 314, 315, 316]], indent=2)}

Return JSON format:
```json
{{
  "home": {{
    "odds_name": "Exact name from Odds API",
    "api_football_id": 123,
    "api_name": "api-football name",
    "confidence": 0.95
  }},
  "away": {{
    "odds_name": "Exact name from Odds API",
    "api_football_id": 456,
    "api_name": "api-football name",
    "confidence": 0.95
  }}
}}
```

If team not found, set api_football_id to null and confidence to 0.
Only return the JSON, no other text.
"""

    import urllib.request
    import urllib.error

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={gemini_key}"
    data = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        response = urllib.request.urlopen(req, timeout=10)
        result = json.loads(response.read().decode('utf-8'))

        if 'candidates' in result:
            content = result['candidates'][0]['content']['parts'][0]['text']
            # 提取 JSON
            content = content.strip().strip('```json').strip('```')
            return json.loads(content)

    except Exception as e:
        print(f"❌ Gemini API Error: {e}")

    return {}


def match_teams(home_team: str, away_team: str) -> Dict:
    """
    整合匹配函數 - 先用本地映射，必要時用 Gemini
    """
    result = {
        "home": get_team_info(home_team),
        "away": get_team_info(away_team),
        "gemini_used": False
    }

    # 檢查是否需要 Gemini
    if not result["home"]["matched"] or not result["away"]["matched"]:
        print("🔄 使用 Gemini API 進行智能匹配...")
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


# ============================================
# 測試
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("🔍 球隊名稱匹配測試")
    print("=" * 60)

    # 測試用例
    test_cases = [
        ("Cerezo Osaka", "Gamba Osaka"),
        ("Urawa Red Diamonds", "Kashima Antlers"),
        ("Tokyo Verdy", "Mito HollyHock"),
        ("Nagoya Grampus", "Shimizu S Pulse"),
    ]

    for home, away in test_cases:
        print(f"\n🏟️ {home} vs {away}")
        result = match_teams(home, away)

        print(f"   主隊:")
        print(f"      Odds API: {result['home']['odds_name']}")
        print(f"      API-Football ID: {result['home']['api_football_id']}")
        print(f"      API-Football Name: {result['home']['api_name']}")
        print(f"      Matched: {result['home']['matched']} ({result['home']['source']})")

        print(f"   客隊:")
        print(f"      Odds API: {result['away']['odds_name']}")
        print(f"      API-Football ID: {result['away']['api_football_id']}")
        print(f"      API-Football Name: {result['away']['api_name']}")
        print(f"      Matched: {result['away']['matched']} ({result['away']['source']})")
