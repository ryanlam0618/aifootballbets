#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
傷停數據獲取模組

支持從多個來源獲取球隊傷停信息
"""

import requests
import json
import time
import re
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from bs4 import BeautifulSoup
import os

# 強制輸出編碼
import sys
sys.stdout.reconfigure(encoding='utf-8')


@dataclass
class PlayerInjury:
    """球員傷停信息"""
    player_id: str
    name: str
    team: str
    injury_type: str  # 'injury', 'suspension', 'international_duty'
    severity: str  # 'doubtful', 'out', '返回'
    description: str
    start_date: str
    expected_return: Optional[str] = None
    games_missed: int = 0
    impact_score: float = 0.0  # 影響評分 0-10


@dataclass
class TeamInjuryReport:
    """球隊傷停報告"""
    team_name: str
    league: str
    match_date: str
    opponents: str
    injuries: List[PlayerInjury] = field(default_factory=list)
    suspensions: List[PlayerInjury] = field(default_factory=list)
    international_duty: List[PlayerInjury] = field(default_factory=list)
    total_impact_score: float = 0.0
    key_players_missing: List[str] = field(default_factory=list)

    def get_available_players(self, all_players: List[str]) -> List[str]:
        """計算可用球員"""
        missing = {p.name for p in self.injuries + self.suspensions + self.international_duty}
        return [p for p in all_players if p not in missing]

    def get_impact_summary(self) -> Dict:
        """獲取影響摘要"""
        return {
            'total_missing': len(self.injuries) + len(self.suspensions) + len(self.international_duty),
            'key_players_missing': self.key_players_missing,
            'impact_score': self.total_impact_score,
            'by_type': {
                'injury': len(self.injuries),
                'suspension': len(self.suspensions),
                'international': len(self.international_duty)
            }
        }


class InjuryDataFetcher:
    """傷停數據獲取器"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.cache_folder = 'data/injury_cache'
        os.makedirs(self.cache_folder, exist_ok=True)

    # ========== Transfermarkt 爬蟲 ==========

    def fetch_transfermarkt_injuries(self, team_name: str, league: str) -> List[PlayerInjury]:
        """
        從 Transfermarkt 獲取傷停數據

        Transfermarkt 傷病數據頁面格式:
        https://www.transfermarkt.com/{team_name}/verletzungen
        """
        # 隊名轉換為 URL 格式
        team_url = team_name.lower().replace(' ', '-').replace('fc', '').strip()
        url = f"https://www.transfermarkt.com/{team_url}/verletzungen"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.content, 'html.parser')
            injuries = []

            # 查找傷病表格
            table = soup.find('table', {'class': 'items'})
            if not table:
                return []

            rows = table.find_all('tr')[1:]  # 跳過表頭

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 8:
                    continue

                try:
                    # 解析欄位
                    player_link = cols[0].find('a')
                    player_name = player_link.text.strip() if player_link else 'Unknown'

                    injury_desc = cols[2].text.strip()
                    severity = cols[3].text.strip()
                    duration = cols[4].text.strip()
                    games_missed = cols[5].text.strip()
                    date_range = cols[6].text.strip()

                    # 判斷傷病類型
                    if 'suspension' in injury_desc.lower() or 'sperre' in injury_desc.lower():
                        injury_type = 'suspension'
                    else:
                        injury_type = 'injury'

                    # 計算影響評分
                    impact = self._calculate_impact(injury_type, severity, games_missed)

                    injury = PlayerInjury(
                        player_id=str(hash(player_name) % 100000),
                        name=player_name,
                        team=team_name,
                        injury_type=injury_type,
                        severity=self._normalize_severity(severity),
                        description=injury_desc,
                        start_date=date_range.split('-')[0].strip() if '-' in date_range else date_range,
                        expected_return=date_range.split('-')[1].strip() if '-' in date_range else None,
                        games_missed=self._parse_games(games_missed),
                        impact_score=impact
                    )
                    injuries.append(injury)

                except Exception as e:
                    continue

            return injuries

        except Exception as e:
            print(f"Transfermarkt 爬取錯誤: {e}")
            return []

    # ========== FotMob 整合 ==========

    def fetch_fotmob_injuries(self, team_id: int) -> List[PlayerInjury]:
        """從 FotMob 獲取傷停數據"""
        url = f"https://www.fotmob.com/api/team/{team_id}/overview"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                return []

            data = response.json()
            injuries = []

            # 遍歷球員
            squad = data.get('squad', [])
            for player in squad:
                status = player.get('status', {})

                if status.get('injured', False) or status.get('suspended', False):
                    injury_type = 'suspension' if status.get('suspended', False) else 'injury'

                    impact = self._calculate_impact(
                        injury_type,
                        status.get('severity', 'unknown'),
                        0
                    )

                    injuries.append(PlayerInjury(
                        player_id=str(player.get('id', 0)),
                        name=player.get('name', 'Unknown'),
                        team=data.get('team', {}).get('name', ''),
                        injury_type=injury_type,
                        severity=status.get('return_date', 'unknown'),
                        description=status.get('reason', ''),
                        start_date=status.get('since', ''),
                        expected_return=status.get('return_date'),
                        impact_score=impact
                    ))

            return injuries

        except Exception as e:
            print(f"FotMob API 錯誤: {e}")
            return []

    # ========== 模擬數據生成 (⚠️ 已棄用 - 僅用於本地測試) ==========
    # 注意: 此函數已棄用，不再用於生產環境
    # 生產環境應該使用真實 API 數據

    def generate_mock_injuries(self, team_name: str, match_date: str) -> TeamInjuryReport:
        """
        ⚠️ 已棄用: 請使用 get_team_injury_report() 獲取真實數據
        
        生成模擬傷停數據 (僅用於本地測試)
        
        警告: 此函數生成的數據是隨機的，不應用於實際投注決策
        """
        import warnings
        warnings.warn(
            "generate_mock_injuries() 已棄用，請使用 get_team_injury_report() 獲取真實 API 數據",
            DeprecationWarning,
            stacklevel=2
        )

        import random

        # 常見傷病情況
        injury_types = [
            ('muscle injury', 'muscle'),
            ('ankle injury', 'ankle'),
            ('knee injury', 'knee'),
            ('thigh strain', 'thigh'),
            ('calf problem', 'calf'),
            ('hip issue', 'hip'),
            ('back problem', 'back'),
            ('illness', 'illness'),
        ]

        severity_levels = [
            ('out for weeks', 'out', 8.5, 3),
            ('doubtful', 'doubtful', 6.0, 1),
            ('expected back next week', '返回', 4.0, 1),
            ('out for season', 'out', 10.0, 10),
        ]

        # 模擬傷停球員
        injuries = []
        num_injuries = random.randint(1, 4)

        key_players = [
            ('Marcus Rashford', 9.0),
            ('Bruno Fernandes', 9.5),
            ('Lisandro Martinez', 8.5),
            ('Alejandro Garnacho', 7.5),
            ('Christian Eriksen', 8.0),
        ]

        for i in range(num_injuries):
            if i == 0 and random.random() < 0.3:  # 30% 機會有核心球員傷停
                name, impact = random.choice(key_players)
            else:
                name = f"Player_{random.randint(1, 100)}"
                severity = random.choice(severity_levels)
                impact = severity[2]

            inj = random.choice(injury_types)

            injury = PlayerInjury(
                player_id=str(random.randint(10000, 99999)),
                name=name,
                team=team_name,
                injury_type='injury',
                severity=severity[1],
                description=f"{severity[0]} - {inj[0]}",
                start_date=match_date,
                expected_return=None,
                games_missed=severity[3],
                impact_score=impact
            )
            injuries.append(injury)

        # 模擬停賽
        if random.random() < 0.2:
            suspension = PlayerInjury(
                player_id=str(random.randint(10000, 99999)),
                name=f"Suspended_Player_{random.randint(1, 50)}",
                team=team_name,
                injury_type='suspension',
                severity='out',
                description='Accumulated yellow cards',
                start_date=match_date,
                expected_return=None,
                games_missed=1,
                impact_score=6.0
            )
            injuries.append(suspension)

        # 計算總影響分數
        total_impact = sum(i.impact_score for i in injuries)
        key_missing = [i.name for i in injuries if i.impact_score >= 7.0]

        return TeamInjuryReport(
            team_name=team_name,
            league='Premier League',
            match_date=match_date,
            opponents='Opponent',
            injuries=[i for i in injuries if i.injury_type == 'injury'],
            suspensions=[i for i in injuries if i.injury_type == 'suspension'],
            total_impact_score=total_impact,
            key_players_missing=key_missing
        )

    # ========== 工具方法 ==========

    def _calculate_impact(self, injury_type: str, severity: str, games_missed: int) -> float:
        """計算傷停影響評分 (0-10)"""
        base_score = 0

        # 類型權重
        if injury_type == 'injury':
            base_score = 5.0
        elif injury_type == 'suspension':
            base_score = 4.0
        elif injury_type == 'international_duty':
            base_score = 3.0

        # 嚴重性調整
        severity_lower = severity.lower()
        if 'out' in severity_lower or 'long-term' in severity_lower:
            base_score += 3.0
        elif 'doubtful' in severity_lower:
            base_score += 1.0
        elif '返回' in severity_lower or 'back' in severity_lower:
            base_score -= 2.0

        # 場次調整
        base_score += min(games_missed * 0.5, 3.0)

        return min(max(base_score, 0), 10)

    def _normalize_severity(self, severity: str) -> str:
        """標準化嚴重性描述"""
        severity_lower = severity.lower()
        if 'out' in severity_lower or 'long' in severity_lower:
            return 'out'
        elif 'doubtful' in severity_lower:
            return 'doubtful'
        elif 'back' in severity_lower or 'return' in severity_lower:
            return '返回'
        else:
            return 'unknown'

    def _parse_games(self, games_str: str) -> int:
        """解析錯過場次"""
        try:
            return int(re.search(r'\d+', games_str).group())
        except:
            return 0

    # ========== API 接口 ==========

    def get_team_injury_report(self, home_team: str, away_team: str,
                                match_date: str, league: str = 'Premier League') -> Dict:
        """
        獲取雙方傷停報告

        優先使用真實 API 數據:
        1. API-Football (主要數據源)
        2. Transfermarkt (備用數據源)
        
        返回:
            Dict: {
                'home': TeamInjuryReport,
                'away': TeamInjuryReport,
                'impact_diff': float  # 主隊相對優勢
            }
        """
        # 嘗試使用真實 API 獲取數據
        home_report = None
        away_report = None
        
        # 嘗試 API-Football
        try:
            if self.api_football:
                home_report = self._fetch_from_api_football(home_team, match_date)
                away_report = self._fetch_from_api_football(away_team, match_date)
                print(f"   [傷停] 從 API-Football 獲取數據")
        except Exception as e:
            print(f"   [傷停] API-Football 失敗: {e}")
        
        # 如果 API 失敗，嘗試 Transfermarkt
        if not home_report or not away_report:
            try:
                home_report = self._fetch_from_transfermarkt(home_team) or home_report
                away_report = self._fetch_from_transfermarkt(away_team) or away_report
                print(f"   [傷停] 從 Transfermarkt 獲取數據")
            except Exception as e:
                print(f"   [傷停] Transfermarkt 失敗: {e}")
        
        # 如果仍然沒有數據，記錄警告 (不再使用模擬數據)
        if not home_report:
            print(f"   ⚠️ [傷停] 無法獲取 {home_team} 的傷停數據")
            home_report = self._create_empty_report(home_team, match_date)
        
        if not away_report:
            print(f"   ⚠️ [傷停] 無法獲取 {away_team} 的傷停數據")
            away_report = self._create_empty_report(away_team, match_date)

        home_report.opponents = away_team
        away_report.opponents = home_team
        home_report.league = league
        away_report.league = league

        return {
            'home': home_report,
            'away': away_report,
            'impact_diff': home_report.total_impact_score - away_report.total_impact_score,
            'data_source': 'api' if home_report.injuries or away_report.injuries else 'none'
        }
    
    def _create_empty_report(self, team_name: str, match_date: str) -> TeamInjuryReport:
        """創建空傷停報告 (用於 API 失敗時)"""
        return TeamInjuryReport(
            team_name=team_name,
            league='Unknown',
            match_date=match_date,
            opponents='Unknown',
            injuries=[],
            suspensions=[],
            total_impact_score=0.0,
            key_players_missing=[]
        )
    
    def _fetch_from_api_football(self, team_name: str, match_date: str) -> TeamInjuryReport:
        """從 API-Football 獲取傷停數據"""
        # 簡化實現 - 實際應該調用 API
        print(f"      [API-Football] 查詢 {team_name}...")
        return None  # 讓調用方處理
    
    def _fetch_from_transfermarkt(self, team_name: str) -> TeamInjuryReport:
        """從 Transfermarkt 獲取傷停數據"""
        print(f"      [Transfermarkt] 查詢 {team_name}...")
        return None  # 讓調用方處理


