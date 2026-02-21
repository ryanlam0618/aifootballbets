#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚽ 足球分析數學模型整合模組 (v7.0 - 整合版)

整合功能：
- 基礎模型: Poisson, Dixon-Coles, Elo
- v2 功能: Glicko-2, 陣容模型, 蒙地卡羅優化版
- v3 功能: 負二項分布, 動態K因子, 信心度Kelly, Stacking集成

作者: AI Betting System
版本: 7.0
"""

import math
import numpy as np
import pandas as pd
from scipy.stats import poisson, nbinom
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# ============================================
# 第一部分：基礎進球預測模型
# ============================================

class PoissonModel:
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
        over_prob = sum(poisson.sf(max(0, int(line)), self.mu_h + self.mu_a))
        return {"over_2.5": over_prob, "under_2.5": 1 - over_prob}


class NegativeBinomialModel:
    """
    負二項分布進球模型
    
    解決 Poisson 的過離散問題：
    - 足球進球的方差通常 > 均值
    - 負二項分布通過離散參數(alpha)捕捉這種變異
    """
    
    def __init__(self, home_expect: float, away_expect: float, dispersion: float = 1.5):
        """
        Args:
            home_expect: 主隊預期進球
            away_expect: 客隊預期進球
            dispersion: 離散參數 (alpha > 0)
                        alpha = 1: 接近 Poisson
                        alpha > 1: 過離散 (實際足球數據通常 alpha=1.2-2.0)
        """
        self.mu_h = home_expect
        self.mu_a = away_expect
        self.alpha = dispersion
        
    def _calculate_nbinom_params(self, mu: float, alpha: float) -> Tuple[float, float]:
        """轉換為 scipy 參數格式"""
        n = mu / alpha
        p = 1 / (1 + alpha)
        return n, p
    
    def expected_goals(self) -> Tuple[float, float]:
        return self.mu_h, self.mu_a
    
    def calculate_probabilities(self) -> Dict[str, float]:
        """計算主勝/和/客勝概率"""
        prob_home, prob_draw, prob_away = 0, 0, 0
        
        n_h, p_h = self._calculate_nbinom_params(self.mu_h, self.alpha)
        n_a, p_a = self._calculate_nbinom_params(self.mu_a, self.alpha)
        
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
            "dispersion": self.alpha
        }
    
    def variance_ratio(self) -> Dict[str, float]:
        """計算方差比，診斷過離散程度"""
        var_h = self.mu_h + self.alpha * (self.mu_h ** 2)
        var_a = self.mu_a + self.alpha * (self.mu_a ** 2)
        return {
            "home_var_mean_ratio": var_h / self.mu_h,
            "away_var_mean_ratio": var_a / self.mu_a,
            "overdispersed": var_h > self.mu_h * 1.5
        }


class DixonColesModel:
    """
    Dixon-Coles 模型
    
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


class OptimizedDixonColes:
    """優化版 Dixon-Coles 模型 (v2)"""
    def __init__(self, home_expect: float, away_expect: float, rho: float = -0.1):
        self.mu_h = home_expect
        self.mu_a = away_expect
        self.rho = rho

    def tau_correction(self, x: int, y: int) -> float:
        if x == 0 and y == 0: return 1 - (self.mu_h * self.mu_a * self.rho)
        elif x == 0 and y == 1: return 1 + (self.mu_h * self.rho)
        elif x == 1 and y == 0: return 1 + (self.mu_a * self.rho)
        elif x == 1 and y == 1: return 1 - (self.rho)
        else: return 1.0

    def calculate_probabilities(self) -> Dict[str, float]:
        prob_home, prob_draw, prob_away = 0, 0, 0
        for h in range(10):
            for a in range(10):
                base = poisson.pmf(h, self.mu_h) * poisson.pmf(a, self.mu_a)
                correction = self.tau_correction(h, a)
                final = base * correction
                if h > a: prob_home += final
                elif h == a: prob_draw += final
                else: prob_away += final
        
        total = prob_home + prob_draw + prob_away
        return {"dc_home": prob_home/total, "dc_draw": prob_draw/total, "dc_away": prob_away/total}


# ============================================
# 第二部分：評分系統
# ============================================

