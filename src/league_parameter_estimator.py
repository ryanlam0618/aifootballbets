#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
聯賽參數估計器
根據歷史數據動態估計各聯賽的模型參數

功能：
1. 離散參數 α 估計（負二項分布）
2. Dixon-Coles ρ 估計
3. xG 衰減率估計
4. Glicko-2 τ 估計

Author: AI Assistant
Date: 2026-02-21
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize
from typing import Dict, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 默認聯賽參數（當數據不足時使用）
# ============================================================

DEFAULT_LEAGUE_PARAMS = {
    # 五大聯賽
    'Premier League': {
        'alpha': 1.35,  # 離散參數
        'rho': -0.12,   # Dixon-Coles 相關係數
        'decay_rate': 0.08,  # xG 衰減率
        'tau': 0.45,    # Glicko-2 波動性
        'home_advantage': 0.12,
    },
    'La Liga': {
        'alpha': 1.40,
        'rho': -0.14,
        'decay_rate': 0.09,
        'tau': 0.48,
        'home_advantage': 0.11,
    },
    'Bundesliga': {
        'alpha': 1.25,
        'rho': -0.10,
        'decay_rate': 0.07,
        'tau': 0.42,
        'home_advantage': 0.10,
    },
    'Serie A': {
        'alpha': 1.38,
        'rho': -0.13,
        'decay_rate': 0.085,
        'tau': 0.46,
        'home_advantage': 0.11,
    },
    'Ligue 1': {
        'alpha': 1.42,
        'rho': -0.15,
        'decay_rate': 0.10,
        'tau': 0.50,
        'home_advantage': 0.10,
    },
    # 亞洲聯賽
    'J1 League': {
        'alpha': 1.30,
        'rho': -0.11,
        'decay_rate': 0.08,
        'tau': 0.44,
        'home_advantage': 0.09,
    },
    'K League': {
        'alpha': 1.28,
        'rho': -0.10,
        'decay_rate': 0.075,
        'tau': 0.43,
        'home_advantage': 0.10,
    },
    # 其他
    'default': {
        'alpha': 1.50,
        'rho': -0.13,
        'decay_rate': 0.10,
        'tau': 0.50,
        'home_advantage': 0.10,
    }
}