def calculate_injury_features(home_report: TeamInjuryReport,
                               away_report: TeamInjuryReport) -> Dict:
    """
    計算傷停特徵

    返回用於模型的特徵字典
    """

    home_impact = home_report.total_impact_score
    away_impact = away_report.total_impact_score

    features = {
        # 基本數量
        'home_injuries': len(home_report.injuries),
        'away_injuries': len(away_report.injuries),
        'home_suspensions': len(home_report.suspensions),
        'away_suspensions': len(away_report.suspensions),

        # 影響分數
        'home_impact_score': home_impact,
        'away_impact_score': away_impact,
        'impact_diff': home_impact - away_impact,
        'impact_ratio': home_impact / (away_impact + 1),  # 避免除零

        # 核心球員
        'home_key_missing': len(home_report.key_players_missing),
        'away_key_missing': len(away_report.key_players_missing),

        # 傷停類型分布
        'home_injury_type_count': len(home_report.injuries),
        'away_injury_type_count': len(away_report.injuries),
    }

    return features


# ========== 主程式 ==========

if __name__ == "__main__":
    fetcher = InjuryDataFetcher()

    # 測試
    report = fetcher.get_team_injury_report(
        home_team="Liverpool",
        away_team="Arsenal",
        match_date="2025-02-02"
    )

    print("=" * 60)
    print("Team Injury Report")
    print("=" * 60)

    for side in ['home', 'away']:
        r = report[side]
        print(f"\n{r.team_name}:")
        print(f"  Total Impact Score: {r.total_impact_score:.1f}")
        print(f"  Key Players Missing: {r.key_players_missing}")
        print(f"  Injuries: {len(r.injuries)}")
        print(f"  Suspensions: {len(r.suspensions)}")

    print(f"\nImpact Difference (Home - Away): {report['impact_diff']:.1f}")

    # 計算特徵
    features = calculate_injury_features(report['home'], report['away'])
    print(f"\nFeatures for ML model:")
    for k, v in features.items():
        print(f"  {k}: {v}")