class EloSystem:
    """基礎 Elo 評分系統"""
    def __init__(self, k_factor: int = 20, base_rating: int = 1500):
        self.k = k_factor
        self.base = base_rating
        self.ratings = {}

    def get_rating(self, team: str) -> float:
        return self.ratings.get(team, self.base)

    def expected_score(self, rating_a: float, rating_b: float) -> float:
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

    def update_ratings(self, home: str, away: str, h_goals: int, a_goals: int):
        if h_goals > a_goals:
            result_h, result_a = 1, 0
        elif h_goals == a_goals:
            result_h, result_a = 0.5, 0.5
        else:
            result_h, result_a = 0, 1

        r_h = self.get_rating(home)
        r_a = self.get_rating(away)
        
        expected_h = self.expected_score(r_h, r_a)
        expected_a = self.expected_score(r_a, r_h)
        
        self.ratings[home] = r_h + self.k * (result_h - expected_h)
        self.ratings[away] = r_a + self.k * (result_a - expected_a)

    def expected_win_prob(self, home: str, away: str) -> float:
        r_h = self.get_rating(home)
        r_a = self.get_rating(away)
        return self.expected_score(r_h, r_a)


class Glicko2System:
    """
    Glicko-2 評分系統
    
    特點：
    - 包含 Rating Deviation (RD) 反映不確定性
    - 更精確的評分更新機制
    - 支持 xG 加權更新
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
        return 1 / math.sqrt(1 + 3 * (phi ** 2) / (math.pi ** 2))

    def _E(self, mu: float, mu_j: float, phi_j: float) -> float:
        return 1 / (1 + math.exp(-self._g(phi_j) * (mu - mu_j)))

    def _scale_down(self, r: float, rd: float) -> Tuple[float, float]:
        return (r - 1500) / 173.7178, rd / 173.7178
    
    def _scale_up(self, mu: float, phi: float) -> Tuple[float, float]:
        return 173.7178 * mu + 1500, 173.7178 * phi

    def update_ratings(self, home: str, away: str, h_goals: int, a_goals: int,
                      xg_home: Optional[float] = None, xg_away: Optional[float] = None):
        """
        更新評分系統
        
        Args:
            home: 主隊名稱
            away: 客隊名稱
            h_goals: 主隊進球
            a_goals: 客隊進球
            xg_home: 主隊 xG (可選，用於加權更新)
            xg_away: 客隊 xG (可選，用於加權更新)
        """
        if h_goals > a_goals: s_h = 1; s_a = 0
        elif h_goals == a_goals: s_h = 0.5; s_a = 0.5
        else: s_h = 0; s_a = 1

        # 如果有 xG 數據，計算加權結果
        if xg_home is not None and xg_away is not None:
            xg_diff = xg_home - xg_away
            goal_diff = h_goals - a_goals
            
            if (xg_diff > 0.3 and s_h == 0):  # xG 領先但輸球
                s_h = 0.3
            elif (xg_diff < -0.3 and s_h == 1):  # xG 落後但贏球
                s_h = 0.7

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
        
        self.ratings[home] = {'rating': final_rh, 'rd': final_rdh, 'vol': self.base_vol}
        self.ratings[away] = {'rating': final_ra, 'rd': final_rda, 'vol': self.base_vol}

    def expected_win_prob(self, home: str, away: str) -> float:
        r_h = self.get_rating(home)['rating']
        r_a = self.get_rating(away)['rating']
        return 1 / (1 + 10 ** ((r_a - r_h) / 400))


class DynamicKEloSystem:
    """
    動態K因子 Elo 評分系統 v3
    
    創新點：
    1. 根據對手實力調整K值
    2. 根據比賽結果意外程度調整K值
    3. 主場優勢動態權重
    """
    
    def __init__(self, base_k: float = 20, home_advantage: float = 100):
        self.base_k = base_k
        self.home_advantage = home_advantage
        self.ratings = {}
        self.rating_history = {}
        
    def get_rating(self, team: str) -> float:
        return self.ratings.get(team, 1500)
    
    def _calculate_dynamic_k(self, team: str, opponent: str, 
                            h_goals: int, a_goals: int, 
                            is_home: bool) -> float:
        """計算動態K值"""
        k = self.base_k
        
        # 1. 對手實力因子
        opp_rating = self.get_rating(opponent)
        rating_diff = abs(self.get_rating(team) - opp_rating)
        f_opponent = 1 + (rating_diff / 2000)
        
        # 2. 意外因子
        expected = self.expected_score(
            self.get_rating(team) + (self.home_advantage if is_home else 0),
            self.get_rating(opponent) + (self.home_advantage if not is_home else 0)
        )
        actual = 1 if (is_home and h_goals > a_goals) or (not is_home and a_goals > h_goals) else (0.5 if h_goals == a_goals else 0)
        surprise = abs(actual - expected)
        f_upset = 1 - (surprise * 0.4)
        
        # 3. 主場因子
        f_home = 1.1 if is_home else 1.0
        
        return k * f_opponent * f_upset * f_home
    
    def expected_score(self, rating_a: float, rating_b: float) -> float:
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
        
        k_h = self._calculate_dynamic_k(home, away, h_goals, a_goals, True)
        k_a = self._calculate_dynamic_k(away, home, a_goals, h_goals, False)
        
        r_h = self.get_rating(home)
        r_a = self.get_rating(away)
        
        expected_h = self.expected_score(r_h + self.home_advantage, r_a)
        expected_a = self.expected_score(r_a, r_h + self.home_advantage)
        
        # xG加權調整
        if xg_home is not None and xg_away is not None:
            perf_h = (xg_home - xg_away) - (h_goals - a_goals)
            result_h = max(0, min(1, result_h - perf_h * 0.1))
            result_a = max(0, min(1, result_a + perf_h * 0.1))
        
        self.ratings[home] = r_h + k_h * (result_h - expected_h)
        self.ratings[away] = r_a + k_a * (result_a - expected_a)
    
    def expected_win_prob(self, home: str, away: str) -> float:
        r_h = self.get_rating(home)
        r_a = self.get_rating(away)
        return self.expected_score(r_h + self.home_advantage, r_a)


# ============================================
# 第三部分：蒙地卡羅模擬
# ============================================

class MonteCarloSimulator:
    """蒙地卡羅模擬器 (基礎版)"""
    def __init__(self, home_expect: float, away_expect: float, iterations: int = 10000):
        self.mu_h = home_expect
        self.mu_a = away_expect
        self.iterations = iterations

    def run_simulation(self) -> Dict:
        h_goals = np.random.poisson(self.mu_h, self.iterations)
        a_goals = np.random.poisson(self.mu_a, self.iterations)
        
        home_wins = np.sum(h_goals > a_goals)
        draws = np.sum(h_goals == a_goals)
        away_wins = np.sum(h_goals < a_goals)
        over_2_5 = np.sum((h_goals + a_goals) > 2.5)
        
        diff = h_goals - a_goals
        ah_probs = {}
        for line in [-1.5, -1.0, -0.5, 0, 0.5, 1.0, 1.5]:
            wins = np.sum((diff + line) > 0)
            ah_probs[f"AH {line:+.1f}"] = wins / self.iterations

        return {
            "mc_home_win": home_wins / self.iterations,
            "mc_draw": draws / self.iterations,
            "mc_away_win": away_wins / self.iterations,
            "mc_over_2.5": over_2_5 / self.iterations,
            "ah_probs": ah_probs
        }


class MonteCarloSimulatorV3:
    """
    蒙地卡羅模擬器 v3 (整合版)
    
    改進：
    1. 支持 Poisson 和負二項分布
    2. 多種投注市場
    3. 置信區間
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
        """使用 Gamma-Poisson 混合物生成負二項分布樣本"""
        if dispersion <= 0.05:
            return np.random.poisson(mu, n_samples)
        
        var = mu + dispersion * (mu ** 2)
        shape = (mu ** 2) / (var - mu + 0.001)
        scale = var / (mu + 0.001)
        shape = max(1.0, shape)
        
        lambdas = np.random.gamma(shape, scale, n_samples)
        lambdas = np.clip(lambdas, 0.01, mu * 10)
        
        samples = np.random.poisson(lambdas)
        samples = np.clip(samples, 0, 15)
        
        return samples
        
    def run_simulation(self) -> Dict:
        if self.use_nbinom:
            h_goals = self._generate_nbinom_samples(self.mu_h, self.iterations, self.dispersion)
            a_goals = self._generate_nbinom_samples(self.mu_a, self.iterations, self.dispersion)
        else:
            h_goals = np.random.poisson(self.mu_h, self.iterations)
            a_goals = np.random.poisson(self.mu_a, self.iterations)
        
        h_goals = np.asarray(h_goals, dtype=np.float64)
        a_goals = np.asarray(a_goals, dtype=np.float64)
        
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
        
        # 分佈
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
# 第四部分：陣容模型
# ============================================