class LeagueParameterEstimator:
    """
    聯賽參數估計器
    
    從歷史數據中估計各聯賽的模型參數
    """
    
    def __init__(self, min_matches: int = 50):
        """
        Args:
            min_matches: 最小比赛数才进行估计，否则使用默认值
        """
        self.min_matches = min_matches
        self._cache = {}
        self._estimated = False
    
    def fit(self, df: pd.DataFrame) -> Dict:
        """
        從數據框估計參數
        
        必須包含以下列：
        - league: 聯賽名稱
        - home_goals: 主隊進球
        - away_goals: 客隊進球
        - date: 比賽日期（可選，用於時間衰減）
        - xg: 主隊 xG（可選）
        - xga: 客隊 xG（可選）
        """
        results = {}
        
        for league in df['league'].unique():
            league_df = df[df['league'] == league].copy()
            
            if len(league_df) < self.min_matches:
                # 數據不足，使用默認值
                results[league] = self._get_default_params(league)
                continue
            
            # 估計各參數
            try:
                alpha = self._estimate_dispersion(league_df)
            except:
                alpha = DEFAULT_LEAGUE_PARAMS['default']['alpha']
            
            try:
                rho = self._estimate_rho(league_df)
            except:
                rho = DEFAULT_LEAGUE_PARAMS['default']['rho']
            
            try:
                decay_rate = self._estimate_decay_rate(league_df)
            except:
                decay_rate = DEFAULT_LEAGUE_PARAMS['default']['decay_rate']
            
            try:
                tau = self._estimate_tau(league_df)
            except:
                tau = DEFAULT_LEAGUE_PARAMS['default']['tau']
            
            try:
                home_adv = self._estimate_home_advantage(league_df)
            except:
                home_adv = DEFAULT_LEAGUE_PARAMS['default']['home_advantage']
            
            results[league] = {
                'alpha': alpha,
                'rho': rho,
                'decay_rate': decay_rate,
                'tau': tau,
                'home_advantage': home_adv,
                'n_matches': len(league_df)
            }
        
        self._cache = results
        self._estimated = True
        return results
    
    def _estimate_dispersion(self, df: pd.DataFrame) -> float:
        """
        估計負二項分布的離散參數 α
        
        使用矩估計法：
        α = (Var - μ) / μ²
        
        同時也考慮主客場分開估計
        """
        # 主場進球
        home_goals = df['home_goals'].dropna().values
        if len(home_goals) < 10:
            return DEFAULT_LEAGUE_PARAMS['default']['alpha']
        
        home_mu = np.mean(home_goals)
        home_var = np.var(home_goals)
        
        # 客場進球
        away_goals = df['away_goals'].dropna().values
        away_mu = np.mean(away_goals)
        away_var = np.var(away_goals)
        
        # 估計 α（過離散參數）
        # Var = μ + α * μ² => α = (Var - μ) / μ²
        if home_mu > 0:
            alpha_home = max(0.1, (home_var - home_mu) / (home_mu ** 2))
        else:
            alpha_home = 1.0
        
        if away_mu > 0:
            alpha_away = max(0.1, (away_var - away_mu) / (away_mu ** 2))
        else:
            alpha_away = 1.0
        
        # 取平均並限制範圍
        alpha = (alpha_home + alpha_away) / 2
        alpha = max(0.5, min(3.0, alpha))  # 限制在合理範圍
        
        return alpha
    
    def _estimate_rho(self, df: pd.DataFrame) -> float:
        """
        估計 Dixon-Coles ρ 參數
        
        ρ 控制低比分（如 0-0, 1-1）的相關性
        通常為負值（表示低比分比 Poisson 預測的更常見）
        
        使用優化方法：最小化預測概率與實際結果的偏差
        """
        # 提取比分數據
        scores = df[['home_goals', 'away_goals']].dropna()
        
        if len(scores) < 50:
            return DEFAULT_LEAGUE_PARAMS['default']['rho']
        
        home_goals = scores['home_goals'].values
        away_goals = scores['away_goals'].values
        
        # 計算 0-0, 1-1, 0-1, 1-0 的實際頻率
        total = len(scores)
        freq_00 = np.sum((home_goals == 0) & (away_goals == 0)) / total
        freq_11 = np.sum((home_goals == 1) & (away_goals == 1)) / total
        freq_01 = np.sum((home_goals == 0) & (away_goals == 1)) / total
        freq_10 = np.sum((home_goals == 1) & (away_goals == 0)) / total
        
        # 計算平均預期進球
        mu_home = np.mean(home_goals)
        mu_away = np.mean(away_goals)
        
        # 使用網格搜索找最優 ρ
        def objective(rho):
            # Poisson 預測
            p00_expected = stats.poisson.pmf(0, mu_home) * stats.poisson.pmf(0, mu_away)
            p11_expected = stats.poisson.pmf(1, mu_home) * stats.poisson.pmf(1, mu_away)
            p01_expected = stats.poisson.pmf(0, mu_home) * stats.poisson.pmf(1, mu_away)
            p10_expected = stats.poisson.pmf(1, mu_home) * stats.poisson.pmf(0, mu_away)
            
            # Dixon-Coles 校正
            if p00_expected > 0:
                p00_adj = p00_expected * (1 - mu_home * mu_away * rho)
            else:
                p00_adj = p00_expected
            
            if p11_expected > 0:
                p11_adj = p11_expected * (1 - rho)
            else:
                p11_adj = p11_expected
            
            if p01_expected > 0:
                p01_adj = p01_expected * (1 + mu_home * rho)
            else:
                p01_adj = p01_expected
            
            if p10_expected > 0:
                p10_adj = p10_expected * (1 + mu_away * rho)
            else:
                p10_adj = p10_expected
            
            # 計算誤差
            error = ((freq_00 - p00_adj) ** 2 + 
                    (freq_11 - p11_adj) ** 2 + 
                    (freq_01 - p01_adj) ** 2 + 
                    (freq_10 - p10_adj) ** 2)
            
            return error
        
        # 搜索最優 rho
        from scipy.optimize import minimize_scalar
        result = minimize_scalar(objective, bounds=(-0.5, 0.1), method='bounded')
        
        rho = result.x
        rho = max(-0.3, min(0.1, rho))  # 限制範圍
        
        return rho
    
    def _estimate_decay_rate(self, df: pd.DataFrame) -> float:
        """
        估計 xG 衰減率
        
        通過擬合：指數衰減模型
        近期比賽權重更高
        """
        if 'date' not in df.columns:
            return DEFAULT_LEAGUE_PARAMS['default']['decay_rate']
        
        # 嘗試解析日期
        try:
            df = df.copy()
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date'])
            
            if len(df) < 50:
                return DEFAULT_LEAGUE_PARAMS['default']['decay_rate']
            
            # 按日期排序
            df = df.sort_values('date')
            
            # 計算時間跨度
            date_range = (df['date'].max() - df['date'].min()).days
            
            if date_range < 30:  # 數據太少
                return DEFAULT_LEAGUE_PARAMS['default']['decay_rate']
            
            # 使用簡單方法：根據數據時間跨度估算衰減率
            # 數據跨度越大，衰減率應該越小
            # 經驗公式：decay_rate ≈ 1 / (平均比賽間隔天數 * 5)
            
            n_games = len(df)
            avg_days_between = date_range / max(n_games, 1)
            
            # 推估算法：讓近期數據佔 70% 權重
            # exp(-decay * days) ≈ 0.7 when days = avg_days_between * 3
            # decay ≈ -ln(0.7) / (avg_days_between * 3)
            decay_rate = -np.log(0.7) / (avg_days_between * 3)
            
            # 限制範圍
            decay_rate = max(0.03, min(0.2, decay_rate))
            
            return decay_rate
            
        except Exception:
            return DEFAULT_LEAGUE_PARAMS['default']['decay_rate']
    
    def _estimate_tau(self, df: pd.DataFrame) -> float:
        """
        估計 Glicko-2 τ 參數（系統波動性）
        
        使用比分差異的方差來估計
        """
        scores = df[['home_goals', 'away_goals']].dropna()
        
        if len(scores) < 50:
            return DEFAULT_LEAGUE_PARAMS['default']['tau']
        
        # 計算比分差異
        goal_diff = scores['home_goals'].values - scores['away_goals'].values
        
        # 比分差異的標準差
        diff_std = np.std(goal_diff)
        
        # τ 與波動性成正比
        # 轉換到合理範圍：0.3 - 0.7
        tau = 0.3 + (diff_std - 1.0) * 0.1
        tau = max(0.3, min(0.7, tau))
        
        return tau
    
    def _estimate_home_advantage(self, df: pd.DataFrame) -> float:
        """
        估計主場優勢
        
        主場勝率 - 客場勝率
        """
        scores = df[['home_goals', 'away_goals']].dropna()
        
        if len(scores) < 10:
            return DEFAULT_LEAGUE_PARAMS['default']['home_advantage']
        
        # 計算主場/客場勝率
        home_wins = np.sum(scores['home_goals'] > scores['away_goals'])
        away_wins = np.sum(scores['home_goals'] < scores['away_goals'])
        draws = np.sum(scores['home_goals'] == scores['away_goals'])
        
        home_win_rate = home_wins / len(scores)
        away_win_rate = away_wins / len(scores)
        
        # 主場優勢 = 主場勝率 - 客場勝率（修正後）
        home_adv = home_win_rate - (1 - away_win_rate) / 2
        
        # 限制範圍
        home_adv = max(0.05, min(0.20, home_adv))
        
        return home_adv
    
    def _get_default_params(self, league: str) -> Dict:
        """獲取默認參數"""
        # 嘗試精確匹配
        if league in DEFAULT_LEAGUE_PARAMS:
            return DEFAULT_LEAGUE_PARAMS[league].copy()
        
        # 嘗試部分匹配
        league_lower = league.lower()
        for key, params in DEFAULT_LEAGUE_PARAMS.items():
            if key != 'default' and key.lower() in league_lower:
                return params.copy()
        
        # 返回默認值
        return DEFAULT_LEAGUE_PARAMS['default'].copy()
    
    def get_params(self, league: str) -> Dict:
        """
        獲取聯賽參數
        
        如果已經進行過估計，返回估計值
        否則返回默認值
        """
        if self._estimated and league in self._cache:
            return self._cache[league]
        
        return self._get_default_params(league)
    
    def get_all_params(self) -> Dict:
        """獲取所有參數"""
        if self._estimated:
            return self._cache.copy()
        else:
            return DEFAULT_LEAGUE_PARAMS.copy()


