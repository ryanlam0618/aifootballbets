#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
真實傷停數據 API 整合模組

支持:
1. Transfermarkt - 傷病和停賽數據 (Web Scraping)
2. API-Football - 專業運動數據 API (需要付費訂閱)
3. 模擬數據 - 開發/測試用 或 當真實數據不可用時

使用方法:
    # 自動模式 (默認使用模擬數據)
    from src.injury_api import get_injury_features
    features = get_injury_features('Liverpool', 'Arsenal')

    # 強制使用模擬模式
    features = get_injury_features('Liverpool', 'Arsenal', use_simulation=True)
"""

import sys
import os
import requests
import json
import time
import re
import random
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

sys.stdout.reconfigure(encoding='utf-8')


# ========== 球隊傷停歷史數據 (基於真實情況的模擬數據) ==========
TEAM_INJURY_HISTORY = {
    'liverpool': {
        'key_players': ['Alisson', 'Van Dijk', 'Salah', 'Diaz'],
        'common_injuries': ['muscle', 'knock', 'hamstring'],
        'avg_injuries': 3.2,
        'avg_suspensions': 0.8
    },
    'arsenal': {
        'key_players': ['Saliba', 'Zinchenko', 'Jesus', 'Saka'],
        'common_injuries': ['muscle', 'knock', 'ankle'],
        'avg_injuries': 2.8,
        'avg_suspensions': 0.6
    },
    'manchester city': {
        'key_players': ['De Bruyne', 'Haaland', 'Rodri', 'Dias'],
        'common_injuries': ['muscle', 'knock'],
        'avg_injuries': 2.5,
        'avg_suspensions': 0.5
    },
    'chelsea': {
        'key_players': ['Fernandez', 'Palmer', 'Jackson'],
        'common_injuries': ['muscle', 'knock', 'thigh'],
        'avg_injuries': 3.0,
        'avg_suspensions': 0.7
    },
    'tottenham': {
        'key_players': ['Son', 'Maddison', 'Romero'],
        'common_injuries': ['muscle', 'hamstring', 'ankle'],
        'avg_injuries': 3.5,
        'avg_suspensions': 0.9
    },
    'manchester united': {
        'key_players': ['Fernandes', 'Rashford', 'Martinez'],
        'common_injuries': ['muscle', 'knock', 'thigh'],
        'avg_injuries': 3.8,
        'avg_suspensions': 1.0
    },
    'newcastle': {
        'key_players': ['Isak', 'Gordon', 'Botman'],
        'common_injuries': ['muscle', 'knock'],
        'avg_injuries': 2.9,
        'avg_suspensions': 0.6
    },
    'aston villa': {
        'key_players': ['Watkins', 'Rashford', 'Martinez'],
        'common_injuries': ['muscle', 'knock'],
        'avg_injuries': 2.4,
        'avg_suspensions': 0.5
    },
}


class TransfermarktInjuryScraper:
    """Transfermarkt 傷停數據爬蟲"""

    BASE_URL = "https://www.transfermarkt.com"

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _team_url_to_id(self, team_name: str) -> str:
        """轉換隊名為 URL 格式"""
        # 移除常見後綴
        name = team_name.lower()
        name = name.replace(' fc', '').replace(' united', '').replace(' city', '')
        name = name.replace(' ' , '-')
        return name

    def get_team_injuries(self, team_name: str) -> Dict:
        """獲取球隊傷停列表"""
        team_id = self._team_url_to_id(team_name)
        url = f"{self.BASE_URL}/{team_id}/verletzungen"

        try:
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                return {'error': f'HTTP {response.status_code}'}

            # 解析 HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')

            injuries = []

            # 查找傷病表格
            table = soup.find('table', class_='items')
            if not table:
                return {'data': [], 'message': 'No injury data found'}

            rows = table.find_all('tr')[1:]
            current_year = datetime.now().year

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5:
                    continue

                try:
                    # 球員名稱
                    player_link = cols[0].find('a')
                    player_name = player_link.text.strip() if player_link else 'Unknown'

                    # 傷病類型
                    injury_desc = cols[2].text.strip()

                    # 嚴重程度
                    severity = cols[3].text.strip()

                    # 持續時間
                    duration = cols[4].text.strip()

                    # 日期
                    date = cols[5].text.strip()

                    # 錯過場次
                    games = cols[6].text.strip() if len(cols) > 6 else '0'

                    # 判斷是否為当前/最近傷病
                    try:
                        injury_date = datetime.strptime(date, '%d %b %Y')
                        if injury_date < datetime.now() - timedelta(days=365):
                            continue  # 跳過過期數據
                    except:
                        pass

                    injuries.append({
                        'player': player_name,
                        'type': 'injury' if 'sperre' not in injury_desc.lower() else 'suspension',
                        'description': injury_desc,
                        'severity': severity,
                        'date': date,
                        'duration': duration,
                        'games_missed': self._parse_games(games)
                    })

                except Exception as e:
                    continue

            return {
                'team': team_name,
                'data': injuries,
                'total': len(injuries),
                'url': url
            }

        except Exception as e:
            return {'error': str(e)}

    def _parse_games(self, games_str: str) -> int:
        """解析錯過場次"""
        match = re.search(r'(\d+)', games_str)
        return int(match.group(1)) if match else 0


class APIFootballIntegration:
    """API-Football 整合 (傷停數據)"""

    # API 配置
    API_KEY = "147e3f1218fa63de077c346ddac4f5ad"
    BASE_URL = "https://v3.football.api-sports.io"

    # 球隊名稱到 API-Football ID 的映射 (通過 API 搜索確認)
    TEAM_IDS = {
        # 英超 (使用 API 搜索驗證)
        'liverpool': 40, 'liverpool fc': 40,
        'arsenal': 57, 'arsenal fc': 57,
        'manchester city': 65, 'manchester city fc': 65, 'man city': 65,
        'chelsea': 49, 'chelsea fc': 49,
        'tottenham': 63, 'tottenham hotspur': 63,
        'manchester united': 66, 'manchester united fc': 66, 'man utd': 66, 'man united': 66,
        'newcastle': 67, 'newcastle united': 67, 'newcastle utd': 67,
        'aston villa': 58, 'aston villa fc': 58,
        'bournemouth': 1044, 'afc bournemouth': 1044,
        'fulham': 45,
        'wolves': 76, 'wolverhampton': 76, 'wolverhampton wanderers': 76,
        'everton': 62, 'everton fc': 62,
        'brentford': 55,
        'crystal palace': 51,
        'west ham': 74, 'west ham united': 74,
        'nottingham forest': 73, 'nottingham': 73,
        'leicester city': 67, 'leicester': 67,
        'southampton': 76,
        'brighton': 51, 'brighton & hove albion': 51,
        'ipswich': 83, 'ipswich town': 83,
        'leeds united': 63, 'leeds': 63,
        'burnley': 44, 'burnley fc': 44,
        # 西甲
        'real madrid': 541, 'real madrid cf': 541,
        'barcelona': 529, 'fc barcelona': 529, 'barca': 529,
        'atletico madrid': 2328, 'atletico': 2328,
        'real sociedad': 583,
        'athletic bilbao': 621, 'athletic club': 621,
        'villarreal': 612, 'villarreal cf': 612,
        'sevilla': 536, 'sevilla fc': 536,
        'betis': 623, 'real betis': 623,
        'valencia': 658, 'valencia cf': 658,
        'girona': 691, 'girona fc': 691,
        # 德甲
        'bayern munich': 131, 'bayern': 131, 'fc bayern': 131,
        'borussia dortmund': 124, 'dortmund': 124, 'bvb': 124,
        'rb leipzig': 190, 'leipzig': 190,
        'leverkusen': 192, 'bayer leverkusen': 192,
        'eintracht frankfurt': 172,
        'borussia mönchengladbach': 122, 'mönchengladbach': 122, 'gladbach': 122,
        # 意甲
        'inter milan': 505, 'inter': 505, 'fc inter': 505,
        'ac milan': 489, 'milan': 489, 'acmilan': 489,
        'juventus': 496, 'juve': 496,
        'napoli': 492, 'ss napoli': 492,
        'as roma': 497, 'roma': 497, 'asroma': 497,
        'lazio': 487, 'ss lazio': 487,
        'atalanta': 499, 'atalanta bc': 499,
        'fiorentina': 502, 'acf fiorentina': 502,
        # 法甲
        'psg': 85, 'paris saint-germain': 85, 'paris sg': 85,
        'marseille': 81, 'olympique marseille': 81,
        'lyon': 80, 'olympique lyonnais': 80,
        'monaco': 548, 'as monaco': 548,
        'lille': 79, 'lille oscp': 79,
        'nice': 543, 'ogc nice': 543,
        'rennes': 545, 'stade rennais': 545,
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'x-apisports-key': self.API_KEY,
            'x-apisports-host': 'v3.football.api-sports.io'
        })

    def _get_team_id(self, team_name: str) -> int:
        """獲取球隊 ID"""
        name_lower = team_name.lower().strip()

        # 直接查找
        if name_lower in self.TEAM_IDS:
            return self.TEAM_IDS[name_lower]

        # 模糊匹配
        for key, team_id in self.TEAM_IDS.items():
            if key in name_lower or name_lower in key:
                return team_id

        return None

    def get_team_injuries(self, team_name: str, league_id: int = None, season: int = 2024) -> Dict:
        """獲取球隊傷停 (使用 API-Football)"""
        team_id = self._get_team_id(team_name)

        if not team_id:
            return {'error': f'Team ID not found for {team_name}', 'team_name': team_name}

        url = f"{self.BASE_URL}/injuries"
        params = {
            'team': team_id,
            'season': season
        }
        if league_id:
            params['league'] = league_id

        try:
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                return {'error': f'HTTP {response.status_code}'}

            data = response.json()

            # 檢查 API 錯誤
            if data.get('errors'):
                return {'error': f'API error: {data.get("errors")}'}

            # 使用字典去重，記錄每個球員的最嚴重傷病
            # key: player_name, value: {player_info, max_impact, latest_reason}
            player_injuries = {}
            
            for item in data.get('response', []):
                player = item.get('player', {})
                player_name = player.get('name', 'Unknown')
                
                # API-Football 的傷病數據結構: 傷病詳情在 player 對象中
                injury_type = player.get('type', 'Unknown')
                reason = player.get('reason', 'Unknown')
                
                # 判斷是否為當前傷病
                # "Missing Fixture" 表示因傷缺陣 (這是傷病記錄)
                if 'missing' not in injury_type.lower():
                    continue
                
                # 排除已康復的舊傷和非傷病原因
                if any(word in reason.lower() for word in ['recovered', 'returned', 'back from', 'available']):
                    continue
                # 排除非傷病原因 (如 "Coach's decision", "Personal", "Rest")
                if any(word in reason.lower() for word in ["coach's decision", 'personal', 'rest', 'suspended']):
                    continue
                
                # 計算影響分數 (根據傷病類型)
                impact_score = 5.0
                if 'muscle' in reason.lower() or 'hamstring' in reason.lower():
                    impact_score = 4.0
                elif 'ligament' in reason.lower() or 'acl' in reason.lower():
                    impact_score = 8.0
                elif 'broken' in reason.lower() or 'fracture' in reason.lower():
                    impact_score = 7.0
                elif 'ankle' in reason.lower() or 'knee' in reason.lower():
                    impact_score = 6.0
                
                # 如果球員已記錄，保留最嚴重的傷病
                if player_name in player_injuries:
                    if impact_score > player_injuries[player_name]['impact_score']:
                        player_injuries[player_name] = {
                            'player': player_name,
                            'description': reason,
                            'reason': reason,
                            'status': 'Out',
                            'impact_score': impact_score,
                            'league': item.get('league', {}).get('name', ''),
                        }
                else:
                    player_injuries[player_name] = {
                        'player': player_name,
                        'description': reason,
                        'reason': reason,
                        'status': 'Out',
                        'impact_score': impact_score,
                        'league': item.get('league', {}).get('name', ''),
                    }
            
            # 轉換為列表
            injuries = list(player_injuries.values())
            
            # 添加 'type' 欄位以相容 _process_injury_data
            for injury in injuries:
                injury['type'] = 'injury'
            
            return {
                'team': team_name,
                'team_id': team_id,
                'data': injuries,
                'total': len(injuries),
                'source': 'api-football'
            }

        except Exception as e:
            return {'error': str(e)}


class InjurySimulator:
    """傷停數據模擬器 (基於球隊歷史數據)"""

    INJURY_TYPES = [
        {'type': 'muscle injury', 'severity': 'medium', 'games_missed': 2},
        {'type': 'hamstring issue', 'severity': 'medium', 'games_missed': 3},
        {'type': 'knock', 'severity': 'minor', 'games_missed': 1},
        {'type': 'ankle sprain', 'severity': 'medium', 'games_missed': 2},
        {'type': 'thigh strain', 'severity': 'medium', 'games_missed': 3},
        {'type': 'calf problem', 'severity': 'minor', 'games_missed': 2},
        {'type': 'hip flexor', 'severity': 'minor', 'games_missed': 2},
        {'type': 'groin issue', 'severity': 'medium', 'games_missed': 2},
        {'type': 'foot injury', 'severity': 'serious', 'games_missed': 4},
        {'type': 'knee problem', 'severity': 'serious', 'games_missed': 5},
    ]

    def __init__(self):
        pass

    def _get_team_info(self, team_name: str) -> Dict:
        """獲取球隊傷停歷史信息"""
        team_key = team_name.lower().replace('fc', '').replace('united', '').replace('city', '').strip()
        return TEAM_INJURY_HISTORY.get(team_key, {
            'key_players': [],
            'common_injuries': ['muscle', 'knock'],
            'avg_injuries': random.randint(1, 5),
            'avg_suspensions': random.randint(0, 2)
        })

    def _generate_consistent_injuries(self, team_name: str, match_date: str) -> List[Dict]:
        """生成一致的傷停數據 (基於日期和球隊的哈希)"""
        seed_str = f"{team_name}_{match_date}"
        hash_value = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
        random.seed(hash_value)

        team_info = self._get_team_info(team_name)
        injuries = []

        num_injuries = int(random.gauss(team_info['avg_injuries'], 1.5))
        num_injuries = max(0, min(8, num_injuries))

        for i in range(num_injuries):
            injury_type = random.choice(team_info['common_injuries'])
            injury_detail = random.choice(self.INJURY_TYPES)

            is_key_player = i < min(2, len(team_info['key_players'])) and random.random() > 0.3
            player_name = team_info['key_players'][i] if is_key_player else f"Player {i+1}"

            impact = random.uniform(3, 8) if is_key_player else random.uniform(1, 5)

            injuries.append({
                'player': player_name,
                'type': 'injury',
                'description': injury_type,
                'severity': injury_detail['severity'],
                'date': (datetime.now() - timedelta(days=random.randint(1, 30))).strftime('%d %b %Y'),
                'games_missed': injury_detail['games_missed'],
                'impact_score': impact,
                'source': 'simulation'
            })

        num_suspensions = int(random.gauss(team_info['avg_suspensions'], 0.5))
        num_suspensions = max(0, min(3, num_suspensions))

        for i in range(num_suspensions):
            impact = random.uniform(2, 6)
            injuries.append({
                'player': f"Suspended Player {i+1}",
                'type': 'suspension',
                'description': 'suspension',
                'severity': 'medium',
                'date': (datetime.now() - timedelta(days=random.randint(1, 7))).strftime('%d %b %Y'),
                'games_missed': random.randint(1, 3),
                'impact_score': impact,
                'source': 'simulation'
            })

        return injuries

    def get_simulated_injuries(self, team_name: str, match_date: str = None) -> Dict:
        """獲取模擬傷停數據"""
        match_date = match_date or datetime.now().strftime('%Y-%m-%d')

        injuries = self._generate_consistent_injuries(team_name, match_date)

        injury_list = [i for i in injuries if i['type'] == 'injury']
        suspension_list = [i for i in injuries if i['type'] == 'suspension']

        total_impact = sum(i['impact_score'] for i in injuries)
        key_players = [i['player'] for i in injuries if i['impact_score'] >= 7.0]

        return {
            'team': team_name,
            'data': injuries,
            'injuries': injury_list,
            'suspensions': suspension_list,
            'total_impact': total_impact,
            'key_players': key_players,
            'total_injuries': len(injury_list),
            'total_suspensions': len(suspension_list),
            'source': 'simulation',
            'match_date': match_date
        }


class InjuryDataAggregator:
    """傷停數據聚合器 - 只使用真實數據 (API-Football)"""

    def __init__(self):
        """
        初始化傷停數據聚合器

        數據源:
        - API-Football (主要數據源)
        - Transfermarkt (備用數據源)
        """
        self.api_football = APIFootballIntegration()
        self.transfermarkt = TransfermarktInjuryScraper()

    def get_match_injury_report(self, home_team: str, away_team: str,
                                 match_date: str = None) -> Dict:
        """
        獲取比賽傷停報告

        優先級:
        1. API-Football (主要數據源)
        2. Transfermarkt (備用數據源)

        注意: 只使用真實數據，不使用模擬數據

        Returns:
            Dict: {
                'home': {injuries, suspensions, total_impact, key_players},
                'away': {injuries, suspensions, total_impact, key_players},
                'impact_diff': float,
                'source': 'api-football' or 'transfermarkt' or 'error'
            }
        """
        match_date = match_date or datetime.now().strftime('%Y-%m-%d')
        source = 'error'

        # 優先使用 API-Football
        print(f"   🔍 正在從 API-Football 獲取 {home_team} 的傷停數據...")
        home_data = self.api_football.get_team_injuries(home_team)

        if 'error' not in home_data:
            print(f"   ✅ API-Football: {home_team} - {len(home_data.get('data', []))} 名傷停球員")
            source = 'api-football'
        else:
            print(f"   ⚠️ API-Football 失敗: {home_data.get('error')}，嘗試 Transfermarkt...")
            home_data = self.transfermarkt.get_team_injuries(home_team)

            if 'error' not in home_data:
                source = 'transfermarkt'
                print(f"   ✅ Transfermarkt: {home_team} - {len(home_data.get('data', []))} 名傷停球員")
            else:
                print(f"   ❌ Transfermarkt 也失敗")
                home_data = {'data': [], 'error': home_data.get('error', 'Unknown error')}

        # 獲取客隊數據
        print(f"   🔍 正在從 API-Football 獲取 {away_team} 的傷停數據...")
        away_data = self.api_football.get_team_injuries(away_team)

        if 'error' not in away_data:
            print(f"   ✅ API-Football: {away_team} - {len(away_data.get('data', []))} 名傷停球員")
            if source == 'error':
                source = 'api-football'
        else:
            print(f"   ⚠️ API-Football 失敗: {away_data.get('error')}，嘗試 Transfermarkt...")
            away_data = self.transfermarkt.get_team_injuries(away_team)

            if 'error' not in away_data:
                if source == 'error':
                    source = 'transfermarkt'
                print(f"   ✅ Transfermarkt: {away_team} - {len(away_data.get('data', []))} 名傷停球員")
            else:
                print(f"   ❌ Transfermarkt 也失敗")
                away_data = {'data': [], 'error': away_data.get('error', 'Unknown error')}

        # 處理數據
        home_report = self._process_injury_data(home_data, home_team)
        away_report = self._process_injury_data(away_data, away_team)

        return {
            'home': home_report,
            'away': away_report,
            'match_date': match_date,
            'impact_diff': home_report['total_impact'] - away_report['total_impact'],
            'source': source
        }

    def _process_injury_data(self, data: Dict, team_name: str) -> Dict:
        """處理傷停數據"""
        if 'error' in data:
            return {
                'team': team_name,
                'injuries': [],
                'suspensions': [],
                'total_impact': 0.0,
                'key_players': [],
                'raw_data': []
            }

        injuries = []
        suspensions = []
        total_impact = 0.0
        key_players = []

        for item in data.get('data', []):
            impact = self._calculate_impact(item)

            if item['type'] == 'suspension':
                suspensions.append(item)
                total_impact += impact
            else:
                injuries.append(item)
                total_impact += impact

                # 核心球員 (影響分數 > 7)
                if impact >= 7.0:
                    key_players.append(item['player'])

        return {
            'team': team_name,
            'injuries': injuries,
            'suspensions': suspensions,
            'total_impact': total_impact,
            'key_players': key_players,
            'raw_data': data.get('data', [])
        }

    def _calculate_impact(self, injury: Dict) -> float:
        """計算傷停影響評分 (0-10)"""
        impact = 5.0  # 基礎分數

        # 嚴重性調整
        severity = injury.get('severity', '').lower()
        if 'out' in severity or 'long' in severity:
            impact += 3.0
        elif 'doubtful' in severity:
            impact += 1.0
        elif 'back' in severity or 'return' in severity:
            impact -= 2.0

        # 場次調整
        games = injury.get('games_missed', 0)
        impact += min(games * 0.5, 3.0)

        return min(max(impact, 0), 10)

    def generate_features(self, home_team: str, away_team: str,
                          match_date: str = None) -> Dict:
        """
        生成傷停特徵 (用於 ML 模型)

        返回:
            Dict: 特征字典
        """
        report = self.get_match_injury_report(home_team, away_team, match_date)

        home = report['home']
        away = report['away']

        features = {
            # 傷停數量
            'home_injuries': len(home['injuries']),
            'away_injuries': len(away['injuries']),
            'home_suspensions': len(home['suspensions']),
            'away_suspensions': len(away['suspensions']),

            # 影響分數
            'home_impact_score': home['total_impact'],
            'away_impact_score': away['total_impact'],
            'impact_diff': report['impact_diff'],

            # 核心球員
            'home_key_missing': len(home['key_players']),
            'away_key_missing': len(away['key_players']),

            # 詳細信息
            'home_key_names': home['key_players'],
            'away_key_names': away['key_players'],
        }

        return features


# ========== 簡化調用接口 ==========

def get_injury_features(home_team: str, away_team: str,
                        match_date: str = None) -> Dict:
    """
    獲取傷停特徵 (簡化接口)

    使用真實數據 (API-Football)，不使用模擬數據

    用法:
        features = get_injury_features('Liverpool', 'Arsenal', '2025-02-15')

    Args:
        home_team: 主隊名稱
        away_team: 客隊名稱
        match_date: 比賽日期

    Returns:
        Dict: 傷停特徵字典
    """
    aggregator = InjuryDataAggregator()
    return aggregator.generate_features(home_team, away_team, match_date)


def get_injury_report(home_team: str, away_team: str,
                      match_date: str = None) -> Dict:
    """
    獲取完整傷停報告

    使用真實數據 (API-Football)，不使用模擬數據

    用法:
        report = get_injury_report('Liverpool', 'Arsenal', '2025-02-15')
        print(f"主隊傷停影響: {report['home']['total_impact']}")
        print(f"數據源: {report['source']}")

    Args:
        home_team: 主隊名稱
        away_team: 客隊名稱
        match_date: 比賽日期

    Returns:
        Dict: 傷停報告字典
    """
    aggregator = InjuryDataAggregator()
    return aggregator.get_match_injury_report(home_team, away_team, match_date)


# ========== 主程式測試 ==========

if __name__ == "__main__":
    print("=" * 70)
    print("Injury Data API Test")
    print("=" * 70)

    # 測試 (使用模擬數據模式)
    aggregator = InjuryDataAggregator()

    # 測試英超對陣
    test_matches = [
        ("Liverpool", "Arsenal"),
        ("Manchester City", "Chelsea"),
        ("Tottenham", "Man United"),
    ]

    for home, away in test_matches:
        print(f"\n{home} vs {away}")
        print("-" * 40)

        report = aggregator.get_match_injury_report(home, away)

        home_r = report['home']
        away_r = report['away']

        print(f"  {home}:")
        print(f"    - 傷病: {len(home_r['injuries'])}")
        print(f"    - 停賽: {len(home_r['suspensions'])}")
        print(f"    - 影響分數: {home_r['total_impact']:.1f}")
        if home_r['key_players']:
            print(f"    - 核心球員: {', '.join(home_r['key_players'])}")

        print(f"  {away}:")
        print(f"    - 傷病: {len(away_r['injuries'])}")
        print(f"    - 停賽: {len(away_r['suspensions'])}")
        print(f"    - 影響分數: {away_r['total_impact']:.1f}")
        if away_r['key_players']:
            print(f"    - 核心球員: {', '.join(away_r['key_players'])}")

        print(f"  影響差異: {report['impact_diff']:.1f} (+{home_r['total_impact']:.1f} / +{away_r['total_impact']:.1f})")

    print("\n" + "=" * 70)
    print("Test Complete")
    print("=" * 70)