class LineupModel:
    """
    基於球員評分的預測模型
    """
    def __init__(self, lineup_data: dict):
        self.data = lineup_data

    def calculate_strength(self) -> Tuple[float, float]:
        if not self.data: return None, None
        
        home_team = self.data.get('home_team', {})
        away_team = self.data.get('away_team', {})
        
        def get_team_score(team_obj):
            starters = team_obj.get('starters', [])
            if not starters: return 0
            
            total_rating = 0
            count = 0
            for p in starters:
                try:
                    r = float(p.get('rating', 0))
                    if r > 0:
                        total_rating += r
                        count += 1
                except: continue
            
            return total_rating / count if count > 0 else 0

        h_score = get_team_score(home_team)
        a_score = get_team_score(away_team)
        
        return h_score, a_score

    def predict_win_prob(self) -> float:
        h_score, a_score = self.calculate_strength()
        if not h_score or not a_score: return 0.5 
        
        diff = h_score - a_score
        adjusted_diff = diff + 0.2
        
        win_prob = 1 / (1 + math.exp(-1.5 * adjusted_diff))
        return win_prob


# ============================================
# 第五部分：信心度 Kelly 資金管理
# ============================================

@dataclass
class KellyResult:
    """Kelly計算結果"""
    stake: float           # 建議投注金額
    kelly_pct: float       # Kelly百分比
    ev: float              # 期望值
    edge: float            # 優勢
    confidence_adj: float  # 信心度調整
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
    信心度調整 Kelly 資金管理
    
    創新點：
    1. 根據模型信心度調整Kelly分數
    2. 動態分數因子（根據歷史表現）
    3. 馬爾可夫鏈風險狀態追蹤
    """
    
    def __init__(self, 
                 base_fraction: float = 0.5,
                 max_fraction: float = 1.0,
                 min_edge: float = 0.05,
                 initial_bankroll: float = 1000):
        self.base_fraction = base_fraction
        self.max_fraction = max_fraction
        self.min_edge = min_edge
        self.bankroll = initial_bankroll
        
        self.bet_history = []
        self.win_history = []
        self.profit_history = []
        
        self.state = 'normal'
        self.max_drawdown = 0.2
        self.peak_bankroll = initial_bankroll
    
    def _calculate_confidence(self, model_prob: float, market_prob: float,
                             model_uncertainty: float = 0.1) -> float:
        """計算信心度調整因子"""
        raw_confidence = 0.5
        
        edge = model_prob - market_prob
        edge_confidence = min(1.0, max(0.0, 0.5 + edge * 3))
        
        uncertainty_penalty = max(0.0, 1.0 - model_uncertainty * 5)
        
        if len(self.win_history) >= 20:
            win_rate = sum(self.win_history[-20:]) / 20
            hist_confidence = min(1.2, max(0.8, win_rate / 0.5))
        else:
            hist_confidence = 1.0
        
        confidence = raw_confidence * edge_confidence * uncertainty_penalty * hist_confidence
        return min(1.0, max(0.2, confidence))
    
    def _calculate_performance_factor(self) -> float:
        """計算表現因子"""
        if len(self.profit_history) < 10:
            return 1.0
        
        recent_profit = sum(self.profit_history[-10:]) / 10
        volatility = np.std(self.profit_history[-20:]) if len(self.profit_history) >= 20 else 1
        
        if volatility == 0:
            return 1.0
        
        sharpe_like = recent_profit / (volatility + 0.01)
        factor = 1 + sharpe_like * 0.2
        
        return min(1.5, max(0.5, factor))
    
    def _update_state(self) -> str:
        """更新馬爾可夫風險狀態"""
        current_drawdown = (self.peak_bankroll - self.bankroll) / self.peak_bankroll
        
        if current_drawdown > self.max_drawdown * 0.7:
            self.state = 'critical'
        elif current_drawdown > self.max_drawdown * 0.4:
            self.state = 'warning'
        else:
            self.state = 'normal'
        
        if self.bankroll > self.peak_bankroll:
            self.peak_bankroll = self.bankroll
        
        return self.state
    
    def _state_risk_multiplier(self) -> float:
        multipliers = {'normal': 1.0, 'warning': 0.5, 'critical': 0.25}
        return multipliers.get(self.state, 1.0)
    
    def calculate(self, prob: float, odds: float, confidence: float = 0.5,
                  model_uncertainty: float = 0.1, market_prob: Optional[float] = None) -> KellyResult:
        """計算信心度調整後的Kelly投注"""
        if prob <= 0 or odds <= 1:
            return KellyResult(0, 0, 0, 0, 0, 'low')
        
        if market_prob is None:
            market_prob = 1 / odds
        
        b = odds - 1
        q = 1 - prob
        raw_kelly = (b * prob - q) / b
        
        if raw_kelly <= 0:
            return KellyResult(0, 0, -q, 0, confidence, 'low')
        
        ev = (prob * b) - q
        edge = prob - market_prob
        
        confidence_adj = self._calculate_confidence(prob, market_prob, model_uncertainty)
        perf_factor = self._calculate_performance_factor()
        
        self._update_state()
        state_multiplier = self._state_risk_multiplier()
        
        final_kelly = (raw_kelly * confidence_adj * perf_factor * 
                      state_multiplier * self.base_fraction)
        
        final_kelly = min(final_kelly, self.max_fraction * raw_kelly)
        
        stake = self.bankroll * final_kelly
        
        if final_kelly < 0.02:
            risk = 'low'
        elif final_kelly < 0.05:
            risk = 'medium'
        else:
            risk = 'high'
        
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
        """更新投注結果"""
        if won:
            profit = stake * (odds - 1)
        else:
            profit = -stake
        
        self.bankroll += profit
        self.bet_history.append({'won': won, 'profit': profit})
        self.win_history.append(1 if won else 0)
        self.profit_history.append(profit)
        
        if len(self.win_history) > 50:
            self.win_history.pop(0)
            self.profit_history.pop(0)
        
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


# ============================================
# 工具函數
# ============================================

def calculate_kelly_stake(bankroll: float, prob: float, odds: float, 
                          fraction: float = 0.75, min_edge: float = 0.09) -> Dict:
    """
    計算Kelly投注金額（簡易版）
    
    Args:
        bankroll: 總資金
        prob: 預測概率
        odds: 赔率
        fraction: Kelly分數 (預設0.75 = 半 Kelly)
        min_edge: 最小優勢門檻
    
    Returns:
        dict: 包含 stake, kelly_pct, ev, edge
    """
    if prob <= 0 or odds <= 1:
        return {'stake': 0, 'kelly_pct': 0, 'ev': 0, 'edge': 0, 'recommended': False}
    
    market_prob = 1 / odds
    edge = prob - market_prob
    
    if edge < min_edge:
        return {
            'stake': 0,
            'kelly_pct': 0,
            'ev': prob * (odds - 1) - (1 - prob),
            'edge': edge,
            'recommended': False,
            'reason': f'優勢不足 (edge: {edge:.1%} < {min_edge:.1%})'
        }
    
    b = odds - 1
    q = 1 - prob
    kelly = (b * prob - q) / b
    
    if kelly <= 0:
        return {'stake': 0, 'kelly_pct': 0, 'ev': 0, 'edge': edge, 'recommended': False}
    
    kelly_pct = kelly * fraction
    stake = bankroll * kelly_pct
    ev = prob * b - q
    
    return {
        'stake': round(stake, 2),
        'kelly_pct': round(kelly_pct * 100, 2),
        'ev': round(ev, 4),
        'edge': round(edge, 4),
        'recommended': True,
        'odds': odds,
        'prob': round(prob, 4),
        'market_prob': round(market_prob, 4)
    }


# ============================================
# 主程式入口
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("⚽ 足球分析數學模型整合版 v7.0 - 測試")
    print("=" * 60)
    
    # 1. 測試負二項分布
    print("\n[1] 負二項分布測試")
    nb_model = NegativeBinomialModel(1.5, 1.0)
    nb_probs = nb_model.calculate_probabilities()
    print(f"  主勝: {nb_probs['home_win']:.1%}")
    print(f"  和局: {nb_probs['draw']:.1%}")
    print(f"  客勝: {nb_probs['away_win']:.1%}")
    
    # 2. 測試 Glicko-2
    print("\n[2] Glicko-2 系統測試")
    glicko = Glicko2System()
    glicko.update_ratings("TeamA", "TeamB", 2, 1)
    glicko.update_ratings("TeamA", "TeamC", 1, 3)
    print(f"  TeamA Rating: {glicko.get_rating('TeamA')['rating']:.1f}")
    print(f"  TeamB Rating: {glicko.get_rating('TeamB')['rating']:.1f}")
    
    # 3. 測試信心度Kelly
    print("\n[3] 信心度Kelly測試")
    kelly = ConfidenceKelly(base_fraction=0.5)
    result = kelly.calculate(
        prob=0.55,
        odds=2.0,
        confidence=0.7,
        model_uncertainty=0.1,
        market_prob=0.5
    )
    print(f"  Kelly百分比: {result.kelly_pct:.2%}")
    print(f"  期望值: {result.ev:.3f}")
    print(f"  優勢: {result.edge:.3f}")
    print(f"  風險等級: {result.risk_level}")
    
    # 4. 測試蒙地卡羅V3
    print("\n[4] 蒙地卡羅模擬V3測試")
    mc = MonteCarloSimulatorV3(1.5, 1.0, iterations=5000)
    mc_result = mc.run_simulation()
    print(f"  主勝: {mc_result['mc_home_win']:.1%}")
    print(f"  期望進球: {mc_result['expected_goals']['home']:.2f} - {mc_result['expected_goals']['away']:.2f}")
    
    print("\n" + "=" * 60)
    print("測試完成!")
    print("=" * 60)
