# -*- coding: utf-8 -*-
"""
角球預測模型

基於歷史數據預測角球數：
- 使用泊松回歸模型預測角球
- 考慮球隊進攻風格和防守能力
- 支持主客場調整
"""

import numpy as np
import pandas as pd
from scipy.stats import poisson
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


class CornerPredictionModel:
    """
    角球預測模型
    
    基於球隊歷史角球數據和進攻/防守能力預測角球
    """
    
    def __init__(self, decay_rate: float = 0.1, min_games: int = 3):
        """
        Args:
            decay_rate: 指數衰減率
            min_games: 最小比賽數
        """
        self.decay_rate = decay_rate
        self.min_games = min_games
        self.team_data = {}  # {team: {'home': [], 'away': []}}
        self.league_avg = {}  # {league: {'home_corners': avg, 'away_corners': avg}}
        
    def add_match_data(self, league: str, home_team: str, away_team: str,
                      home_corners: int, away_corners: int, 
                      home_attack_strength: float = 1.0, away_attack_strength: float = 1.0,
                      match_date: Optional[str] = None):
        """
        添加比賽角球數據
        
        Args:
            league: 聯賽名稱
            home_team: 主隊
            away_team: 客隊
            home_corners: 主隊角球數
            away_corners: 客隊角球數
            home_attack_strength: 主隊進攻強度 (可選)
            away_attack_strength: 客隊進攻強度 (可選)
            match_date: 比賽日期 (可選)
        """
        # 記錄球隊數據
        if home_team not in self.team_data:
            self.team_data[home_team] = {'home': [], 'away': []}
        if away_team not in self.team_data:
            self.team_data[away_team] = {'home': [], 'away': []}
            
        self.team_data[home_team]['home'].append(home_corners)
        self.team_data[away_team]['away'].append(away_corners)
        
        # 記錄聯賽平均
        if league not in self.league_avg:
            self.league_avg[league] = {'home': [], 'away': []}
        self.league_avg[league]['home'].append(home_corners)
        self.league_avg[league]['away'].append(away_corners)
    
    def _calculate_team_average(self, team: str, is_home: bool, 
                               use_weighted: bool = True) -> float:
        """計算球隊平均角球數"""
        if team not in self.team_data:
            return 5.5  # 默認值
        
        key = 'home' if is_home else 'away'
        corners = self.team_data[team][key]
        
        if len(corners) < self.min_games:
            return 5.5
        
        if use_weighted:
            # 指數衰減加權
            weights = np.exp(-self.decay_rate * np.arange(len(corners))[::-1])
            return np.average(corners, weights=weights)
        else:
            return np.mean(corners)
    
    def _calculate_league_avg(self, league: str, is_home: bool) -> float:
        """計算聯賽平均角球數"""
        if league not in self.league_avg:
            return 5.5
        
        key = 'home' if is_home else 'away'
        corners = self.league_avg[league][key]
        
        if len(corners) < 10:
            return 5.5
        
        return np.mean(corners)
    
    def predict_corners(self, league: str, home_team: str, away_team: str,
                       home_attack: float = 1.0, away_attack: float = 1.0,
                       home_defense: float = 1.0, away_defense: float = 1.0) -> Dict:
        """
        預測角球數
        
        Args:
            league: 聯賽
            home_team: 主隊
            away_team: 客隊
            home_attack: 主隊進攻強度 (相對值)
            away_attack: 客隊進攻強度 (相對值)
            home_defense: 主隊防守強度 (相對值)
            away_defense: 客隊防守強度 (相對值)
            
        Returns:
            Dict:
            - home_corners: 預測主隊角球
            - away_corners: 預測客隊角球
            - total_corners: 預測總角球
            - over_9.5_prob: 大於9.5角球概率
            - under_9.5_prob: 小於9.5角球概率
        """
        # 獲取球隊歷史平均
        home_avg = self._calculate_team_average(home_team, is_home=True)
        away_avg = self._calculate_team_average(away_team, is_home=False)
        
        # 獲取聯賽平均
        league_home_avg = self._calculate_league_avg(league, is_home=True)
        league_away_avg = self._calculate_league_avg(league, is_home=False)
        
        # 計算調整後的預測
        # 球隊表現相對於聯賽平均的調整
        home_adjustment = (home_avg / league_home_avg) if league_home_avg > 0 else 1.0
        away_adjustment = (away_avg / league_away_avg) if league_away_avg > 0 else 1.0
        
        # 結合進攻和防守因素
        # 強進攻 -> 更多角球
        # 強防守 -> 對手更多角球
        
        predicted_home = league_home_avg * home_adjustment * (
            0.5 * home_attack + 0.5 * away_defense
        )
        
        predicted_away = league_away_avg * away_adjustment * (
            0.5 * away_attack + 0.5 * home_defense
        )
        
        # 確保預測值在合理範圍內
        predicted_home = max(1, min(15, predicted_home))
        predicted_away = max(1, min(15, predicted_away))
        
        # 計算大小角球概率 (使用泊松分布)
        total_corners = predicted_home + predicted_away
        
        home_poisson = poisson(predicted_home)
        away_poisson = poisson(predicted_away)
        
        # Over 9.5 概率
        over_prob = 1 - poisson.cdf(9, total_corners)
        
        return {
            'home_corners': round(predicted_home, 1),
            'away_corners': round(predicted_away, 1),
            'total_corners': round(total_corners, 1),
            'over_9.5_prob': round(over_prob, 3),
            'under_9.5_prob': round(1 - over_prob, 3),
            'over_10.5_prob': round(1 - poisson.cdf(10, total_corners), 3),
            'under_10.5_prob': round(poisson.cdf(10, total_corners), 3),
        }
    
    def get_team_corners_stats(self, team: str) -> Dict:
        """獲取球隊角球統計"""
        if team not in self.team_data:
            return {'avg_home': 5.5, 'avg_away': 5.5, 'total_games': 0}
        
        home_data = self.team_data[team]['home']
        away_data = self.team_data[team]['away']
        
        return {
            'avg_home': round(np.mean(home_data), 2) if home_data else 5.5,
            'avg_away': round(np.mean(away_data), 2) if away_data else 5.5,
            'total_games': len(home_data) + len(away_data),
            'max_home': max(home_data) if home_data else 0,
            'max_away': max(away_data) if away_data else 0,
        }


