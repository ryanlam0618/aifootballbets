#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
陣容數據 API 整合模組

支持:
1. API-Football - 主要數據源 (需要 API key)
2. FotMob - 備用數據源 (Web scraping)

使用方法:
    from src.lineup_api import LineupAggregator
    
    lineup = LineupAggregator.get_lineup("Liverpool", "Arsenal", "2025-02-15")
"""

import sys
import os
import re
import time
import json
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple

sys.stdout.reconfigure(encoding='utf-8')


class APIFootballLineups:
    """API-Football 陣容數據"""
    
    API_KEY = "147e3f1218fa63de077c346ddac4f5ad"
    BASE_URL = "https://v3.football.api-sports.io"
    
    # 球隊名稱到 API-Football ID 的映射
    TEAM_IDS = {
        'liverpool': 40, 'liverpool fc': 40,
        'arsenal': 42, 'arsenal fc': 42,
        'manchester city': 65, 'man city': 65,
        'chelsea': 49, 'chelsea fc': 49,
        'tottenham': 63, 'tottenham hotspur': 63,
        'manchester united': 66, 'man utd': 66,
        'newcastle': 67, 'newcastle united': 67,
        'aston villa': 58,
        'bournemouth': 1044, 'afc bournemouth': 1044,
        'fulham': 45,
        'wolves': 76, 'wolverhampton': 76,
        'everton': 62,
        'brentford': 55,
        'crystal palace': 51,
        'west ham': 74, 'west ham united': 74,
        'nottingham forest': 73,
        'leicester city': 67,
        'southampton': 76,
        'brighton': 51,
        'ipswich': 83, 'ipswich town': 83,
        'burnley': 44,
        # 西甲
        'real madrid': 541,
        'barcelona': 529, 'fc barcelona': 529,
        'atletico madrid': 2328,
        'real sociedad': 583,
        'athletic bilbao': 621,
        'villarreal': 612,
        'sevilla': 536,
        'betis': 623,
        'valencia': 658,
        'girona': 691,
        # 德甲
        'bayern munich': 131, 'bayern': 131,
        'borussia dortmund': 124,
        'rb leipzig': 190,
        'leverkusen': 192,
        'eintracht frankfurt': 172,
        'borussia mönchengladbach': 122,
        # 意甲
        'inter milan': 505, 'inter': 505,
        'ac milan': 489, 'milan': 489,
        'juventus': 496,
        'napoli': 492,
        'as roma': 497, 'roma': 497,
        'lazio': 487,
        'atalanta': 499,
        'fiorentina': 502,
        # 法甲
        'psg': 85, 'paris saint-germain': 85,
        'marseille': 81,
        'lyon': 80,
        'monaco': 548,
        'lille': 79,
        'nice': 543,
        'rennes': 545,
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
        
        if name_lower in self.TEAM_IDS:
            return self.TEAM_IDS[name_lower]
        
        for key, team_id in self.TEAM_IDS.items():
            if key in name_lower or name_lower in key:
                return team_id
        
        return None
    
    def search_fixtures(self, home_team: str, away_team: str, date: str = None) -> Optional[int]:
        """搜索比賽 ID"""
        url = f"{self.BASE_URL}/fixtures"
        
        params = {
            'team': self._get_team_id(home_team),
            'season': 2024
        }
        
        if date:
            params['date'] = date
        
        try:
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if data.get('errors'):
                return None
            
            # API-Football 返回的是直接列表，不需要 'fixtures' 嵌套
            for fixture in data.get('response', []):
                teams = fixture.get('teams', {})
                home = teams.get('home', {}).get('name', '').lower()
                away = teams.get('away', {}).get('name', '').lower()
                
                # 檢查兩種方向
                if (home_team.lower() in home and away_team.lower() in away) or \
                   (away_team.lower() in home and home_team.lower() in away):
                    return fixture.get('fixture', {}).get('id')
            
            return None
            
        except Exception as e:
            print(f"   ⚠️ 搜索比賽失敗: {e}")
            return None
    
    def get_lineup(self, home_team: str, away_team: str, date: str = None) -> Optional[Dict]:
        """獲取比賽陣容"""
        # 步驟 1: 搜索比賽 ID
        fixture_id = self.search_fixtures(home_team, away_team, date)
        
        if not fixture_id:
            print(f"   ⚠️ 找不到 {home_team} vs {away_team} 的比賽 ID")
            return None
        
        # 步驟 2: 獲取陣容數據
        url = f"{self.BASE_URL}/lineups"
        params = {'fixture': fixture_id}
        
        try:
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                print(f"   ⚠️ API 回應錯誤: {response.status_code}")
                return None
            
            data = response.json()
            
            if data.get('errors'):
                print(f"   ⚠️ API 錯誤: {data.get('errors')}")
                return None
            
            if not data.get('response'):
                print(f"   ⚠️ 沒有陣容數據")
                return None
            
            # 解析陣容數據
            result = {
                'match_id': fixture_id,
                'date': date or datetime.now().strftime('%Y-%m-%d'),
                'home_team': None,
                'away_team': None,
                'source': 'api-football'
            }
            
            for team in data['response']:
                team_info = team.get('team', {})
                team_name = team_info.get('name', '')
                
                lineup_data = {
                    'name': team_name,
                    'formation': team.get('formation', 'Unknown'),
                    'coach': team.get('coach', {}).get('name', 'Unknown'),
                    'starters': [],
                    'substitutes': []
                }
                
                # 主力球員
                for p in team.get('startXI', []):
                    player = p.get('player', {})
                    lineup_data['starters'].append({
                        'id': player.get('id'),
                        'name': player.get('name'),
                        'position': player.get('position'),
                        'number': player.get('number'),
                    })
                
                # 替補球員
                for p in team.get('substitutes', []):
                    player = p.get('player', {})
                    lineup_data['substitutes'].append({
                        'id': player.get('id'),
                        'name': player.get('name'),
                        'position': player.get('position'),
                    })
                
                # 分配到主/客隊
                if home_team.lower() in team_name.lower():
                    result['home_team'] = lineup_data
                else:
                    result['away_team'] = lineup_data
            
            return result
            
        except Exception as e:
            print(f"   ⚠️ 獲取陣容失敗: {e}")
            return None


class FotMobLineups:
    """FotMob 陣容數據 (備用)"""
    
    BASE_URL = "https://www.fotmob.com"
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.fotmob.com/"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def _search_match_id(self, home_team: str, away_team: str) -> Optional[str]:
        """搜索比賽 ID"""
        search_url = f"{self.BASE_URL}/api/searchAll"
        params = {
            "query": f"{home_team} {away_team}",
            "type": "match"
        }
        
        try:
            response = self.session.get(search_url, params=params, timeout=10)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            matches = data.get('matches', [])
            
            for match in matches:
                home = match.get('home', {}).get('name', '').lower()
                away = match.get('away', {}).get('name', '').lower()
                
                if home_team.lower() in home and away_team.lower() in away:
                    return str(match.get('id'))
            
            return None
            
        except Exception as e:
            print(f"   ⚠️ FotMob 搜索失敗: {e}")
            return None

    def get_lineup(self, home_team: str, away_team: str, date: str = None) -> Optional[Dict]:
        """獲取比賽陣容 (自動搜索 + 獲取)"""
        # 先搜索 match ID
        match_id = self._search_match_id(home_team, away_team)
        
        if not match_id:
            print(f"   ⚠️ FotMob 找不到 {home_team} vs {away_team} 的比賽")
            return None
        
        # 獲取陣容
        return self.get_lineup_by_id(match_id, home_team, away_team, date)

    def get_lineup_by_id(self, match_id: str, home_team: str, away_team: str, date: str = None) -> Optional[Dict]:
        """通過 match ID 獲取陣容"""
        url = f"{self.BASE_URL}/api/matchDetails?matchId={match_id}"
        
        try:
            response = self.session.get(url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            # 解析 FotMob 數據結構
            content = data.get('content', {})
            lineup_root = content.get('lineup', {})
            
            if not lineup_root or 'homeTeam' not in lineup_root:
                return None
            
            def extract_players(team_data):
                players = []
                starters = team_data.get('starters', [])
                for p in starters:
                    players.append({
                        'id': p.get('id'),
                        'name': p.get('name'),
                        'position': p.get('positionId'),
                        'number': p.get('shirtNumber'),
                    })
                return players
            
            result = {
                'match_id': match_id,
                'date': date or datetime.now().strftime('%Y-%m-%d'),
                'source': 'fotmob',
                'home_team': {
                    'name': lineup_root['homeTeam']['name'],
                    'formation': lineup_root['homeTeam'].get('formation'),
                    'coach': lineup_root['homeTeam'].get('coach', {}).get('name'),
                    'starters': extract_players(lineup_root['homeTeam']),
                    'substitutes': lineup_root['homeTeam'].get('substitutes', [])
                },
                'away_team': {
                    'name': lineup_root['awayTeam']['name'],
                    'formation': lineup_root['awayTeam'].get('formation'),
                    'coach': lineup_root['awayTeam'].get('coach', {}).get('name'),
                    'starters': extract_players(lineup_root['awayTeam']),
                    'substitutes': lineup_root['awayTeam'].get('substitutes', [])
                }
            }

            return result
            
            return result
            
        except Exception as e:
            print(f"   ⚠️ FotMob 獲取失敗: {e}")
            return None


class LineupAggregator:
    """陣容數據聚合器"""
    
    def __init__(self):
        self.api_football = APIFootballLineups()
        self.fotmob = FotMobLineups()
    
    def get_lineup(self, home_team: str, away_team: str, date: str = None,
                   auto_save: bool = True) -> Optional[Dict]:
        """
        獲取比賽陣容

        優先級:
        1. API-Football (需要高級訂閱)
        2. FotMob API (已失效 - 端點已移除)
        3. 手動輸入

        Args:
            home_team: 主隊名稱
            away_team: 客隊名稱
            date: 比賽日期 (可選)
            auto_save: 是否自動保存到文件

        Returns:
            Dict: 陣容數據 或 None
        """
        date_str = date or datetime.now().strftime('%Y-%m-%d')

        print(f"   [1/2] 獲取 {home_team} vs {away_team} 陣容...")

        # 優先使用 API-Football
        print(f"   [嘗試 API-Football (需要高級訂閱)]")
        lineup = self.api_football.get_lineup(home_team, away_team, date_str)

        if lineup:
            print(f"   [OK] API-Football 成功獲取陣容!")
            if auto_save:
                self._save_lineup(lineup)
            return lineup

        # API-Football 失敗，嘗試 FotMob
        print(f"\n   [注意] API-Football 不可用")
        print(f"   [嘗試 FotMob API...]")
        lineup = self.fotmob.get_lineup(home_team, away_team, date_str)

        if lineup:
            print(f"   [OK] FotMob 成功獲取陣容!")
            if auto_save:
                self._save_lineup(lineup)
            return lineup

        # 所有 API 都失敗
        print(f"\n   [警告] 無法自動獲取陣容數據")
        print(f"   ====== 選項 ======")
        print(f"   [1] 手動輸入陣容數據")
        print(f"   [2] 使用 FotMob Match ID 爬取陣容")
        print(f"   =================")

        choice = input(f"   請選擇 (1/2): ").strip()

        if choice == "1":
            print(f"   [手動輸入模式] 請提供以下格式的 JSON:")
            print(f"""   {{
    "home_team": {{"name": "Home", "formation": "4-3-3", "starters": [{{"name": "Player1", "position": "Midfielder"}}]}},
    "away_team": {{"name": "Away", "formation": "4-4-2", "starters": [{{"name": "Player2", "position": "Forward"}}]}}
   }}""")

            json_str = input(f"   請輸入 JSON (直接按 Enter 跳過): ").strip()

            if json_str:
                try:
                    import json
                    lineup = {
                        'match_id': 'manual',
                        'date': date_str,
                        'source': 'manual',
                        'home_team': {},
                        'away_team': {}
                    }
                    data = json.loads(json_str)
                    lineup['home_team'] = data.get('home_team', {})
                    lineup['away_team'] = data.get('away_team', {})
                    print(f"   [OK] 手動輸入成功!")
                    if auto_save:
                        self._save_lineup(lineup)
                    return lineup
                except Exception as e:
                    print(f"   [錯誤] JSON 解析失敗: {e}")

        elif choice == "2":
            # 使用 FotMob Lineup Scraper
            try:
                from TakeData.fotmob_lineup_scraper import FotMobLineupHarvester
            except ImportError:
                print(f"   [錯誤] 無法導入 FotMobLineupHarvester")
                print(f"   [跳過] 略過陣容獲取，將使用歷史平均評分")
                return None

            match_id = input(f"   請輸入 FotMob Match ID (例如: 4830636): ").strip()

            if not match_id:
                print(f"   [跳過] 未輸入 Match ID")
                return None

            print(f"   [INFO] 正在使用 FotMob 爬取陣容...")
            harvester = FotMobLineupHarvester(match_id)
            lineup = harvester.fetch_lineup(save_to_file=bool(auto_save))

            if lineup:
                print(f"   [OK] FotMob 爬取成功!")
                lineup['date'] = date_str
                lineup['source'] = 'fotmob_manual'
                if auto_save:
                    self._save_lineup(lineup)
                return lineup
            else:
                print(f"   [錯誤] FotMob 爬取失敗")
                return None

        print(f"   [跳過] 略過陣容獲取，將使用歷史平均評分")
        return None
    
    def _save_lineup(self, lineup: Dict, save_folder: str = None):
        """保存陣容到文件"""
        if save_folder is None:
            save_folder = r"C:\Users\Ryan\python\.vscode\fb_ai_bets\data\lineup"
        
        if not os.path.exists(save_folder):
            os.makedirs(save_folder)
            print(f"   [INFO] 已建立資料夾: {save_folder}")
        
        home_name = lineup['home_team']['name']
        away_name = lineup['away_team']['name']
        
        safe_home = home_name.replace(" ", "_")
        safe_away = away_name.replace(" ", "_")
        filename = f"lineup_{safe_home}_vs_{safe_away}.json"
        full_path = os.path.join(save_folder, filename)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(lineup, f, ensure_ascii=False, indent=4)
        
        print(f"   [已保存] {full_path}")
    
    def get_player_ratings(self, home_team: str, away_team: str, date: str = None) -> Dict:
        """
        獲取球員評分 (用於 ML 模型)
        
        Returns:
            Dict: {
                'home_avg_rating': float,
                'away_avg_rating': float,
                'home_key_players': list,
                'away_key_players': list,
                'lineup_quality_diff': float
            }
        """
        lineup = self.get_lineup(home_team, away_team, date)
        
        if not lineup:
            return {
                'home_avg_rating': 0,
                'away_avg_rating': 0,
                'home_key_players': [],
                'away_key_players': [],
                'lineup_quality_diff': 0,
                'source': 'none'
            }
        
        # 計算平均評分 (如果有評分數據)
        home_starters = lineup.get('home_team', {}).get('starters', [])
        away_starters = lineup.get('away_team', {}).get('starters', [])
        
        # 假設每個位置有基本評分 (實際可從 FotMob API 獲取)
        position_ratings = {
            'Goalkeeper': 6.5,
            'Defender': 6.8,
            'Midfielder': 7.0,
            'Forward': 7.2
        }
        
        def calc_avg_rating(players):
            if not players:
                return 0
            total = sum(position_ratings.get(p.get('position', 'Midfielder'), 6.5) for p in players)
            return round(total / len(players), 2)
        
        home_avg = calc_avg_rating(home_starters)
        away_avg = calc_avg_rating(away_starters)
        
        return {
            'home_avg_rating': home_avg,
            'away_avg_rating': away_avg,
            'home_starters_count': len(home_starters),
            'away_starters_count': len(away_starters),
            'home_formation': lineup.get('home_team', {}).get('formation'),
            'away_formation': lineup.get('away_team', {}).get('formation'),
            'lineup_quality_diff': round(home_avg - away_avg, 2),
            'source': lineup.get('source', 'unknown')
        }


# ========== 便捷函數 ==========

def get_lineup(home_team: str, away_team: str, date: str = None) -> Optional[Dict]:
    """獲取比賽陣容"""
    aggregator = LineupAggregator()
    return aggregator.get_lineup(home_team, away_team, date)


def get_player_ratings(home_team: str, away_team: str, date: str = None) -> Dict:
    """獲取球員評分"""
    aggregator = LineupAggregator()
    return aggregator.get_player_ratings(home_team, away_team, date)


# ========== 測試 ==========

if __name__ == "__main__":
    print("="*60)
    print("測試陣容 API")
    print("="*60)
    
    aggregator = LineupAggregator()
    
    # 測試
    result = aggregator.get_lineup("Liverpool", "Arsenal")
    
    if result:
        print(f"\n✅ 成功獲取陣容!")
        print(f"數據源: {result.get('source')}")
        
        home = result.get('home_team', {})
        away = result.get('away_team', {})
        
        print(f"\n主隊: {home.get('name')} ({home.get('formation')})")
        print(f"  主教練: {home.get('coach')}")
        print(f"  主力球員: {len(home.get('starters', []))} 人")
        
        print(f"\n客隊: {away.get('name')} ({away.get('formation')})")
        print(f"  主教練: {away.get('coach')}")
        print(f"  主力球員: {len(away.get('starters', []))} 人")
        
        # 球員評分
        ratings = aggregator.get_player_ratings("Liverpool", "Arsenal")
        print(f"\n📊 評分分析:")
        print(f"  主隊平均評分: {ratings['home_avg_rating']}")
        print(f"  客隊平均評分: {ratings['away_avg_rating']}")
        print(f"  陣容質量差異: {ratings['lineup_quality_diff']:+.2f}")
    else:
        print("\n❌ 無法獲取陣容")
    
    print("\n" + "="*60)