# ============================================================
# 便捷函數
# ============================================================

# 全局估計器實例
_global_estimator = None


def fit_league_parameters(df: pd.DataFrame, min_matches: int = 50) -> Dict:
    """
    從數據框擬合聯賽參數
    
    Args:
        df: 包含 league, home_goals, away_goals 等列的 DataFrame
        min_matches: 最小比赛数
    
    Returns:
        Dict: {league_name: {alpha, rho, decay_rate, tau, home_advantage}}
    """
    global _global_estimator
    _global_estimator = LeagueParameterEstimator(min_matches=min_matches)
    return _global_estimator.fit(df)


def get_league_parameters(league: str) -> Dict:
    """
    獲取特定聯賽的參數
    
    Args:
        league: 聯賽名稱
    
    Returns:
        Dict: 參數字典
    """
    global _global_estimator
    
    if _global_estimator is None:
        # 返回默認值
        if league in DEFAULT_LEAGUE_PARAMS:
            return DEFAULT_LEAGUE_PARAMS[league].copy()
        return DEFAULT_LEAGUE_PARAMS['default'].copy()
    
    return _global_estimator.get_params(league)


# ============================================================
# 測試
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("聯賽參數估計器測試")
    print("=" * 60)
    
    # 測試默認參數
    leagues = ['Premier League', 'La Liga', 'J1 League', 'Unknown League']
    
    for league in leagues:
        params = get_league_parameters(league)
        print(f"\n{league}:")
        print(f"  α (離散): {params['alpha']:.3f}")
        print(f"  ρ (DC): {params['rho']:.3f}")
        print(f"  衰減率: {params['decay_rate']:.3f}")
        print(f"  τ (Glicko-2): {params['tau']:.3f}")
        print(f"  主場優勢: {params['home_advantage']:.1%}")
    
    print("\n" + "=" * 60)
    print("測試完成!")
    print("=" * 60)