class CornerValueBetModel:
    """
    角球價值投注模型
    
    識別博彩公司開出的角球盤口中可能的價值
    """
    
    def __init__(self, corner_model: CornerPredictionModel):
        self.corner_model = corner_model
        self.best_line_history = []  # 記錄最佳線
        
    def find_value_bets(self, league: str, home_team: str, away_team: str,
                       bookie_line: float, bookie_odds_over: float,
                       bookie_odds_under: float,
                       home_attack: float = 1.0, away_attack: float = 1.0,
                       home_defense: float = 1.0, away_defense: float = 1.0) -> Dict:
        """
        尋找價值投注
        
        Args:
            bookie_line: 博彩公司開出的角球盤口
            bookie_odds_over: 大於盤口的赔率
            bookie_odds_under: 小於盤口的赔率
            
        Returns:
            Dict:
            - has_value: 是否有價值
            - over_edge: 大於的優勢
            - under_edge: 小於的優勢
            - recommended: 建議 ('over', 'under', 'none')
        """
        prediction = self.corner_model.predict_corners(
            league, home_team, away_team,
            home_attack, away_attack, home_defense, away_defense
        )
        
        # 計算模型預期的概率
        total = prediction['total_corners']
        
        # 使用泊松分布計算真實概率
        true_prob_over = 1 - poisson.cdf(bookie_line - 0.5, total)
        true_prob_under = poisson.cdf(bookie_line - 0.5, total)
        
        # 轉換赔率為概率
        implied_prob_over = 1 / bookie_odds_over if bookie_odds_over > 0 else 0
        implied_prob_under = 1 / bookie_odds_under if bookie_odds_under > 0 else 0
        
        # 計算優勢 (edge)
        over_edge = true_prob_over - implied_prob_over
        under_edge = true_prob_under - implied_prob_under
        
        # 判斷是否有價值 (假設5%門檻)
        threshold = 0.05
        
        if over_edge > threshold:
            recommended = 'over'
            has_value = True
        elif under_edge > threshold:
            recommended = 'under'
            has_value = True
        else:
            recommended = 'none'
            has_value = False
        
        return {
            'has_value': has_value,
            'recommended': recommended,
            'over_edge': round(over_edge, 4),
            'under_edge': round(under_edge, 4),
            'model_total': prediction['total_corners'],
            'bookie_line': bookie_line,
            'true_prob_over': round(true_prob_over, 4),
            'true_prob_under': round(true_prob_under, 4),
            'implied_prob_over': round(implied_prob_over, 4),
            'implied_prob_under': round(implied_prob_under, 4),
        }


# ============================================================
# 測試
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("角球預測模型測試")
    print("=" * 60)
    
    # 創建模型
    model = CornerPredictionModel(decay_rate=0.1)
    
    # 添加一些測試數據
    test_matches = [
        ('Premier League', 'Arsenal', 'Chelsea', 7, 3),
        ('Premier League', 'Arsenal', 'Chelsea', 5, 4),
        ('Premier League', 'Arsenal', 'Chelsea', 8, 2),
        ('Premier League', 'Man City', 'Liverpool', 6, 5),
        ('Premier League', 'Man City', 'Liverpool', 9, 1),
    ]
    
    for league, home, away, hc, ac in test_matches:
        model.add_match_data(league, home, away, hc, ac)
    
    # 測試預測
    prediction = model.predict_corners(
        league='Premier League',
        home_team='Arsenal',
        away_team='Chelsea',
        home_attack=1.2,  # 強進攻
        away_attack=0.8,  # 弱進攻
        home_defense=1.1, # 強防守
        away_defense=0.9  # 弱防守
    )
    
    print("\n角球預測結果:")
    print(f"  主隊角球: {prediction['home_corners']}")
    print(f"  客隊角球: {prediction['away_corners']}")
    print(f"  總角球: {prediction['total_corners']}")
    print(f"  大9.5概率: {prediction['over_9.5_prob']}")
    print(f"  小9.5概率: {prediction['under_9.5_prob']}")
    
    # 測試球隊統計
    stats = model.get_team_corners_stats('Arsenal')
    print("\n阿森納角球統計:")
    print(f"  主場平均: {stats['avg_home']}")
    print(f"  客場平均: {stats['avg_away']}")
    print(f"  總場次: {stats['total_games']}")
