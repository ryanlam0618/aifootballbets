#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
數學模型升級版 v3
包含：
1. 負二項分布 (Negative Binomial Distribution) - 處理過離散數據
2. 動態K因子 Elo/Glicko-2 - 自適應評分
3. 信心度 Kelly 資金管理 - 根據模型信心調整
4. Stacking 集成學習 - 多模型融合
"""

import math
import numpy as np
import pandas as pd
from scipy.stats import poisson, nbinom, norm, beta
from scipy.optimize import minimize, differential_evolution
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable
from abc import ABC, abstractmethod
import warnings
warnings.filterwarnings('ignore')

# ============================================
# 第一部分：進球預測模型
# ============================================

class BaseGoalModel(ABC):
    """進球預測模型基類"""
    
    @abstractmethod
    def calculate_probabilities(self) -> Dict[str, float]:
        pass
    
    @abstractmethod
    def expected_goals(self) -> Tuple[float, float]:
        pass


class PoissonModel(BaseGoalModel):
    """
    標準 Poisson 進球模型
    
    優點：簡單、計算快
    缺點：假設均值=方差，實際足球進球存在過離散
    """
    
    def __init__(self, home_expect: float, away_expect: float):
        self.mu_h = home_expect
        self.mu_a = away_expect
        
    def expected_goals(self) -> Tuple[float, float]:
        return self.mu_h, self.mu_a
    
    def calculate_probabilities(self) -> Dict[str, float]:
        """計算主勝/和/客勝概率"""
        prob_home, prob_draw, prob_away = 0, 0, 0
        
        for h in range(15):
            for a in range(15):
                p = poisson.pmf(h, self.mu_h) * poisson.pmf(a, self.mu_a)
                if h > a:
                    prob_home += p
                elif h == a:
                    prob_draw += p
                else:
                    prob_away += p
        
        total = prob_home + prob_draw + prob_away
        return {
            "home_win": prob_home / total if total > 0 else 0,
            "draw": prob_draw / total if total > 0 else 0,
            "away_win": prob_away / total if total > 0 else 0,
            "model": "Poisson"
        }
    
    def score_distribution(self, team: str = 'home') -> Dict[int, float]:
        """返回進球數分布"""
        mu = self.mu_h if team == 'home' else self.mu_a
        return {i: poisson.pmf(i, mu) for i in range(10)}
    
    def over_under_prob(self, line: float = 2.5) -> Dict[str, float]:
        """大小球概率"""
        over_prob = sum(
            poisson.sf(max(0, int(line)), self.mu_h + self.mu_a)
        )
        return {"over_2.5": over_prob, "under_2.5": 1 - over_prob}


class NegativeBinomialModel(BaseGoalModel):
    """
    負二項分布進球模型 v3
    
    解決Poisson的過離散問題：
    - 足球進球的方差通常 > 均值
    - 負二項分布通過離散參數(alpha)捕捉這種變異
    
    P(X=k) = C(n+k-1, k) * p^n * (1-p)^k
    其中 n = mu/alpha, p = 1/(1+alpha)
    """
    
    def __init__(self, home_expect: float, away_expect: float, 
                 dispersion: float = 1.5,
                 calibrate_dispersion: bool = True):
        """
        Args:
            home_expect: 主隊預期進球
            away_expect: 客隊預期進球
            dispersion: 離散參數 (alpha > 0)
                        alpha = 1: 接近Poisson
                        alpha > 1: 過離散 (實際足球數據通常 alpha=1.2-2.0)
                calibrate_dispersion: 是否自動校準離散參數
        """
        self.mu_h = home_expect
        self.mu_a = away_expect
        self.alpha = dispersion
        self.calibrate = calibrate_dispersion
        
        # 如果需要校準，會在calculate_probabilities時自動調用
        self._fitted_alpha = dispersion
        
    def _calculate_nbinom_params(self, mu: float, alpha: float) -> Tuple[float, float]:
        """轉換為scipy參數格式"""
        n = mu / alpha  # 失敗次數參數
        p = 1 / (1 + alpha)  # 成功概率
        return n, p
    
    def _estimate_dispersion(self, goals: np.ndarray, mu: float) -> float:
        """
        使用矩估計法估計離散參數
        
        Var(X) = mu + alpha * mu^2
        => alpha = (Var - mu) / mu^2
        """
        var = np.var(goals)
        if var <= mu:
            return 0.1  # 接近Poisson
        
        alpha = (var - mu) / (mu ** 2)
        return max(0.1, min(3.0, alpha))  # 限制在合理範圍
    
    def expected_goals(self) -> Tuple[float, float]:
        return self.mu_h, self.mu_a
    
    def calculate_probabilities(self, historical_goals: Optional[np.ndarray] = None) -> Dict[str, float]:
        """
        計算主勝/和/客勝概率
        """
        # 如果有歷史數據，校準離散參數
        if self.calibrate and historical_goals is not None:
            self._fitted_alpha = self._estimate_dispersion(historical_goals, self.mu_h)
        else:
            self._fitted_alpha = self.alpha
            
        prob_home, prob_draw, prob_away = 0, 0, 0
        
        n_h, p_h = self._calculate_nbinom_params(self.mu_h, self._fitted_alpha)
        n_a, p_a = self._calculate_nbinom_params(self.mu_a, self._fitted_alpha)
        
        for h in range(15):
            for a in range(15):
                p = nbinom.pmf(h, n_h, p_h) * nbinom.pmf(a, n_a, p_a)
                if h > a:
                    prob_home += p
                elif h == a:
                    prob_draw += p
                else:
                    prob_away += p
        
        total = prob_home + prob_draw + prob_away
        
        return {
            "home_win": prob_home / total if total > 0 else 0,
            "draw": prob_draw / total if total > 0 else 0,
            "away_win": prob_away / total if total > 0 else 0,
            "model": "NegativeBinomial",
            "dispersion": self._fitted_alpha,
            "overdispersion": self._fitted_alpha > 0.3  # 標記是否顯著過離散
        }
    
    def score_distribution(self, team: str = 'home') -> Dict[int, float]:
        """返回進球數分布"""
        mu = self.mu_h if team == 'home' else self.mu_a
        n, p = self._calculate_nbinom_params(mu, self._fitted_alpha)
        return {i: nbinom.pmf(i, n, p) for i in range(10)}
    
    def variance_ratio(self) -> Dict[str, float]:
        """計算方差比，診斷過離散程度"""
        var_h = self.mu_h + self._fitted_alpha * (self.mu_h ** 2)
        var_a = self.mu_a + self._fitted_alpha * (self.mu_a ** 2)
        return {
            "home_var_mean_ratio": var_h / self.mu_h,
            "away_var_mean_ratio": var_a / self.mu_a,
            "overdispersed": var_h > self.mu_h * 1.5
        }


class DixonColesModel(BaseGoalModel):
    """
    Dixon-Coles 模型 v3
    
    核心改進：引入 ρ (rho) 參數修正低比分相關性
    τ(x,y) 校正系數：
    - 0-0 比分: 1 - μh × μa × ρ
    - 1-1 比分: 1 - ρ
    - 0-1, 1-0 比分: 1 + μ × ρ
    """
    
    def __init__(self, home_expect: float, away_expect: float, rho: float = -0.13):
        self.mu_h = home_expect
        self.mu_a = away_expect
        self.rho = rho
        
    def tau_correction(self, x: int, y: int) -> float:
        """Dixon-Coles τ校正"""
        if x == 0 and y == 0:
            return 1 - (self.mu_h * self.mu_a * self.rho)
        elif x == 0 and y == 1:
            return 1 + (self.mu_h * self.rho)
        elif x == 1 and y == 0:
            return 1 + (self.mu_a * self.rho)
        elif x == 1 and y == 1:
            return 1 - self.rho
        else:
            return 1.0
    
    def expected_goals(self) -> Tuple[float, float]:
        return self.mu_h, self.mu_a
    
    def calculate_probabilities(self) -> Dict[str, float]:
        prob_home, prob_draw, prob_away = 0, 0, 0
        
        for h in range(15):
            for a in range(15):
                base = poisson.pmf(h, self.mu_h) * poisson.pmf(a, self.mu_a)
                correction = self.tau_correction(h, a)
                final = base * correction
                
                if h > a:
                    prob_home += final
                elif h == a:
                    prob_draw += final
                else:
                    prob_away += final
        
        total = prob_home + prob_draw + prob_away
        
        return {
            "home_win": prob_home / total if total > 0 else 0,
            "draw": prob_draw / total if total > 0 else 0,
            "away_win": prob_away / total if total > 0 else 0,
            "model": "DixonColes",
            "rho": self.rho
        }


class OptimizedNegativeBinomialDC(BaseGoalModel):
    """
    負二項分布 + Dixon-Coles 校正
    結合兩種方法的优势
    """
    
    def __init__(self, home_expect: float, away_expect: float, 
                 dispersion: float = 1.5, rho: float = -0.13):
        self.mu_h = home_expect
        self.mu_a = away_expect
        self.alpha = dispersion
        self.rho = rho
        
    def _nbinom_params(self, mu: float, alpha: float) -> Tuple[float, float]:
        n = mu / alpha
        p = 1 / (1 + alpha)
        return n, p
    
    def tau_correction(self, x: int, y: int) -> float:
        """增強版τ校正"""
        if x == 0 and y == 0:
            return 1 - (self.mu_h * self.mu_a * self.rho * 0.8)
        elif x == 0 and y == 1:
            return 1 + (self.mu_h * self.rho * 0.5)
        elif x == 1 and y == 0:
            return 1 + (self.mu_a * self.rho * 0.5)
        elif x == 1 and y == 1:
            return 1 - (self.rho * 0.6)
        else:
            return 1.0
    
    def expected_goals(self) -> Tuple[float, float]:
        return self.mu_h, self.mu_a
    
    def calculate_probabilities(self) -> Dict[str, float]:
        prob_home, prob_draw, prob_away = 0, 0, 0
        
        n_h, p_h = self._nbinom_params(self.mu_h, self.alpha)
        n_a, p_a = self._nbinom_params(self.mu_a, self.alpha)
        
        for h in range(15):
            for a in range(15):
                base = nbinom.pmf(h, n_h, p_h) * nbinom.pmf(a, n_a, p_a)
                correction = self.tau_correction(h, a)
                final = base * correction
                
                if h > a:
                    prob_home += final
                elif h == a:
                    prob_draw += final
                else:
                    prob_away += final
        
        total = prob_home + prob_draw + prob_away
        
        return {
            "home_win": prob_home / total if total > 0 else 0,
            "draw": prob_draw / total if total > 0 else 0,
            "away_win": prob_away / total if total > 0 else 0,
            "model": "NegBinom-DC",
            "dispersion": self.alpha,
            "rho": self.rho
        }


# ============================================
# 第二部分：評分系統升級
# ============================================

class BaseRatingSystem(ABC):
    """評分系統基類"""
    
    @abstractmethod
    def get_rating(self, team: str) -> float:
        pass
    
    @abstractmethod
    def expected_score(self, rating_a: float, rating_b: float) -> float:
        pass
    
    @abstractmethod
    def update_ratings(self, home: str, away: str, h_goals: int, a_goals: int):
        pass


class DynamicKEloSystem(BaseRatingSystem):
    """
    動態K因子 Elo 評分系統 v3
    
    創新點：
    1. 根據對手實力調整K值
    2. 根據比賽結果意外程度調整K值
    3. 主場優勢動態權重
    4. 比賽重要性係數
    """
    
    def __init__(self, base_k: float = 20, home_advantage: float = 100):
        self.base_k = base_k
        self.home_advantage = home_advantage
        self.ratings = {}
        self.rating_history = {}  # 用於追蹤變化
        
    def get_rating(self, team: str) -> float:
        return self.ratings.get(team, 1500)
    
    def _calculate_dynamic_k(self, team: str, opponent: str, 
                            h_goals: int, a_goals: int, 
                            is_home: bool) -> float:
        """
        計算動態K值
        
        K = K_base × F_opponent × F_upset × F_importance × F_home
        """
        k = self.base_k
        
        # 1. 對手實力因子 (面對強隊時K值更大)
        opp_rating = self.get_rating(opponent)
        rating_diff = abs(self.get_rating(team) - opp_rating)
        f_opponent = 1 + (rating_diff / 2000)  # ±50% 範圍
        
        # 2. 意外因子 (結果越意外，K值越小，避免過度反應)
        expected = self.expected_score(
            self.get_rating(team) + (self.home_advantage if is_home else 0),
            self.get_rating(opponent) + (self.home_advantage if not is_home else 0)
        )
        actual = 1 if (is_home and h_goals > a_goals) or (not is_home and a_goals > h_goals) else (0.5 if h_goals == a_goals else 0)
        surprise = abs(actual - expected)
        f_upset = 1 - (surprise * 0.4)  # 最大調整 ±40%
        
        # 3. 主場因子
        f_home = 1.1 if is_home else 1.0
        
        # 4. 比賽重要性 (可用於杯賽決賽等)
        # 預設為1.0，可通過外部配置提高
        f_importance = 1.0
        
        return k * f_opponent * f_upset * f_home * f_importance
    
    def expected_score(self, rating_a: float, rating_b: float) -> float:
        """Elo期望分數公式"""
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    
    def update_ratings(self, home: str, away: str, h_goals: int, a_goals: int,
                       xg_home: Optional[float] = None, xg_away: Optional[float] = None):
        """更新評分"""
        if h_goals > a_goals:
            result_h, result_a = 1, 0
        elif h_goals == a_goals:
            result_h, result_a = 0.5, 0.5
        else:
            result_h, result_a = 0, 1
        
        # 計算動態K值
        k_h = self._calculate_dynamic_k(home, away, h_goals, a_goals, True)
        k_a = self._calculate_dynamic_k(away, home, a_goals, h_goals, False)
        
        r_h = self.get_rating(home)
        r_a = self.get_rating(away)
        
        expected_h = self.expected_score(r_h + self.home_advantage, r_a)
        expected_a = self.expected_score(r_a, r_h + self.home_advantage)
        
        # xG加權調整 (如果可用)
        if xg_home is not None and xg_away is not None:
            # 計算表現係數
            perf_h = (xg_home - xg_away) - (h_goals - a_goals)
            perf_a = -perf_h
            # 輕微調整結果
            result_h = max(0, min(1, result_h - perf_h * 0.1))
            result_a = max(0, min(1, result_a - perf_a * 0.1))
        
        self.ratings[home] = r_h + k_h * (result_h - expected_h)
        self.ratings[away] = r_a + k_a * (result_a - expected_a)
        
        # 記錄歷史
        if home not in self.rating_history:
            self.rating_history[home] = []
        if away not in self.rating_history:
            self.rating_history[away] = []
            
        self.rating_history[home].append({
            'date': pd.Timestamp.now(),
            'rating': self.ratings[home],
            'k': k_h
        })
        self.rating_history[away].append({
            'date': pd.Timestamp.now(),
            'rating': self.ratings[away],
            'k': k_a
        })
    
    def expected_win_prob(self, home: str, away: str) -> float:
        """計算主隊預期勝率"""
        r_h = self.get_rating(home)
        r_a = self.get_rating(away)
        return self.expected_score(r_h + self.home_advantage, r_a)
    
    def get_league_strength(self) -> pd.DataFrame:
        """返回聯賽球隊實力排名"""
        if not self.ratings:
            return pd.DataFrame()
        
        df = pd.DataFrame([
            {'team': team, 'rating': rating}
            for team, rating in self.ratings.items()
        ])
        return df.sort_values('rating', ascending=False)


class DynamicGlicko2System:
    """
    動態 Glicko-2 評分系統 v3
    
    改進點：
    1. 動態τ參數 (系統波動性)
    2. 根據比賽質量調整RD
    3. 批量更新支持
    """
    
    def __init__(self, tau: float = 0.5, base_rating: float = 1500, 
                 base_rd: float = 350, base_vol: float = 0.06):
        self.tau = tau
        self.base_rating = base_rating
        self.base_rd = base_rd
        self.base_vol = base_vol
        self.ratings = {}
        
    def get_rating(self, team: str) -> Dict[str, float]:
        if team not in self.ratings:
            self.ratings[team] = {
                'rating': self.base_rating,
                'rd': self.base_rd,
                'vol': self.base_vol
            }
        return self.ratings[team]
    
    def _g(self, phi: float) -> float:
        """Glicko-2 g函數"""
        return 1 / math.sqrt(1 + 3 * (phi ** 2) / (math.pi ** 2))
    
    def _E(self, mu: float, mu_j: float, phi_j: float) -> float:
        """E函數"""
        return 1 / (1 + math.exp(-self._g(phi_j) * (mu - mu_j)))
    
    def _scale_down(self, r: float, rd: float) -> Tuple[float, float]:
        return (r - 1500) / 173.7178, rd / 173.7178
    
    def _scale_up(self, mu: float, phi: float) -> Tuple[float, float]:
        return 173.7178 * mu + 1500, 173.7178 * phi
    
    def _calculate_dynamic_tau(self, team: str, opponent: str) -> float:
        """
        動態τ計算
        
        τ基於：
        1. 對手實力差異
        2. 球隊近期表現波動
        """
        opp = self.get_rating(opponent)
        team_data = self.get_rating(team)
        
        # 實力差距越大，τ越大（不確定性增加）
        rating_diff = abs(team_data['rating'] - opp['rating']) / 500
        dynamic_tau = self.tau * (1 + rating_diff * 0.3)
        
        return min(max(dynamic_tau, 0.2), 1.0)  # 限制範圍
    
    def update_ratings(self, home: str, away: str, h_goals: int, a_goals: int,
                      xg_home: Optional[float] = None, xg_away: Optional[float] = None):
        """更新評分"""
        if h_goals > a_goals:
            s_h, s_a = 1, 0
        elif h_goals == a_goals:
            s_h, s_a = 0.5, 0.5
        else:
            s_h, s_a = 0, 1
        
        # xG加權調整
        if xg_home is not None and xg_away is not None:
            xg_diff = xg_home - xg_away
            goal_diff = h_goals - a_goals
            
            if xg_diff > 0.3 and s_h == 0:
                s_h = 0.3
            elif xg_diff < -0.3 and s_h == 1:
                s_h = 0.7
        
        # 動態τ
        tau_h = self._calculate_dynamic_tau(home, away)
        tau_a = self._calculate_dynamic_tau(away, home)
        
        rh, rdh = self._scale_down(self.get_rating(home)['rating'], self.get_rating(home)['rd'])
        ra, rda = self._scale_down(self.get_rating(away)['rating'], self.get_rating(away)['rd'])
        
        g_phi_a = self._g(rda)
        g_phi_h = self._g(rdh)
        
        E_h = self._E(rh, ra, rda)
        E_a = self._E(ra, rh, rdh)
        
        v_h = 1 / (g_phi_a ** 2 * E_h * (1 - E_h))
        v_a = 1 / (g_phi_h ** 2 * E_a * (1 - E_a))
        
        new_rh = rh + (1 / (1/rdh**2 + 1/v_h)) * g_phi_a * (s_h - E_h)
        new_ra = ra + (1 / (1/rda**2 + 1/v_a)) * g_phi_h * (s_a - E_a)
        
        new_rdh = math.sqrt(1 / (1/rdh**2 + 1/v_h))
        new_rda = math.sqrt(1 / (1/rda**2 + 1/v_a))
        
        final_rh, final_rdh = self._scale_up(new_rh, new_rdh)
        final_ra, final_rda = self._scale_up(new_ra, new_rda)
        
        self.ratings[home] = {'rating': final_rh, 'rd': final_rdh, 'vol': tau_h}
        self.ratings[away] = {'rating': final_ra, 'rd': final_rda, 'vol': tau_a}
    
    def expected_win_prob(self, home: str, away: str) -> float:
        """計算主隊勝率"""
        rh = self.get_rating(home)['rating']
        ra = self.get_rating(away)['rating']
        return 1 / (1 + 10 ** ((ra - rh) / 400))
    
    def batch_update(self, matches: pd.DataFrame):
        """
        批量更新評分
        
        Args:
            matches: DataFrame with columns ['home_team', 'away_team', 'home_goals', 'away_goals']
        """
        for _, row in matches.iterrows():
            try:
                self.update_ratings(
                    row['home_team'],
                    row['away_team'],
                    int(row['home_goals']),
                    int(row['away_goals'])
                )
            except:
                continue


# ============================================
# 第三部分：信心度 Kelly 資金管理
# ============================================

@dataclass
class KellyResult:
    """Kelly計算結果"""
    stake: float           # 建議投注金額
    kelly_pct: float       # Kelly百分比
    ev: float              # 期望值
    edge: float            # 優勢
    confidence_adj: float   # 信心度調整
    risk_level: str        # 風險等級: low/medium/high

    def to_dict(self) -> Dict:
        return {
            'stake': self.stake,
            'pct': self.kelly_pct,
            'ev': self.ev,
            'edge': self.edge,
            'confidence_adj': self.confidence_adj,
            'risk_level': self.risk_level
        }


class ConfidenceKelly:
    """
    信心度調整 Kelly 資金管理 v3.1
    
    創新點：
    1. 根據模型信心度調整Kelly分數
    2. 動態分數因子（根據歷史表現）
    3. 馬爾可夫鏈風險狀態追蹤
    4. 多市場 Kelly 分配
    5. 波動率調整
    6. 連勝/連敗追蹤
    
    v3.1 更新：
    - 添加波動率調整
    - 添加連勝/連敗調整
    - 添加最大回撤保護
    """
    
    def __init__(self, 
                 base_fraction: float = 0.5,
                 max_fraction: float = 1.0,
                 min_edge: float = 0.05,
                 initial_bankroll: float = 1000):
        """
        Args:
            base_fraction: 基礎Kelly分數 (建議使用0.25-0.5的半Kelly)
            max_fraction: 最大Kelly分數限制
            min_edge: 最小優勢門檻
            initial_bankroll: 初始資金
        """
        self.base_fraction = base_fraction
        self.max_fraction = max_fraction
        self.min_edge = min_edge
        self.bankroll = initial_bankroll
        
        # 歷史追蹤
        self.bet_history = []
        self.win_history = []  # 最近20場勝率
        self.profit_history = []
        
        # 馬爾可夫狀態
        self.state = 'normal'  # normal/warning/critical
        self.max_drawdown = 0.2
        self.peak_bankroll = initial_bankroll
        
        # v3.1 新增
        self.streak_wins = 0  # 連勝
        self.streak_losses = 0  # 連敗
        self.volatility_history = []  # 波動率歷史
        
        # 風險控制
        self.max_daily_bets = 10
        self.cooldown_bets = 0  # 冷卻期
        
    def _calculate_confidence(self, 
                             model_prob: float,
                             market_prob: float,
                             model_uncertainty: float = 0.1) -> float:
        """
        計算信心度調整因子
        
        信心度基於：
        1. 模型概率 vs 市場隱含概率 的差異
        2. 模型不確定性
        """
        # 基礎信心度
        raw_confidence = 0.5
        
        # 優勢越大，信心越高
        edge = model_prob - market_prob
        edge_confidence = min(1.0, max(0.0, 0.5 + edge * 3))
        
        # 模型不確定性調整
        uncertainty_penalty = max(0.0, 1.0 - model_uncertainty * 5)
        
        # 歷史勝率調整
        if len(self.win_history) >= 20:
            win_rate = sum(self.win_history[-20:]) / 20
            hist_confidence = min(1.2, max(0.8, win_rate / 0.5))
        else:
            hist_confidence = 1.0
        
        confidence = raw_confidence * edge_confidence * uncertainty_penalty * hist_confidence
        return min(1.0, max(0.2, confidence))
    
    def _calculate_performance_factor(self) -> float:
        """計算表現因子 (基於最近表現調整)"""
        if len(self.profit_history) < 10:
            return 1.0
        
        recent_profit = sum(self.profit_history[-10:]) / 10
        volatility = np.std(self.profit_history[-20:]) if len(self.profit_history) >= 20 else 1
        
        if volatility == 0:
            return 1.0
        
        sharpe_like = recent_profit / (volatility + 0.01)
        
        # 正Sharpe比率提高Kelly，負Sharpe比率降低
        factor = 1 + sharpe_like * 0.2
        return min(1.5, max(0.5, factor))
    
    def _calculate_volatility_adjustment(self) -> float:
        """
        計算波動率調整因子
        
        高波動率時降低投注，低波動率時增加投注
        """
        if len(self.volatility_history) < 5:
            return 1.0
        
        recent_vol = np.mean(self.volatility_history[-5:])
        historical_vol = np.mean(self.volatility_history[-20:]) if len(self.volatility_history) >= 20 else recent_vol
        
        if historical_vol == 0:
            return 1.0
        
        vol_ratio = recent_vol / historical_vol
        
        # 如果近期波動率上升，降低投注
        if vol_ratio > 1.5:
            return 0.7
        elif vol_ratio > 1.2:
            return 0.85
        elif vol_ratio < 0.8:
            return 1.15
        elif vol_ratio < 0.5:
            return 1.3
        return 1.0
    
    def _calculate_streak_adjustment(self) -> float:
        """
        計算連勝/連敗調整因子
        
        連勝時稍微增加投注，連敗時減少投注
        """
        # 連勝調整
        if self.streak_wins >= 3:
            streak_bonus = min(0.2, (self.streak_wins - 2) * 0.05)
            return 1.0 + streak_bonus
        
        # 連敗調整
        if self.streak_losses >= 2:
            streak_penalty = min(0.4, self.streak_losses * 0.15)
            return 1.0 - streak_penalty
        
        return 1.0
    
    def update_after_bet(self, won: bool, profit: float):
        """
        更新投注後的狀態
        
        Args:
            won: 是否獲勝
            profit: 利潤（正數為贏，負數為輸）
        """
        self.bet_history.append(won)
        self.win_history.append(1 if won else 0)
        self.profit_history.append(profit)
        
        # 計算波動率
        if len(self.profit_history) >= 3:
            vol = np.std(self.profit_history[-3:])
            self.volatility_history.append(abs(vol))
        
        # 更新連勝/連敗
        if won:
            self.streak_wins += 1
            self.streak_losses = 0
        else:
            self.streak_losses += 1
            self.streak_wins = 0
        
        # 更新資金
        self.bankroll += profit
        
        # 觸發冷卻
        if not won and self.streak_losses >= 3:
            self.cooldown_bets = 2  # 冷卻2場
        
        # 記錄巔峰
        if self.bankroll > self.peak_bankroll:
            self.peak_bankroll = self.bankroll
    
    def get_risk_status(self) -> Dict:
        """獲取當前風險狀態"""
        current_drawdown = (self.peak_bankroll - self.bankroll) / self.peak_bankroll if self.peak_bankroll > 0 else 0
        
        return {
            'bankroll': self.bankroll,
            'peak_bankroll': self.peak_bankroll,
            'drawdown': round(current_drawdown * 100, 2),
            'state': self.state,
            'streak_wins': self.streak_wins,
            'streak_losses': self.streak_losses,
            'cooldown': self.cooldown_bets,
            'total_bets': len(self.bet_history),
            'win_rate': round(sum(self.win_history) / len(self.win_history) * 100, 2) if self.win_history else 0
        }
    
    def _update_state(self) -> str:
        """更新馬爾可夫風險狀態"""
        current_drawdown = (self.peak_bankroll - self.bankroll) / self.peak_bankroll
        
        if current_drawdown > self.max_drawdown * 0.7:
            self.state = 'critical'
        elif current_drawdown > self.max_drawdown * 0.4:
            self.state = 'warning'
        else:
            self.state = 'normal'
        
        # 更新峰值
        if self.bankroll > self.peak_bankroll:
            self.peak_bankroll = self.bankroll
        
        return self.state
    
    def _state_risk_multiplier(self) -> float:
        """根據風險狀態計算投注倍數"""
        multipliers = {
            'normal': 1.0,
            'warning': 0.5,
            'critical': 0.25
        }
        return multipliers.get(self.state, 1.0)
    
    def calculate(self,
                  prob: float,
                  odds: float,
                  confidence: float = 0.5,
                  model_uncertainty: float = 0.1,
                  market_prob: Optional[float] = None) -> KellyResult:
        """
        計算信心度調整後的Kelly投注 v3.1
        
        Args:
            prob: 模型預測概率
            odds: 歐洲赔率
            confidence: 模型信心度 (0-1)
            model_uncertainty: 模型不確定性 (0-1)
            market_prob: 市場隱含概率 (用於計算優勢)
        """
        # 檢查冷卻期
        if self.cooldown_bets > 0:
            return KellyResult(0, 0, 0, 0, confidence, 'cooldown')
        
        if prob <= 0 or odds <= 1:
            return KellyResult(0, 0, 0, 0, 0, 'low')
        
        if market_prob is None:
            market_prob = 1 / odds
        
        # 1. 計算原始Kelly
        b = odds - 1
        q = 1 - prob
        raw_kelly = (b * prob - q) / b
        
        if raw_kelly <= 0:
            return KellyResult(0, 0, -q, 0, confidence, 'low')
        
        # 2. 計算期望值
        ev = (prob * b) - q
        
        # 3. 計算優勢
        edge = prob - market_prob

        # 4. 計算信心度調整因子
        confidence_adj = self._calculate_confidence(
            prob, market_prob, model_uncertainty
        )
        
        # 5. 表現因子
        perf_factor = self._calculate_performance_factor()
        
        # 6. 波動率調整 (v3.1)
        vol_adjustment = self._calculate_volatility_adjustment()
        
        # 7. 連勝/連敗調整 (v3.1)
        streak_adjustment = self._calculate_streak_adjustment()
        
        # 8. 風險狀態
        self._update_state()
        state_multiplier = self._state_risk_multiplier()
        
        # 9. 計算最終Kelly分數
        final_kelly = (
            raw_kelly * 
            confidence_adj * 
            perf_factor * 
            vol_adjustment *
            streak_adjustment *
            state_multiplier *
            self.base_fraction
        )
        
        # 限制最大分數
        final_kelly = min(final_kelly, self.max_fraction * raw_kelly)
        
        # 8. 計算投注金額
        stake = self.bankroll * final_kelly
        
        # 9. 風險等級
        if final_kelly < 0.02:
            risk = 'low'
        elif final_kelly < 0.05:
            risk = 'medium'
        else:
            risk = 'high'
        
        # 10. 檢查最小優勢門檻
        if edge < self.min_edge:
            stake = 0
            risk = 'low'

        return KellyResult(
            stake=stake,
            kelly_pct=final_kelly,
            ev=ev,
            edge=edge,
            confidence_adj=confidence_adj,
            risk_level=risk
        )
    
    def update_result(self, won: bool, odds: float, stake: float):
        """
        更新投注結果
        
        Args:
            won: 是否獲勝
            odds: 赔率
            stake: 投注金額
        """
        if won:
            profit = stake * (odds - 1)
        else:
            profit = -stake
        
        self.bankroll += profit
        self.bet_history.append({'won': won, 'profit': profit})
        self.win_history.append(1 if won else 0)
        self.profit_history.append(profit)
        
        # 保持歷史長度
        if len(self.win_history) > 50:
            self.win_history.pop(0)
            self.profit_history.pop(0)
        
        # 更新風險狀態
        self._update_state()
    
    def get_stats(self) -> Dict:
        """獲取統計信息"""
        if not self.bet_history:
            return {'total_bets': 0}
        
        total = len(self.bet_history)
        wins = sum(1 for b in self.bet_history if b['won'])
        total_profit = sum(b['profit'] for b in self.bet_history)
        
        return {
            'total_bets': total,
            'wins': wins,
            'win_rate': wins / total,
            'total_profit': total_profit,
            'current_bankroll': self.bankroll,
            'roi': total_profit / (self.peak_bankroll * total) * 100 if total > 0 else 0,
            'risk_state': self.state
        }


class PortfolioKelly:
    """
    組合 Kelly 管理 v2
    
    管理多個市場的投注分配
    
    v2 更新：
    - 添加多元化係數
    - 添加相關性調整
    - 支持多種風險偏好
    """
    
    def __init__(self, kelly_managers: List[ConfidenceKelly],
                 risk_tolerance: str = 'moderate'):  # conservative/moderate/aggressive
        self.managers = kelly_managers
        self.total_allocated = 0
        self.max_allocation = 0.25  # 最多投入25%資金
        self.risk_tolerance = risk_tolerance
        
        # 風險參數
        self.risk_params = {
            'conservative': {'max_allocation': 0.15, 'min_odds': 1.5, 'max_odds': 3.0},
            'moderate': {'max_allocation': 0.25, 'min_odds': 1.3, 'max_odds': 4.0},
            'aggressive': {'max_allocation': 0.40, 'min_odds': 1.2, 'max_odds': 6.0}
        }
        
        # 多元化追蹤
        self.market_exposure = {}  # {market: total_exposure}
        self.correlation_matrix = {}
        
        # 歷史記錄
        self.allocation_history = []
    
    def set_risk_tolerance(self, tolerance: str):
        """設置風險偏好"""
        if tolerance in self.risk_params:
            self.risk_tolerance = tolerance
            self.max_allocation = self.risk_params[tolerance]['max_allocation']
    
    def calculate_diversity_bonus(self, markets: List[str]) -> float:
        """
        計算多元化獎勵
        
        投注在不同市場可以降低整體風險
        """
        unique_markets = len(set(markets))
        if unique_markets == 1:
            return 1.0
        elif unique_markets == 2:
            return 1.1
        elif unique_markets >= 3:
            return 1.2
        return 1.0
    
    def calculate_correlation_penalty(self, outcomes: List[str]) -> float:
        """
        計算相關性懲罰
        
        避免過度集中在相關的結果上
        """
        # 簡單的相關性檢測
        # 例如：主勝和讓球主勝視為相關
        correlation_groups = [
            {'home_win', 'asian_home', 'handicap_home'},
            {'draw', 'under', 'under_2.5'},
            {'away_win', 'asian_away', 'handicap_away'}
        ]
        
        for group in correlation_groups:
            overlap = len(set(outcomes) & group)
            if overlap > 1:
                return 0.8  # 懲罰
        
        return 1.0
    
    def allocate_bets(self, 
                     bets: List[Tuple[float, float, float, float, float]],
                     bankroll: float,
                     markets: List[str] = None,
                     outcomes: List[str] = None) -> List[KellyResult]:
        """
        分配組合投注 v2
        
        Args:
            bets: List of (prob, odds, confidence, uncertainty, market_prob) tuples
            bankroll: 總資金
            markets: 市場列表（用於多元化計算）
            outcomes: 結果列表（用於相關性計算）
        Returns: List of KellyResult
        """
        results = []
        total_kelly = 0
        
        # 獲取風險參數
        params = self.risk_params.get(self.risk_tolerance, self.risk_params['moderate'])
        
        for i, (prob, odds, conf, unc, market_prob) in enumerate(bets):
            # 過濾不符合風險參數的投注
            if odds < params['min_odds'] or odds > params['max_odds']:
                results.append(KellyResult(0, 0, 0, 0, conf, 'filtered'))
                continue
            
            # 使用 manager 計算
            result = self.managers[0].calculate(
                prob, odds, conf, unc, market_prob
            )
            results.append(result)
            total_kelly += result.kelly_pct
        
        # 多元化獎勵
        if markets and len(markets) > 1:
            diversity_bonus = self.calculate_diversity_bonus(markets)
            total_kelly *= diversity_bonus
        
        # 相關性懲罰
        if outcomes:
            correlation_penalty = self.calculate_correlation_penalty(outcomes)
            total_kelly *= correlation_penalty
        
        # 調整過度集中的投注
        if total_kelly > self.max_allocation:
            scale = self.max_allocation / total_kelly
            for r in results:
                if r.stake > 0:
                    r.stake *= scale
                    r.kelly_pct *= scale
        
        # 記錄分配歷史
        self.allocation_history.append({
            'total_kelly': total_kelly,
            'n_bets': len(bets),
            'risk_tolerance': self.risk_tolerance
        })
        
        return results
    
    def get_portfolio_stats(self) -> Dict:
        """獲取組合統計"""
        if not self.allocation_history:
            return {'status': 'no_data'}
        
        recent = self.allocation_history[-20:]
        
        return {
            'avg_allocation': np.mean([h['total_kelly'] for h in recent]),
            'avg_bets': np.mean([h['n_bets'] for h in recent]),
            'risk_tolerance': self.risk_tolerance,
            'max_allocation': self.max_allocation,
            'market_exposure': self.market_exposure
        }


class DutchingCalculator:
    """
    Dutching (荷蘭投注) 計算器
    
    在多個選項上投注，無論哪個選項獲勝都能獲得相同回報
    """
    
    def __init__(self, target_return: float = 1.0, min_odds: float = 1.1):
        """
        Args:
            target_return: 目標回報率 (例如 1.0 = 100% 回報)
            min_odds: 最小赔率過濾
        """
        self.target_return = target_return
        self.min_odds = min_odds
    
    def calculate(self, odds_dict: Dict[str, float], 
                  total_stake: float = 100) -> Dict[str, Dict]:
        """
        計算 Dutching 投注
        
        Args:
            odds_dict: {outcome: odds} 例如 {'home': 2.0, 'draw': 3.5, 'away': 4.0}
            total_stake: 總投注額
            
        Returns:
            Dict: {outcome: {stake, odds, profit, win_prob}}
        """
        # 過濾低赔率
        valid_odds = {k: v for k, v in odds_dict.items() if v >= self.min_odds}
        
        if not valid_odds:
            return {}
        
        # 計算隱含概率
        implied_probs = {k: 1/v for k, v in valid_odds.items()}
        total_implied = sum(implied_probs.values())
        
        # 檢查是否有價值
        if total_implied > 1.0:
            # 無利可圖，返回空結果
            return {}
        
        # 計算每個選項的投注額
        stakes = {}
        for outcome, odds in valid_odds.items():
            # 根據隱含概率比例分配
            adjusted_prob = implied_probs[outcome] / total_implied
            stake = total_stake * adjusted_prob
            
            # 計算如果該選項獲勝的利潤
            profit = stake * (odds - 1) - (total_stake - stake)
            
            stakes[outcome] = {
                'stake': round(stake, 2),
                'odds': odds,
                'implied_prob': round(implied_probs[outcome], 4),
                'profit_if_win': round(profit, 2),
                'roi': round(profit / total_stake * 100, 2)
            }
        
        # 計算預期回報
        expected_return = sum(
            s['implied_prob'] * s['profit_if_win'] 
            for s in stakes.values()
        )
        
        return {
            'bets': stakes,
            'total_stake': total_stake,
            'guaranteed_profit': round(expected_return, 2),
            'total_odds': round(1 / total_implied, 3) if total_implied > 0 else 0,
            'is_profitable': total_implied < 1.0
        }
    
    def calculate_kelly_dutching(self, odds_dict: Dict[str, float],
                                  probabilities: Dict[str, float],
                                  kelly_fraction: float = 0.5) -> Dict:
        """
        Kelly Dutching - 結合 Kelly 準則的 Dutching
        
        Args:
            odds_dict: {outcome: odds}
            probabilities: {outcome: model_probability}
            kelly_fraction: Kelly 分數 (0.5 = 半 Kelly)
            
        Returns:
            Dict with Kelly-optimized stakes
        """
        # 過濾有效選項
        valid_outcomes = [k for k in odds_dict.keys() if k in probabilities]
        
        if not valid_outcomes:
            return {}
        
        # 計算 Kelly 優勢
        kelly_edges = {}
        for outcome in valid_outcomes:
            odds = odds_dict[outcome]
            prob = probabilities[outcome]
            implied_prob = 1 / odds
            
            # Kelly 優勢
            edge = prob - implied_prob
            kelly_edges[outcome] = max(0, edge)
        
        # 正規化 Kelly 優勢
        total_edge = sum(kelly_edges.values())
        
        if total_edge <= 0:
            return {'status': 'no_edge', 'bets': {}}
        
        # 計算 Kelly 投注額
        stakes = {}
        for outcome in valid_outcomes:
            # 使用 Kelly 權重
            weight = kelly_edges[outcome] / total_edge
            
            # Kelly 公式
            odds = odds_dict[outcome]
            prob = probabilities[outcome]
            b = odds - 1
            q = 1 - prob
            
            kelly_pct = max(0, (b * prob - q) / b) if b > 0 else 0
            kelly_pct *= kelly_fraction
            
            stakes[outcome] = {
                'kelly_pct': round(kelly_pct, 4),
                'weight': round(weight, 4),
                'edge': round(kelly_edges[outcome], 4),
                'odds': odds
            }
        
        return {
            'status': 'success',
            'bets': stakes,
            'total_kelly': round(sum(s['kelly_pct'] for s in stakes.values()), 4),
            'kelly_fraction': kelly_fraction
        }


# ============================================
# 第四部分：Stacking 集成學習
# ============================================

@dataclass
class ModelPrediction:
    """單模型預測結果"""
    name: str
    prob_home: float
    prob_draw: float
    prob_away: float
    confidence: float  # 模型信心度
    weight: float      # 集成權重


class BaseMLModel(ABC):
    """ML模型基類"""
    
    @abstractmethod
    def fit(self, X: pd.DataFrame, y: np.ndarray):
        pass
    
    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        pass
    
    @abstractmethod
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        pass


class XGBoostModel(BaseMLModel):
    """XGBoost 模型包裝"""
    
    def __init__(self, n_estimators: int = 200, learning_rate: float = 0.05,
                 max_depth: int = 6, random_state: int = 42):
        try:
            from xgboost import XGBClassifier
            self.model = XGBClassifier(
                n_estimators=n_estimators,
                learning_rate=learning_rate,
                max_depth=max_depth,
                min_child_weight=3,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1,
                eval_metric='mlogloss',
                random_state=random_state,
                use_label_encoder=False
            )
        except ImportError:
            self.model = None
    
    def fit(self, X: pd.DataFrame, y: np.ndarray):
        if self.model:
            self.model.fit(X, y)
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            return np.zeros(len(X))
        return self.model.predict(X)
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            return np.ones((len(X), 3)) / 3
        return self.model.predict_proba(X)
    
    def feature_importance(self) -> pd.Series:
        if self.model:
            return pd.Series(
                self.model.feature_importances_,
                index=self.model.feature_names_in_
            )
        return pd.Series()


class RandomForestModel(BaseMLModel):
    """Random Forest 模型包裝"""
    
    def __init__(self, n_estimators: int = 200, max_depth: int = 10, random_state: int = 42):
        from sklearn.ensemble import RandomForestClassifier
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=random_state
        )
    
    def fit(self, X: pd.DataFrame, y: np.ndarray):
        self.model.fit(X, y)
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(X)
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X)


class GradientBoostingModel(BaseMLModel):
    """Gradient Boosting 模型包裝"""
    
    def __init__(self, n_estimators: int = 150, learning_rate: float = 0.05,
                 max_depth: int = 5, random_state: int = 42):
        from sklearn.ensemble import GradientBoostingClassifier
        self.model = GradientBoostingClassifier(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            max_depth=max_depth,
            subsample=0.8,
            random_state=random_state
        )
    
    def fit(self, X: pd.DataFrame, y: np.ndarray):
        self.model.fit(X, y)
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(X)
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X)


class LogisticRegressionModel(BaseMLModel):
    """Logistic Regression 模型包裝"""
    
    def __init__(self, C: float = 1.0, random_state: int = 42):
        from sklearn.linear_model import LogisticRegression
        self.model = LogisticRegression(
            C=C,
            max_iter=1000,
            multi_class='multinomial',
            random_state=random_state
        )
        self.feature_names = None
    
    def fit(self, X: pd.DataFrame, y: np.ndarray):
        self.feature_names = X.columns.tolist()
        self.model.fit(X, y)
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(X)
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X)


class StackingEnsemble:
    """
    Stacking 集成模型 v3
    
    創新點：
    1. 多層次Stacking
    2. 貝葉斯權重優化
    3. Out-of-Fold 預防過擬合
    4. 動態權重更新
    
    v3.1 更新：
    - 添加與真實數據整合的方法
    - 添加特徵工程支持
    - 添加交叉驗證框架
    """
    
    def __init__(self, 
                 base_models: List[BaseMLModel],
                 meta_model: Optional[BaseMLModel] = None,
                 cv_folds: int = 5,
                 use_bayesian_weights: bool = True):
        """
        Args:
            base_models: 基礎模型列表
            meta_model: 元學習器 (預設LogisticRegression)
            cv_folds: 交叉驗證折數
            use_bayesian_weights: 是否使用貝葉斯權重
        """
        self.base_models = base_models
        self.meta_model = meta_model or LogisticRegressionModel(C=0.5)
        self.cv_folds = cv_folds
        self.use_bayesian = use_bayesian_weights
        
        # 權重
        self.model_weights = {}
        self._initialize_weights()
        
        # 性能追蹤
        self.validation_scores = {}
        self.oof_predictions = {}
        
        # 訓練數據
        self.training_data = None
        self.feature_names = []
    
    def _initialize_weights(self):
        """初始化均勻權重"""
        for model in self.base_models:
            name = model.__class__.__name__
            self.model_weights[name] = 1.0 / len(self.base_models)
    
    def _get_oof_predictions(self, X: np.ndarray, y: np.ndarray) -> np.ndarray:
        """
        獲取Out-of-Fold預測 (防止過擬合)
        """
        from sklearn.model_selection import StratifiedKFold
        
        n_samples = len(X)
        n_classes = len(np.unique(y))
        oof_preds = np.zeros((n_samples, n_classes))
        
        kfold = StratifiedKFold(n_splits=self.cv_folds, shuffle=True)
        
        for train_idx, val_idx in kfold.split(X, y):
            X_train, X_val = X[train_idx], X[val_idx]
            y_train = y[train_idx]
            
            for model in self.base_models:
                model.fit(X_train, y_train)
                oof_preds[val_idx] += model.predict_proba(X_val)
        
        # 平均
        oof_preds /= len(self.base_models)
        return oof_preds
    
    def _optimize_bayesian_weights(self, 
                                    oof_preds: np.ndarray,
                                    y: np.ndarray) -> Dict[str, float]:
        """
        使用貝葉斯優化找到最佳權重
        """
        from scipy.optimize import minimize
        from sklearn.metrics import log_loss
        
        n_models = len(self.base_models)
        
        def objective(weights):
            # 正則化權重
            weights = np.exp(weights) / np.sum(np.exp(weights))
            
            # 加權平均預測
            weighted_pred = np.zeros_like(oof_preds[0])
            for i, model in enumerate(self.base_models):
                name = model.__class__.__name__
                model_idx = int(name.split('_')[-1]) if name.endswith('_') else i
                weighted_pred += weights[i] * oof_preds[:, model_idx]
            
            return log_loss(y, weighted_pred)
        
        # 初始權重
        x0 = np.zeros(n_models)
        
        # 優化
        result = minimize(objective, x0, method='Nelder-Mead')
        
        # 轉換為概率
        weights = np.exp(result.x) / np.sum(np.exp(result.x))
        
        # 返回權重字典
        weights_dict = {}
        for i, model in enumerate(self.base_models):
            name = model.__class__.__name__
            weights_dict[name] = weights[i]
        
        return weights_dict
    
    def _calculate_model_confidence(self, 
                                   predictions: np.ndarray,
                                   y: np.ndarray) -> Dict[str, float]:
        """
        計算每個模型的信心度
        """
        from sklearn.metrics import brier_score_loss
        
        confidences = {}
        for i, model in enumerate(self.base_models):
            name = model.__class__.__name__
            # Brier Score越小，信心度越高
            bs = brier_score_loss(y, predictions[:, i])
            confidence = 1 / (1 + bs)
            confidences[name] = confidence
        
        return confidences
    
    def fit(self, X: pd.DataFrame, y: np.ndarray):
        """訓練集成模型"""
        X_array = X.values
        n_classes = len(np.unique(y))
        
        # 1. 訓練基礎模型並獲取OOF預測
        oof_preds = np.zeros((len(X_array), n_classes, len(self.base_models)))
        
        for i, model in enumerate(self.base_models):
            name = model.__class__.__name__
            print(f"  訓練基礎模型: {name}")
            
            # OOF預測
            kfold = StratifiedKFold(n_splits=self.cv_folds, shuffle=True)
            fold_preds = np.zeros((len(X_array), n_classes))
            
            for train_idx, val_idx in kfold.split(X_array, y):
                X_train, X_val = X_array[train_idx], X_array[val_idx]
                y_train = y[train_idx]
                
                model.fit(X_train, y_train)
                fold_preds[val_idx] = model.predict_proba(X_val)
            
            oof_preds[:, :, i] = fold_preds
            
            # 驗證分數
            from sklearn.metrics import accuracy_score
            acc = accuracy_score(y, np.argmax(fold_preds, axis=1))
            self.validation_scores[name] = acc
            print(f"    驗證準確率: {acc:.2%}")
        
        # 2. 計算權重
        if self.use_bayesian:
            # 重塑為 (n_samples, n_models) 每列一個類別
            # 使用主類別(主勝)概率優化權重
            self.model_weights = self._optimize_bayesian_weights(
                oof_preds[:, 0, :],  # 使用主勝概率
                (y == 0).astype(int)
            )
        else:
            self._initialize_weights()
        
        # 3. 計算信心度
        self.model_confidence = self._calculate_model_confidence(
            oof_preds.mean(axis=2), y
        )
        
        # 4. 訓練元學習器
        print("  訓練元學習器...")
        meta_features = oof_preds.mean(axis=2)  # 平均所有基礎模型預測
        
        # 為元學習器創建特徵：每個基礎模型對每個類別的預測
        meta_X = np.zeros((len(X_array), len(self.base_models) * n_classes))
        for i, model in enumerate(self.base_models):
            for c in range(n_classes):
                meta_X[:, i * n_classes + c] = oof_preds[:, c, i]
        
        self.meta_model.fit(pd.DataFrame(meta_X), y)
        
        print("  權重:")
        for name, weight in self.model_weights.items():
            print(f"    {name}: {weight:.3f}")
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """預測"""
        X_array = X.values
        n_samples = len(X_array)
        n_classes = 3
        
        # 1. 基礎模型預測
        base_preds = np.zeros((n_samples, n_classes, len(self.base_models)))
        for i, model in enumerate(self.base_models):
            base_preds[:, :, i] = model.predict_proba(X_array)
        
        # 2. 權重平均
        weighted_avg = np.zeros((n_samples, n_classes))
        for i, model in enumerate(self.base_models):
            name = model.__class__.__name__
            weight = self.model_weights.get(name, 1.0 / len(self.base_models))
            weighted_avg += weight * base_preds[:, :, i]
        
        # 3. 元學習器預測 (如果可用)
        try:
            meta_X = np.zeros((n_samples, len(self.base_models) * n_classes))
            for i, model in enumerate(self.base_models):
                for c in range(n_classes):
                    meta_X[:, i * n_classes + c] = base_preds[:, c, i]
            
            meta_pred = self.meta_model.predict(meta_X)
            
            # 結合兩種方法
            final_pred = 0.7 * weighted_avg + 0.3 * meta_pred
        except:
            final_pred = weighted_avg
        
        return np.argmax(final_pred, axis=1)
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """預測概率"""
        X_array = X.values
        n_samples = len(X_array)
        n_classes = 3
        
        # 基礎模型預測
        base_preds = np.zeros((n_samples, n_classes, len(self.base_models)))
        for i, model in enumerate(self.base_models):
            base_preds[:, :, i] = model.predict_proba(X_array)
        
        # 加權平均
        weighted_avg = np.zeros((n_samples, n_classes))
        for i, model in enumerate(self.base_models):
            name = model.__class__.__name__
            weight = self.model_weights.get(name, 1.0 / len(self.base_models))
            weighted_avg += weight * base_preds[:, :, i]
        
        # 標準化
        weighted_avg = weighted_avg / weighted_avg.sum(axis=1, keepdims=True)
        
        return weighted_avg
    
    def get_individual_predictions(self, X: pd.DataFrame) -> List[ModelPrediction]:
        """獲取各模型單獨預測"""
        X_array = X.values
        predictions = []
        
        for model in self.base_models:
            name = model.__class__.__name__
            proba = model.predict_proba(X_array)
            
            predictions.append(ModelPrediction(
                name=name,
                prob_home=proba[0, 0] if len(proba) == 1 else proba[:, 0].mean(),
                prob_draw=proba[0, 1] if len(proba) == 1 else proba[:, 1].mean(),
                prob_away=proba[0, 2] if len(proba) == 1 else proba[:, 2].mean(),
                confidence=self.model_confidence.get(name, 0.5),
                weight=self.model_weights.get(name, 0.33)
            ))
        
        return predictions
    
    def get_ensemble_stats(self) -> Dict:
        """獲取集成統計"""
        return {
            'model_weights': self.model_weights,
            'validation_scores': self.validation_scores,
            'model_confidence': self.model_confidence,
            'n_base_models': len(self.base_models)
        }
    
    def prepare_features_from_dataframe(self, df: pd.DataFrame, target_col: str = 'result') -> Tuple[pd.DataFrame, np.ndarray]:
        """
        從 DataFrame 準備特徵矩陣
        
        自動處理：
        - 數值特徵標準化
        - 類別特徵編碼
        - 缺失值處理
        
        Args:
            df: 輸入數據
            target_col: 目標列名稱
            
        Returns:
            Tuple of (features, target)
        """
        from sklearn.preprocessing import StandardScaler, LabelEncoder
        
        # 複製避免修改原始數據
        data = df.copy()
        
        # 識別特徵列
        exclude_cols = [target_col, 'date', 'match_date', 'event_id', 'home_team', 'away_team', 'league']
        feature_cols = [c for c in data.columns if c not in exclude_cols]
        
        # 處理目標變量
        if target_col in data.columns:
            le = LabelEncoder()
            y = le.fit_transform(data[target_col])
        else:
            y = None
        
        # 處理數值特徵
        numeric_cols = data[feature_cols].select_dtypes(include=[np.number]).columns.tolist()
        
        # 標準化
        scaler = StandardScaler()
        data[numeric_cols] = scaler.fit_transform(data[numeric_cols].fillna(0))
        
        # 選擇特徵
        X = data[numeric_cols]
        self.feature_names = numeric_cols
        
        return X, y
    
    def train_with_cross_validation(self, X: pd.DataFrame, y: np.ndarray, 
                                   optimize_weights: bool = True) -> Dict:
        """
        使用交叉驗證訓練集成模型
        
        Args:
            X: 特徵矩陣
            y: 目標變量
            optimize_weights: 是否優化權重
            
        Returns:
            Dict: 訓練結果統計
        """
        from sklearn.model_selection import cross_val_score, StratifiedKFold
        
        # 存儲結果
        cv_scores = {}
        fold_predictions = {}
        
        # 交叉驗證
        skf = StratifiedKFold(n_splits=self.cv_folds, shuffle=True)
        
        for fold, (train_idx, val_idx) in enumerate(skf.split(X, y)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]
            
            # 訓練每個基礎模型
            for model in self.base_models:
                name = model.__class__.__name__
                model.fit(X_train, y_train)
                
                # 驗證
                score = model.model.score(X_val, y_val) if hasattr(model.model, 'score') else 0.5
                
                if name not in cv_scores:
                    cv_scores[name] = []
                cv_scores[name].append(score)
            
            # 訓練元模型
            base_preds_train = np.column_stack([
                m.predict_proba(X_train)[:, 1] for m in self.base_models
            ])
            base_preds_val = np.column_stack([
                m.predict_proba(X_val)[:, 1] for m in self.base_models
            ])
            
            self.meta_model.fit(base_preds_train, y_train)
            meta_score = self.meta_model.model.score(base_preds_val, y_val) if hasattr(self.meta_model.model, 'score') else 0.5
            
            if 'Meta' not in cv_scores:
                cv_scores['Meta'] = []
            cv_scores['Meta'].append(meta_score)
        
        # 計算平均分數
        self.validation_scores = {k: np.mean(v) for k, v in cv_scores.items()}
        
        # 優化權重
        if optimize_weights:
            for name in self.model_weights:
                self.model_weights[name] = self.validation_scores.get(name, 0.33)
            
            # 正規化
            total = sum(self.model_weights.values())
            self.model_weights = {k: v/total for k, v in self.model_weights.items()}
        
        # 最終在全量數據上訓練
        X_array = X.values
        for model in self.base_models:
            model.fit(X_array, y)
        
        # 訓練元模型
        base_preds_full = np.column_stack([
            m.predict_proba(X_array)[:, 1] for m in self.base_models
        ])
        self.meta_model.fit(base_preds_full, y)
        
        return {
            'cv_scores': self.validation_scores,
            'model_weights': self.model_weights,
            'n_folds': self.cv_folds,
            'n_features': len(self.feature_names)
        }
    
    def get_feature_importance(self) -> pd.DataFrame:
        """
        獲取特徵重要性（如果有模型支持）
        
        Returns:
            DataFrame: 特徵重要性
        """
        importance_dict = {}
        
        for model in self.base_models:
            name = model.__class__.__name__
            if hasattr(model, 'feature_importance'):
                importance_dict[name] = model.feature_importance()
        
        if importance_dict:
            return pd.DataFrame(importance_dict)
        return pd.DataFrame()


# ============================================
# 第五部分：蒙地卡羅模擬器升級
# ============================================

class MonteCarloSimulatorV3:
    """
    蒙地卡羅模擬器 v3
    
    改進：
    1. 支持 Poisson 和負二項分布
    2. 多種投注市場
    3. 置信區間
    
    負二項分布參數化說明：
    - scipy.stats.nbinom 使用 (n, p) 參數化
    - mean = n * (1-p) / p
    - variance = n * (1-p) / p^2
    - 對於足球進球，我們使用 Quasi-Poisson 思想
    - variance = mu + alpha * mu^2
    """
    
    def __init__(self, home_expect: float, away_expect: float, 
                 iterations: int = 10000,
                 use_nbinom: bool = True,
                 dispersion: float = 1.5):
        self.mu_h = home_expect
        self.mu_a = away_expect
        self.iterations = iterations
        self.use_nbinom = use_nbinom
        self.dispersion = dispersion
        
    def _generate_nbinom_samples(self, mu: float, n_samples: int, dispersion: float) -> np.ndarray:
        """
        生成負二項分布樣本
        
        穩定的參數化方法：
        使用 Gamma-Poisson 混合物方法
        1. 先從 Gamma 分布生成 lambda ~ Gamma(alpha, theta)
        2. 再從 Poisson(lambda) 生成計數
        """
        if dispersion <= 0.05:
            # 接近 Poisson
            return np.random.poisson(mu, n_samples)
        
        # Gamma-Poisson 混合物方法
        # Gamma: shape = mu^2 / var, scale = var / mu
        # var = mu + alpha * mu^2
        var = mu + dispersion * (mu ** 2)
        shape = (mu ** 2) / (var - mu + 0.001)
        scale = var / (mu + 0.001)
        
        # 確保 shape 足夠大
        shape = max(1.0, shape)
        
        # 生成 Gamma 樣本
        lambdas = np.random.gamma(shape, scale, n_samples)
        lambdas = np.clip(lambdas, 0.01, mu * 10)  # 限制範圍
        
        # 生成 Poisson 樣本
        samples = np.random.poisson(lambdas)
        samples = np.clip(samples, 0, 15)  # 進球數限制
        
        return samples
        
    def run_simulation(self) -> Dict:
        """運行模擬"""
        # 生成樣本
        if self.use_nbinom:
            h_goals = self._generate_nbinom_samples(self.mu_h, self.iterations, self.dispersion)
            a_goals = self._generate_nbinom_samples(self.mu_a, self.iterations, self.dispersion)
        else:
            h_goals = np.random.poisson(self.mu_h, self.iterations)
            a_goals = np.random.poisson(self.mu_a, self.iterations)
        
        # 確保是 numpy 數組
        h_goals = np.asarray(h_goals, dtype=np.float64)
        a_goals = np.asarray(a_goals, dtype=np.float64)
        
        # 計算結果
        home_wins = np.sum(h_goals > a_goals)
        draws = np.sum(h_goals == a_goals)
        away_wins = np.sum(h_goals < a_goals)
        total_goals = h_goals + a_goals
        
        diff = h_goals - a_goals
        
        # 亞洲讓分盤
        ah_lines = [-1.5, -1.0, -0.5, 0, 0.5, 1.0, 1.5]
        ah_probs = {}
        for line in ah_lines:
            wins = np.sum((diff + line) > 0)
            ah_probs[f"AH {line:+.1f}"] = float(wins / self.iterations)
        
        # 大小球
        ou_lines = [1.5, 2.0, 2.5, 3.0, 3.5]
        ou_probs = {}
        for line in ou_lines:
            over = np.sum(total_goals > line)
            ou_probs[f"OU {line:.1f}"] = float(over / self.iterations)
        
        # 計算分佈
        home_dist = {i: float(np.sum(h_goals == i) / self.iterations) for i in range(6)}
        away_dist = {i: float(np.sum(a_goals == i) / self.iterations) for i in range(6)}
        
        # 置信區間
        home_ci = np.percentile(h_goals, [2.5, 97.5])
        away_ci = np.percentile(a_goals, [2.5, 97.5])
        
        return {
            "mc_home_win": float(home_wins / self.iterations),
            "mc_draw": float(draws / self.iterations),
            "mc_away_win": float(away_wins / self.iterations),
            "mc_over_2.5": ou_probs.get("OU 2.5", 0.0),
            "mc_under_2.5": 1.0 - ou_probs.get("OU 2.5", 0.0),
            "ah_probs": ah_probs,
            "ou_probs": ou_probs,
            "expected_goals": {
                "home": float(np.mean(h_goals)),
                "away": float(np.mean(a_goals)),
                "home_var": float(np.var(h_goals)),
                "away_var": float(np.var(a_goals))
            },
            "goals_distribution": {
                "home": home_dist,
                "away": away_dist
            },
            "confidence_95": {
                "home_goals_ci": [float(home_ci[0]), float(home_ci[1])],
                "away_goals_ci": [float(away_ci[0]), float(away_ci[1])]
            }
        }


# ============================================
# 工具函數
# ============================================

def create_ensemble_models() -> List[BaseMLModel]:
    """創建默認集成模型列表"""
    return [
        XGBoostModel(n_estimators=200, learning_rate=0.05, max_depth=6),
        RandomForestModel(n_estimators=200, max_depth=10),
        GradientBoostingModel(n_estimators=150, learning_rate=0.05, max_depth=5),
        LogisticRegressionModel(C=1.0)
    ]


def calculate_model_uncertainty(predictions: np.ndarray) -> float:
    """
    計算模型不確定性
    
    基於預測概率的熵
    """
    # 添加小值避免log(0)
    p = np.clip(predictions, 1e-10, 1 - 1e-10)
    entropy = -np.sum(p * np.log(p), axis=1)
    
    # 標準化到0-1
    max_entropy = np.log(3)
    uncertainty = 1 - (entropy / max_entropy)
    
    return float(np.mean(uncertainty))


def calibrate_probabilities(predictions: Dict[str, np.ndarray]) -> np.ndarray:
    """
    校準概率預測 (使用Platt Scaling思想)
    
    predictions: {model_name: [n_samples, 3]} 的字典
    """
    from sklearn.linear_model import LogisticRegression
    
    # 合併所有預測
    all_preds = np.column_stack([p for p in predictions.values()])
    n_samples = len(all_preds) // len(predictions)
    
    # 使用第一個預測的標籤作為目標
    labels = np.argmax(list(predictions.values())[0], axis=1)
    
    # 簡單校準：平均 + softmax
    calibrated = np.mean(list(predictions.values()), axis=0)
    calibrated = calibrated / calibrated.sum(axis=1, keepdims=True)
    
    return calibrated


# ============================================
# 主程式入口
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("數學模型升級版 v3 - 測試")
    print("=" * 60)
    
    # 1. 測試負二項分布
    print("\n[1] 負二項分布測試")
    nb_model = NegativeBinomialModel(1.5, 1.0)
    nb_probs = nb_model.calculate_probabilities()
    print(f"  主勝: {nb_probs['home_win']:.1%}")
    print(f"  和局: {nb_probs['draw']:.1%}")
    print(f"  客勝: {nb_probs['away_win']:.1%}")
    print(f"  離散參數: {nb_probs['dispersion']:.2f}")
    
    # 2. 測試動態K Elo
    print("\n[2] 動態K Elo系統測試")
    elo = DynamicKEloSystem()
    elo.update_ratings("TeamA", "TeamB", 2, 1)
    elo.update_ratings("TeamA", "TeamC", 1, 3)
    print(f"  TeamA Rating: {elo.get_rating('TeamA'):.1f}")
    print(f"  TeamB Rating: {elo.get_rating('TeamB'):.1f}")
    print(f"  TeamC Rating: {elo.get_rating('TeamC'):.1f}")
    
    # 3. 測試信心度Kelly
    print("\n[3] 信心度Kelly測試")
    kelly = ConfidenceKelly(base_fraction=0.5)
    result = kelly.calculate(
        prob=0.55,  # 模型概率
        odds=2.0,   # 赔率
        confidence=0.7,  # 信心度
        model_uncertainty=0.1,
        market_prob=0.5  # 市場隱含概率
    )
    print(f"  Kelly百分比: {result.kelly_pct:.2%}")
    print(f"  期望值: {result.ev:.3f}")
    print(f"  優勢: {result.edge:.3f}")
    print(f"  風險等級: {result.risk_level}")
    
    # 4. 測試Stacking集成
    print("\n[4] Stacking集成測試")
    print("  (需要實際數據訓練，請運行 scripts/train_model_v3.py)")
    
    # 5. 測試蒙地卡羅
    print("\n[5] 蒙地卡羅模擬V3測試")
    mc = MonteCarloSimulatorV3(1.5, 1.0, iterations=5000)
    mc_result = mc.run_simulation()
    print(f"  主勝: {mc_result['mc_home_win']:.1%}")
    print(f"  期望進球: {mc_result['expected_goals']['home']:.2f} - {mc_result['expected_goals']['away']:.2f}")
    
    print("\n" + "=" * 60)
    print("測試完成!")
    print("=" * 60)
