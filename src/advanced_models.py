"""
============================================================
高級數學模型改進模組
============================================================
1. xG滾動窗口優化 - 指數衰減加權
2. 傷停影響量化 - 球員市場價值調整
3. 貝葉斯進球模型 - 完全概率化不確定性估計
4. LSTM時序模型 - 捕捉球隊狀態變化
5. Reinforcement Learning - 自動優化投注策略

Author: AI Assistant
Date: 2026-02-05
============================================================
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import beta as beta_func, gammaln
from scipy.stats import gamma as gamma_dist, norm as normal_dist
from typing import Dict, List, Tuple, Optional, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import math
import warnings
warnings.filterwarnings('ignore')

# LSTM 需要 TensorFlow/Keras，如果沒有則回退
try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential, Model
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Input, BatchNormalization, Attention
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
    from tensorflow.keras.optimizers import Adam
    HAS_TENSORFLOW = True
except ImportError:
    HAS_TENSORFLOW = False
    # 定義 Model 為 NoneType
    Model = type('Model', (), {})


# ============================================================
# 第一部分：指數衰減加權 xG 滾動窗口
# ============================================================

class ExponentialDecayXGForecaster:
    """
    指數衰減加權 xG 預測模型
    
    特點：
    - 近期比賽權重更高
    - 可自定義衰減係數 (alpha)
    - 支持主客場分開計算
    - 自動適應球隊風格變化
    """
    
    def __init__(self, 
                 decay_rate: float = 0.1,       # 衰減率 (0.05-0.2)
                 halflife: Optional[float] = None,  # 半衰期 (替代 decay_rate)
                 min_games: int = 3,           # 最小比賽數
                 use_home_away: bool = True,   # 主客場分開計算
                 recency_weight: float = 1.0): # 近期權重放大
    
        self.decay_rate = decay_rate
        self.halflife = halflife or np.log(2) / decay_rate
        self.min_games = min_games
        self.use_home_away = use_home_away
        self.recency_weight = recency_weight
        
        # 球隊歷史數據
        self.team_data = {}  # {team_name: {home: [], away: [], dates: []}}
        
    def _calculate_weight(self, days_ago: float) -> float:
        """計算指數衰減權重"""
        weight = np.exp(-self.decay_rate * days_ago / 7)  # 以週為單位
        return weight
    
    def add_match(self, team: str, xg: float, is_home: bool, date, goals_scored: int = None):
        """添加一場比賽數據"""
        if team not in self.team_data:
            self.team_data[team] = {'home': [], 'away': [], 'dates': []}
        
        entry = {
            'xg': xg,
            'goals': goals_scored if goals_scored is not None else xg,
            'is_home': is_home,
            'date': pd.Timestamp(date) if not isinstance(date, pd.Timestamp) else date
        }
        
        if is_home:
            self.team_data[team]['home'].append(entry)
        else:
            self.team_data[team]['away'].append(entry)
        
        self.team_data[team]['dates'].append(entry['date'])
    
    def _calculate_weighted_avg(self, matches: List[dict], reference_date) -> Tuple[float, float, float]:
        """計算加權平均值"""
        if not matches or len(matches) < self.min_games:
            return None, None, 0
        
        weights = []
        values = []
        ref = pd.Timestamp(reference_date)
        
        for m in matches:
            days_ago = (ref - m['date']).days
            weight = self._calculate_weight(days_ago)
            
            # 近期放大
            if days_ago < 14:  # 兩週內的比賽
                weight *= self.recency_weight
            
            weights.append(weight)
            values.append(m['xg'])
        
        weights = np.array(weights)
        values = np.array(values)
        
        # 正規化權重
        weights = weights / weights.sum()
        
        weighted_avg = np.sum(weights * values)
        
        # 計算標準誤差 (考慮權重)
        variance = np.sum(weights * (values - weighted_avg) ** 2)
        std_err = np.sqrt(variance) / np.sqrt(len(values))
        
        return weighted_avg, std_err, len(values)
    
    def get_team_xg(self, team: str, reference_date, is_home: bool = True) -> Dict:
        """獲取球隊 xG 預測"""
        if team not in self.team_data:
            return {'xg': None, 'std': None, 'n_games': 0}
        
        if self.use_home_away:
            matches = self.team_data[team]['home'] if is_home else self.team_data[team]['away']
        else:
            matches = self.team_data[team]['home'] + self.team_data[team]['away']
        
        xg, std, n = self._calculate_weighted_avg(matches, reference_date)
        
        return {'xg': xg, 'std': std, 'n_games': n}
    
    def predict_match(self, home_team: str, away_team: str, reference_date,
                      home_advantage: float = 0.1) -> Dict:
        """預測比賽進球"""
        home_xg = self.get_team_xg(home_team, reference_date, is_home=True)
        away_xg = self.get_team_xg(away_team, reference_date, is_home=False)
        
        # 考慮主場優勢
        adjusted_home_xg = home_xg['xg'] + home_advantage if home_xg['xg'] else None
        
        return {
            'home_xg': adjusted_home_xg,
            'away_xg': away_xg['xg'],
            'home_std': home_xg['std'],
            'away_std': away_xg['std'],
            'n_games': (home_xg['n_games'], away_xg['n_games']),
            'combined_xg': (adjusted_home_xg or 1.2, away_xg['xg'] or 1.0)
        }


# ============================================================
# 第二部分：傷停影響量化 - 球員市場價值調整
# ============================================================

@dataclass
class Player:
    """球員數據類"""
    name: str
    position: str  # 'GK', 'DEF', 'MID', 'FWD'
    market_value_eur: float  # 市場價值（百萬歐元）
    minutes_played_avg: float  # 平均上場時間
    xg_contribution: float  # 場均 xG 貢獻
    xga_prevention: float  # 場均 xGA 預防 (後衛/門將)
    importance_score: float = 0.0  # 重要性分數
    
    def __post_init__(self):
        # 根據位置和市場價值計算重要性
        position_weight = {'GK': 0.8, 'DEF': 0.9, 'MID': 1.0, 'FWD': 1.1}
        weight = position_weight.get(self.position, 1.0)
        self.importance_score = self.market_value_eur * weight * (
            self.minutes_played_avg / 90 * 
            (self.xg_contribution + 0.5)
        )


class InjuryImpactModel:
    """
    傷停影響量化模型
    
    特點：
    - 根據球員市場價值調整影響權重
    - 考慮位置重要性
    - 計算對手對應位置的強弱
    - 返回影響係數 (0-1)
    """
    
    def __init__(self,
                 value_threshold_millions: float = 5.0,  # 關鍵球員門檻
                 position_weights: Dict[str, float] = None,
                 default_xg_impact: float = 0.15):       # 預設替補影響
    
        if position_weights is None:
            position_weights = {
                'GK': 0.25,    # 門將影響較大
                'DEF': 0.30,   # 後防線核心
                'MID': 0.35,   # 中場發電機
                'FWD': 0.40    # 前鋒決定力強
            }
        
        self.position_weights = position_weights
        self.value_threshold = value_threshold_millions
        self.default_impact = default_xg_impact
        
        # 球員數據庫
        self.players_db = {}  # {team: {player_name: Player}}
    
    def add_player(self, team: str, player: Player):
        """添加球員到數據庫"""
        if team not in self.players_db:
            self.players_db[team] = {}
        self.players_db[team][player.name] = player
    
    def add_injury(self, team: str, player_name: str, severity: float = 1.0,
                   expected_absence_matches: int = 3):
        """記錄傷病情況"""
        if team not in self.injuries:
            self.injuries[team] = []
        
        self.injuries[team].append({
            'player': player_name,
            'severity': severity,
            'expected_absence': expected_absence_matches,
            'timestamp': pd.Timestamp.now()
        })
    
    def calculate_team_impact(self, team: str, opponent: str = None) -> Dict:
        """計算球隊傷停影響"""
        if not hasattr(self, 'injuries'):
            self.injuries = {team: [] for team in self.players_db}
        
        injuries = self.injuries.get(team, [])
        
        if not injuries:
            return {
                'total_impact': 0.0,
                'xg_impact': 0.0,
                'xga_impact': 0.0,
                'key_players_lost': [],
                'position_breakdown': {pos: 0.0 for pos in ['GK', 'DEF', 'MID', 'FWD']}
            }
        
        total_impact = 0.0
        xg_impact = 0.0
        xga_impact = 0.0
        key_players_lost = []
        position_breakdown = {pos: 0.0 for pos in ['GK', 'DEF', 'MID', 'FWD']}
        
        for injury in injuries:
            player_name = injury['player']
            severity = injury['severity']
            
            # 查找球員
            player = None
            for t in self.players_db:
                if player_name in self.players_db[t]:
                    player = self.players_db[t][player_name]
                    break
            
            if player:
                # 計算影響
                position_weight = self.position_weights.get(player.position, 0.3)
                value_factor = min(1.0, player.market_value_eur / (self.value_threshold * 2))
                
                player_impact = (position_weight * 0.6 + value_factor * 0.4) * severity
                
                # 累加影響
                total_impact += player_impact * severity
                xg_impact += player.xg_contribution * player_impact
                xga_impact += player.xga_prevention * player_impact
                
                position_breakdown[player.position] += player_impact
                
                if value_factor > 0.5:  # 關鍵球員
                    key_players_lost.append({
                        'name': player_name,
                        'value': player.market_value_eur,
                        'impact': player_impact
                    })
            else:
                # 未知球員使用預設影響
                total_impact += self.default_impact * severity
        
        # 正規化影響 (0-1)
        total_impact = min(1.0, total_impact)
        xg_impact = min(1.0, xg_impact)
        xga_impact = min(1.0, xga_impact)
        
        return {
            'total_impact': total_impact,
            'xg_impact': xg_impact,
            'xga_impact': xga_impact,
            'key_players_lost': key_players_lost,
            'position_breakdown': position_breakdown,
            'n_injuries': len(injuries)
        }
    
    def calculate_match_impact(self, home_team: str, away_team: str) -> Tuple[Dict, Dict]:
        """計算比賽雙方的傷停影響"""
        home_impact = self.calculate_team_impact(home_team, away_team)
        away_impact = self.calculate_team_impact(away_team, home_team)
        
        # 計算相對優勢
        net_home = home_impact['total_impact'] - away_impact['total_impact']
        
        return home_impact, away_impact, net_home
    
    def adjust_xg_for_injuries(self, base_xg_home: float, base_xg_away: float,
                                home_team: str, away_team: str) -> Tuple[float, float]:
        """根據傷停調整 xG"""
        home_impact, away_impact = self.calculate_match_impact(home_team, away_team)
        
        # 受傷球隊 xG 降低
        adj_home_xg = base_xg_home * (1 - away_impact['xg_impact'] * 0.3)
        adj_away_xg = base_xg_away * (1 - home_impact['xg_impact'] * 0.3)
        
        return adj_home_xg, adj_away_xg


# ============================================================
# 第三部分：貝葉斯進球模型 - 完全概率化不確定性估計
# ============================================================

class BayesianGoalModel:
    """
    貝葉斯進球模型
    
    特點：
    - 完全概率化輸出 (後驗分布)
    - 不確定性量化
    - 適用於小樣本
    - 可更新先驗
    """
    
    def __init__(self, 
                 prior_strength: float = 10.0,   # 先驗強度
                 home_advantage_prior: float = 0.1,  # 主場優勢先驗
                 confidence_level: float = 0.95): # 置信水平
    
        self.prior_strength = prior_strength
        self.home_advantage_prior = home_advantage_prior
        self.confidence_level = confidence_level
        
        # 先驗參數 (Gamma-Poisson)
        self.prior_alpha = 1.0  # 弱信息先驗
        self.prior_beta = 1.0
        
        # 歷史數據
        self.observations = []
    
    def add_observation(self, home_goals: int, away_goals: int, 
                        home_xg: float = None, away_xg: float = None,
                        is_home: bool = True, date=None):
        """添加觀察數據"""
        self.observations.append({
            'home_goals': home_goals,
            'away_goals': away_goals,
            'home_xg': home_xg or home_goals,
            'away_xg': away_xg or away_goals,
            'is_home': is_home,
            'date': pd.Timestamp(date) if date else pd.Timestamp.now()
        })
    
    def _calculate_posterior(self, observations: List[dict]) -> Tuple[float, float]:
        """計算後驗參數 (Gamma-Poisson)"""
        if not observations:
            return self.prior_alpha, self.prior_beta
        
        # 使用 xG 或實際進球
        xgs = [o['home_xg'] for o in observations]
        alphas = [max(0.1, xg) for xg in xgs]  # 確保正數
        
        # 後驗 alpha = 先驗 + 觀察總和
        posterior_alpha = self.prior_alpha + sum(alphas)
        
        # 後驗 beta = 先驗 + 觀察數量 * 權重
        posterior_beta = self.prior_beta + len(observations)
        
        return posterior_alpha, posterior_beta
    
    def _gamma_ci(self, alpha: float, beta: float, confidence: float = 0.95) -> Tuple[float, float]:
        """計算 Gamma 分布置信區間"""
        a = alpha
        b = beta
        
        # Gamma 分布的均值和方差
        mean = a / b
        var = a / (b ** 2)
        std = np.sqrt(var)
        
        # 使用正態近似計算 CI
        z_lower = normal_dist.ppf((1 - confidence) / 2)
        z_upper = normal_dist.ppf((1 + confidence) / 2)
        
        ci_lower = max(0.01, mean + z_lower * std)
        ci_upper = mean + z_upper * std
        
        return ci_lower, ci_upper
    
    def predict(self, home_team_observations: List[dict] = None,
                away_team_observations: List[dict] = None) -> Dict:
        """
        貝葉斯預測
        
        返回：
        - 後驗均值
        - 置信區間
        - 每個進球數的概率
        """
        # 使用提供的觀察或全局觀察
        home_obs = home_team_observations or [
            o for o in self.observations if o['is_home']
        ]
        away_obs = away_team_observations or [
            o for o in self.observations if not o['is_home']
        ]
        
        # 計算後驗
        home_alpha, home_beta = self._calculate_posterior(home_obs)
        away_alpha, away_beta = self._calculate_posterior(away_obs)
        
        # 後驗均值
        home_mean = home_alpha / home_beta
        away_mean = away_alpha / away_beta
        
        # 考慮主場優勢
        home_mean += self.home_advantage_prior
        
        # 計算置信區間
        home_ci = self._gamma_ci(home_alpha, home_beta, self.confidence_level)
        away_ci = self._gamma_ci(away_alpha, away_beta, self.confidence_level)
        
        # 計算每個進球數的概率 (使用後驗預測)
        def calc_goal_probs(mean_lambda: float, alpha: float, beta: float, max_goals: int = 6) -> List[float]:
            probs = []
            for k in range(max_goals + 1):
                # 混合 Gamma-Poisson (負二項近似)
                prob = (beta ** alpha) / (beta_func(k + alpha, 1) * math.factorial(k)) * \
                       (beta / (beta + 1)) ** alpha * (1 / (beta + 1)) ** k
                probs.append(prob)
            
            # 正規化
            total = sum(probs)
            if total > 0:
                probs = [p / total for p in probs]
            return probs
        
        home_dist = calc_goal_probs(home_mean, home_alpha, home_beta)
        away_dist = calc_goal_probs(away_mean, away_alpha, away_beta)
        
        # 計算勝平負概率
        home_wins = sum(home_dist[i] * sum(away_dist[:i]) for i in range(len(home_dist)))
        draws = sum(home_dist[i] * away_dist[i] for i in range(len(home_dist)))
        away_wins = sum(away_dist[i] * sum(home_dist[:i]) for i in range(len(away_dist)))
        
        # 計算不確定性指標
        home_uncertainty = (home_ci[1] - home_ci[0]) / home_mean if home_mean > 0 else 1.0
        away_uncertainty = (away_ci[1] - away_ci[0]) / away_mean if away_mean > 0 else 1.0
        avg_uncertainty = (home_uncertainty + away_uncertainty) / 2
        
        return {
            'home_lambda': home_mean,
            'away_lambda': away_mean,
            'home_ci': home_ci,
            'away_ci': away_ci,
            'home_distribution': home_dist,
            'away_distribution': away_dist,
            'probabilities': {
                'home_win': home_wins,
                'draw': draws,
                'away_win': away_wins
            },
            'uncertainty': {
                'home_std_ratio': home_uncertainty,
                'away_std_ratio': away_uncertainty,
                'average': avg_uncertainty,
                'confidence_level': self.confidence_level
            },
            'data_quality': {
                'home_n': len(home_obs),
                'away_n': len(away_obs),
                'total_n': len(self.observations)
            }
        }
    
    def get_value_bets(self, odds_home: float, odds_away: float, odds_draw: float,
                       threshold: float = 0.05) -> List[Dict]:
        """識別價值投注"""
        pred = self.predict()
        
        implied_home = 1 / odds_home
        implied_away = 1 / odds_away
        implied_draw = 1 / odds_draw
        
        value_bets = []
        
        for market, pred_prob, odds in [
            ('Home', pred['probabilities']['home_win'], odds_home),
            ('Draw', pred['probabilities']['draw'], odds_draw),
            ('Away', pred['probabilities']['away_win'], odds_away)
        ]:
            edge = pred_prob - implied_prob
            
            if edge > threshold:
                value_bets.append({
                    'market': market,
                    'predicted_prob': pred_prob,
                    'implied_prob': implied_prob,
                    'edge': edge,
                    'odds': odds,
                    'ev': pred_prob * odds - 1,
                    'uncertainty': pred['uncertainty']['average']
                })
        
        return sorted(value_bets, key=lambda x: x['edge'], reverse=True)


# ============================================================
# 第四部分：LSTM 時序模型 - 球隊狀態變化
# ============================================================

class TeamFormLSTM:
    """
    LSTM 球隊狀態追蹤模型
    
    特點：
    - 捕捉時序依賴
    - 學習狀態變化模式
    - 多維度特徵輸入
    - 狀態向量輸出
    """
    
    def __init__(self,
                 sequence_length: int = 10,     # 輸入序列長度
                 hidden_units: int = 64,       # LSTM 隱藏單元
                 n_features: int = 8,          # 特徵維度
                 dropout_rate: float = 0.2,    # Dropout 比率
                 use_attention: bool = True):  # 是否使用 Attention
    
        self.sequence_length = sequence_length
        self.hidden_units = hidden_units
        self.n_features = n_features
        self.dropout_rate = dropout_rate
        self.use_attention = use_attention
        
        self.models = {}  # {team_name: trained_model}
        self.team_sequences = {}  # {team_name: sequence_data}
        self.is_fitted = HAS_TENSORFLOW
        
        if not HAS_TENSORFLOW:
            print("⚠️ TensorFlow 不可用，LSTM 功能受限")
    
    def _prepare_sequence(self, matches: List[dict]) -> np.ndarray:
        """準備時序特徵"""
        if not matches:
            return None
        
        features = []
        
        for m in matches[-self.sequence_length:]:
            # 標準化特徵
            feat = [
                m.get('goals_scored', 0) / 5,  # 進球 (0-5)
                m.get('goals_conceded', 0) / 5,  # 失球 (0-5)
                m.get('xg', 0) / 3,             # xG
                m.get('possession', 50) / 100,   # 控球率
                m.get('shots_on_target', 5) / 10,  # 射正
                1.0 if m.get('won', False) else 0.0,  # 勝利
                0.5 if m.get('draw', False) else 0.0,  # 平局
                m.get('home_advantage', 0.5),    # 主客場
            ]
            features.append(feat[:self.n_features])
        
        # Padding
        while len(features) < self.sequence_length:
            features.insert(0, [0.5] * self.n_features)
        
        return np.array(features)
    
    def add_match(self, team: str, goals_scored: int, goals_conceded: int,
                  xg: float, possession: float, shots_on_target: int,
                  result: str, is_home: bool, date=None):
        """添加比賽數據"""
        if team not in self.team_sequences:
            self.team_sequences[team] = []
        
        self.team_sequences[team].append({
            'goals_scored': goals_scored,
            'goals_conceded': goals_conceded,
            'xg': xg,
            'possession': possession,
            'shots_on_target': shots_on_target,
            'won': result == 'W',
            'draw': result == 'D',
            'home_advantage': 1.0 if is_home else 0.0,
            'date': pd.Timestamp(date) if date else pd.Timestamp.now()
        })
    
    def _build_model(self):
        """構建 LSTM 模型"""
        if not HAS_TENSORFLOW:
            return None
        
        model = Sequential([
            Input(shape=(self.sequence_length, self.n_features)),
            LSTM(self.hidden_units, return_sequences=self.use_attention),
            Dropout(self.dropout_rate),
            LSTM(self.hidden_units // 2),
            Dropout(self.dropout_rate),
            Dense(32, activation='relu'),
            Dense(16, activation='relu'),
            Dense(8, activation='linear')  # 輸出 8 維狀態向量
        ])
        
        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='mse',
            metrics=['mae']
        )
        
        return model
    
    def fit_team(self, team: str, epochs: int = 50, verbose: int = 0) -> bool:
        """訓練球隊狀態模型"""
        if not HAS_TENSORFLOW or team not in self.team_sequences:
            return False
        
        sequences = self.team_sequences[team]
        if len(sequences) < self.sequence_length:
            print(f"⚠️ {team}: 比賽數據不足 ({len(sequences)}/{self.sequence_length})")
            return False
        
        # 準備數據
        X = self._prepare_sequence(sequences)
        
        # 目標：下一場比賽的表現
        # 使用滑動窗口，最後一場作為測試
        y = np.array([
            sequences[-1].get('goals_scored', 0) / 5,
            sequences[-1].get('goals_conceded', 0) / 5,
            sequences[-1].get('xg', 0) / 3,
            1.0 if sequences[-1].get('won', False) else 0.0,
            0.0  # Padding
        ] + [0.0] * 3)[:8]
        
        # 創建多序列訓練數據
        X_train, y_train = [], []
        for i in range(len(sequences) - 1):
            seq = self._prepare_sequence(sequences[:i+1])
            if seq is not None:
                X_train.append(seq)
                next_match = sequences[min(i+1, len(sequences)-1)]
                y_train.append([
                    next_match.get('goals_scored', 0) / 5,
                    next_match.get('goals_conceded', 0) / 5,
                    next_match.get('xg', 0) / 3,
                    1.0 if next_match.get('won', False) else 0.0,
                    0.0, 0.0, 0.0, 0.0
                ])
        
        if len(X_train) < 3:
            return False
        
        X_train = np.array(X_train)
        y_train = np.array(y_train)
        
        # 訓練
        model = self._build_model()
        
        callbacks = [
            EarlyStopping(patience=10, restore_best_weights=True),
            ReduceLROnPlateau(factor=0.5, patience=5)
        ]
        
        model.fit(X_train, y_train, epochs=epochs, 
                 callbacks=callbacks, verbose=verbose)
        
        self.models[team] = model
        return True
    
    def predict_team_form(self, team: str) -> Dict:
        """預測球隊當前狀態"""
        if team not in self.team_sequences:
            return {'form_vector': None, 'form_score': None, 'trend': None}
        
        # 使用簡單的加權平均作為回退
        matches = self.team_sequences[team]
        recent = matches[-self.sequence_length:]
        
        if len(recent) < 3:
            # 數據不足，使用簡單平均
            avg_xg = np.mean([m.get('xg', 0) for m in matches]) if matches else 1.0
            return {
                'form_vector': [avg_xg, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
                'form_score': 0.5,
                'trend': 'stable',
                'confidence': 'low'
            }
        
        # 計算近期狀態
        weights = np.exp(np.linspace(0, 1, len(recent)))
        weights /= weights.sum()
        
        form_vector = [
            np.average([m.get('goals_scored', 0) for m in recent], weights=weights) / 5,
            np.average([m.get('goals_conceded', 0) for m in recent], weights=weights) / 5,
            np.average([m.get('xg', 0) for m in recent], weights=weights) / 3,
            np.average([1.0 if m.get('won', False) else 0.0 for m in recent], weights=weights),
            np.average([m.get('possession', 50) for m in recent], weights=weights) / 100,
            np.average([m.get('shots_on_target', 3) for m in recent], weights=weights) / 10,
            np.average([m.get('home_advantage', 0.5) for m in recent], weights=weights),
            0.5  # Padding
        ]
        
        # 計算狀態分數 (0-1)
        win_rate = form_vector[3]
        xg_ratio = form_vector[0] / (form_vector[1] + 0.1)
        form_score = (win_rate * 0.4 + min(1.0, xg_ratio) * 0.4 + form_vector[2] * 0.2)
        
        # 計算趨勢
        if len(recent) >= 5:
            early = np.mean([m.get('xg', 0) for m in recent[:len(recent)//2]])
            late = np.mean([m.get('xg', 0) for m in recent[len(recent)//2:]])
            
            if late > early * 1.1:
                trend = 'improving'
            elif late < early * 0.9:
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            trend = 'stable'
        
        # 置信度
        n_games = len(matches)
        confidence = 'high' if n_games >= 15 else 'medium' if n_games >= 5 else 'low'
        
        return {
            'form_vector': form_vector,
            'form_score': form_score,
            'trend': trend,
            'confidence': confidence,
            'recent_xg': np.mean([m.get('xg', 0) for m in recent[-3:]]),
            'win_rate_recent': np.mean([1.0 if m.get('won', False) else 0.0 for m in recent[-5:]])
        }
    
    def predict_match(self, home_team: str, away_team: str) -> Dict:
        """預測比賽結果"""
        home_form = self.predict_team_form(home_team)
        away_form = self.predict_team_form(away_team)
        
        # 結合雙方狀態
        home_xg_est = (home_form['recent_xg'] + 0.1) * home_form['form_score'] * 2
        away_xg_est = away_form['recent_xg'] * away_form['form_score'] * 2
        
        # 主場優勢
        home_xg_est += 0.15
        
        # 計算狀態差距
        form_diff = home_form['form_score'] - away_form['form_score']
        
        return {
            'home_xg_estimate': home_xg_est,
            'away_xg_estimate': away_xg_est,
            'home_form': home_form,
            'away_form': away_form,
            'form_advantage': form_diff,
            'prediction': 'Home' if form_diff > 0.1 else 'Away' if form_diff < -0.1 else 'Draw',
            'confidence': min(home_form['confidence'], away_form['confidence'])
        }


# ============================================================
# 第五部分：強化學習投注策略優化器
# ============================================================

class BettingRLAgent:
    """
    強化學習投注策略優化器
    
    特點：
    - Q-Learning 框架
    - 自動學習最優策略
    - 風險管理整合
    - 可訓練和部署
    """
    
    def __init__(self,
                 learning_rate: float = 0.1,
                 discount_factor: float = 0.95,
                 exploration_rate: float = 1.0,
                 min_exploration_rate: float = 0.01,
                 exploration_decay: float = 0.995,
                 bankroll: float = 1000.0,
                 max_bet_pct: float = 0.1):  # 最大投注比例
    
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = exploration_rate
        self.epsilon_min = min_exploration_rate
        self.epsilon_decay = exploration_decay
        self.bankroll = bankroll
        self.max_bet_pct = max_bet_pct
        
        # Q表：{(state, action): q_value}
        self.q_table = {}
        
        # 動作空間：投注比例 (0%, 25%, 50%, 75%, 100% Kelly)
        self.actions = [0.0, 0.25, 0.5, 0.75, 1.0]
        
        # 狀態空間離散化
        self.state_bins = {
            'edge': [0, 0.02, 0.05, 0.10, 0.20, 1.0],
            'confidence': [0, 0.3, 0.5, 0.7, 0.9, 1.0],
            'odds': [0, 1.5, 2.0, 3.0, 5.0, 100.0],
            'recent_form': [0, 0.3, 0.5, 0.7, 1.0]
        }
        
        # 歷史記錄
        self.history = []
        self.total_bets = 0
        self.wins = 0
        self.profit = 0.0
    
    def _discretize(self, value: float, bins: List[float]) -> int:
        """將連續值離散化"""
        for i, b in enumerate(bins):
            if value <= b:
                return i
        return len(bins) - 1
    
    def get_state_key(self, edge: float, confidence: float, 
                      odds: float, home_form: float, away_form: float) -> Tuple:
        """獲取離散狀態"""
        form_diff = home_form - away_form
        return (
            self._discretize(edge, self.state_bins['edge']),
            self._discretize(confidence, self.state_bins['confidence']),
            self._discretize(odds, self.state_bins['odds']),
            self._discretize(form_diff + 0.5, self.state_bins['recent_form'])
        )
    
    def choose_action(self, state_key: Tuple, exploit: bool = False) -> int:
        """選擇動作 (epsilon-greedy)"""
        if not exploit and np.random.random() < self.epsilon:
            # 探索
            return np.random.randint(0, len(self.actions))
        
        # 利用：選擇 Q 值最高的動作
        q_values = [self.q_table.get((state_key, a), 0.0) for a in range(len(self.actions))]
        return np.argmax(q_values)
    
    def calculate_kelly(self, prob: float, odds: float) -> float:
        """計算 Kelly 分數"""
        b = odds - 1
        p = prob
        q = 1 - p
        kelly = (b * p - q) / b if b > 0 else 0
        return max(0, kelly)
    
    def place_bet(self, edge: float, confidence: float, odds: float,
                  home_form: float, away_form: float, 
                  predicted_prob: float, actual_result: float = None) -> Dict:
        """
        進行投注決策
        
        Args:
            edge: 優勢 (模型勝率 - 市場隱含勝率)
            confidence: 模型信心度
            odds: 赔率
            home_form: 主隊狀態
            away_form: 客隊狀態
            predicted_prob: 模型預測概率
            actual_result: 實際結果 (用於訓練)
        """
        kelly_frac = self.calculate_kelly(predicted_prob, odds)
        
        # 根據信心度調整 Kelly
        adj_kelly = kelly_frac * confidence
        
        # 限制最大投注
        max_bet = self.bankroll * self.max_bet_pct
        kelly_bet = adj_kelly * self.bankroll
        
        state_key = self.get_state_key(edge, confidence, odds, home_form, away_form)
        
        # 選擇動作
        action_idx = self.choose_action(state_key)
        action = self.actions[action_idx]  # Kelly 比例
        
        # 計算實際投注額
        bet_pct = action * adj_kelly
        bet_amount = min(self.bankroll * bet_pct, max_bet)
        
        result = {
            'state': state_key,
            'action': action,
            'bet_pct': bet_pct,
            'bet_amount': bet_amount,
            'kelly_frac': kelly_frac,
            'edge': edge,
            'confidence': confidence,
            'odds': odds,
            'predicted_prob': predicted_prob
        }
        
        # 如果有實際結果，更新 Q 表
        if actual_result is not None:
            result['actual_result'] = actual_result
            
            # 計算獎勵
            if bet_amount > 0:
                if actual_result == 1:  # 贏
                    profit = bet_amount * (odds - 1)
                    self.wins += 1
                else:  # 輸
                    profit = -bet_amount
                self.profit += profit
                self.bankroll += bet_amount * (actual_result * (odds - 1) - (1 - actual_result))
            else:
                profit = 0
            
            # 更新 Q 值
            reward = profit / (self.bankroll + 1)  # 歸一化獎勵
            
            if bet_amount > 0:
                current_q = self.q_table.get((state_key, action_idx), 0.0)
                next_action = self.choose_action(state_key, exploit=True)
                next_q = self.q_table.get((state_key, next_action), 0.0)
                
                new_q = current_q + self.lr * (reward + self.gamma * next_q - current_q)
                self.q_table[(state_key, action_idx)] = new_q
            
            # 衰減 epsilon
            self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
            
            self.total_bets += 1
        
        self.history.append(result)
        return result
    
    def train_on_history(self, matches: List[Dict]):
        """根據歷史比賽訓練"""
        for match in matches:
            self.place_bet(
                edge=match.get('edge', 0),
                confidence=match.get('confidence', 0.5),
                odds=match.get('odds', 2.0),
                home_form=match.get('home_form', 0.5),
                away_form=match.get('away_form', 0.5),
                predicted_prob=match.get('prob', 0.5),
                actual_result=match.get('result', None)  # 1=贏, 0=輸
            )
    
    def get_strategy_stats(self) -> Dict:
        """獲取策略統計"""
        if not self.history:
            return {}
        
        bets_with_action = [h for h in self.history if h.get('bet_amount', 0) > 0]
        
        if not bets_with_action:
            return {
                'total_bets': self.total_bets,
                'win_rate': 0,
                'profit': self.profit,
                'roi': 0,
                'avg_bet': 0
            }
        
        wins = sum(1 for h in bets_with_action if h.get('actual_result', 0) == 1)
        total_bet = sum(h['bet_amount'] for h in bets_with_action)
        profit = sum(
            h['bet_amount'] * (h['odds'] - 1) if h.get('actual_result', 0) == 1 
            else -h['bet_amount'] 
            for h in bets_with_action
        )
        
        return {
            'total_bets': self.total_bets,
            'n_bets_placed': len(bets_with_action),
            'win_rate': wins / len(bets_with_action) if bets_with_action else 0,
            'profit': profit,
            'roi': profit / total_bet if total_bet > 0 else 0,
            'avg_bet': np.mean([h['bet_amount'] for h in bets_with_action]),
            'current_bankroll': self.bankroll,
            'exploration_rate': self.epsilon
        }
    
    def export_policy(self) -> Dict:
        """導出策略 (最優動作映射)"""
        policy = {}
        for state in set(k[0] for k in self.q_table.keys()):
            best_action = self.choose_action(state, exploit=True)
            policy[state] = {
                'action': best_action,
                'kelly_pct': self.actions[best_action],
                'q_value': self.q_table.get((state, best_action), 0)
            }
        return policy


# ============================================================
# 工具函數
# ============================================================

def create_advanced_ensemble() -> Dict:
    """創建高級模型集合"""
    return {
        'xg_forecaster': ExponentialDecayXGForecaster(decay_rate=0.1),
        'injury_model': InjuryImpactModel(),
        'bayesian_model': BayesianGoalModel(),
        'lstm_model': TeamFormLSTM(),
        'rl_agent': BettingRLAgent(bankroll=1000)
    }


def run_advanced_prediction(home_team: str, away_team: str,
                           historical_data: pd.DataFrame = None,
                           injury_data: Dict = None,
                           betting_odds: Dict = None) -> Dict:
    """
    運行高級預測整合
    
    返回包含所有模型預測的字典
    """
    results = {}
    
    # 1. xG 指數衰減預測
    xg_model = ExponentialDecayXGForecaster(decay_rate=0.1)
    # ... (需要填充歷史數據)
    xg_pred = xg_model.predict_match(home_team, away_team)
    results['xg_forecast'] = xg_pred
    
    # 2. 傷停影響
    injury_model = InjuryImpactModel()
    home_impact, away_impact, net = injury_model.calculate_match_impact(home_team, away_team)
    results['injury_impact'] = {
        'home': home_impact,
        'away': away_impact,
        'net_home_advantage': net
    }
    
    # 3. 貝葉斯模型
    bayes_model = BayesianGoalModel()
    bayes_pred = bayes_model.predict()
    results['bayesian'] = {
        'home_lambda': bayes_pred['home_lambda'],
        'away_lambda': bayes_pred['away_lambda'],
        'probabilities': bayes_pred['probabilities'],
        'uncertainty': bayes_pred['uncertainty']
    }
    
    # 4. LSTM 狀態追蹤
    lstm_model = TeamFormLSTM()
    lstm_pred = lstm_model.predict_match(home_team, away_team)
    results['lstm_form'] = lstm_pred
    
    # 5. RL 投注策略
    rl_agent = BettingRLAgent()
    if betting_odds:
        # 識別價值投注
        value_bets = bayes_model.get_value_bets(
            odds_home=betting_odds.get('home', 2.0),
            odds_away=betting_odds.get('away', 2.0),
            odds_draw=betting_odds.get('draw', 3.0)
        )
        results['value_bets'] = value_bets
        
        # RL 建議
        if value_bets:
            best_bet = value_bets[0]
            rl_decision = rl_agent.place_bet(
                edge=best_bet['edge'],
                confidence=1 - bayes_pred['uncertainty']['average'],
                odds=best_bet['odds'],
                home_form=lstm_pred['home_form']['form_score'],
                away_form=lstm_pred['away_form']['form_score'],
                predicted_prob=best_bet['predicted_prob']
            )
            results['rl_decision'] = rl_decision
    
    # 6. 綜合預測
    combined_prob = (
        bayes_pred['probabilities']['home_win'] * 0.3 +
        lstm_pred['home_form']['form_score'] * 0.2 +
        xg_pred['combined_xg'][0] / (xg_pred['combined_xg'][0] + xg_pred['combined_xg'][1]) * 0.3 +
        0.15  # 主場優勢基線
    )
    
    results['combined_prediction'] = {
        'home_win_prob': combined_prob,
        'away_win_prob': 1 - combined_prob,
        'confidence_weighted': combined_prob * (1 - bayes_pred['uncertainty']['average'])
    }
    
    return results


if __name__ == "__main__":
    # 測試
    print("="*60)
    print("高級模型測試")
    print("="*60)
    
    # 1. 指數衰減 xG
    print("\n[1] 指數衰減 xG 模型:")
    xg = ExponentialDecayXGForecaster(decay_rate=0.1)
    import datetime
    base_date = datetime.datetime.now()
    for i in range(5):
        xg.add_match("TestTeam", xg=1.5-i*0.1, is_home=True, 
                    date=base_date - datetime.timedelta(days=7*(5-i)))
    pred = xg.get_team_xg("TestTeam", base_date, is_home=True)
    print(f"   預測 xG: {pred['xg']:.3f} ± {pred['std']:.3f}")
    
    # 2. 傷停影響
    print("\n[2] 傷停影響模型:")
    injury = InjuryImpactModel()
    injury.add_player("TeamA", Player("GK1", "GK", 8.0, 90, 0.1, 0.8))
    injury.add_player("TeamA", Player("FWD1", "FWD", 25.0, 85, 0.6, 0.1))
    impact = injury.calculate_team_impact("TeamA")
    print(f"   傷停影響: {impact['total_impact']:.2%}")
    
    # 3. 貝葉斯模型
    print("\n[3] 貝葉斯進球模型:")
    bayes = BayesianGoalModel()
    for _ in range(10):
        bayes.add_observation(1, 1)
    pred = bayes.predict()
    print(f"   主場 λ: {pred['home_lambda']:.3f} [{pred['home_ci'][0]:.2f}-{pred['home_ci'][1]:.2f}]")
    print(f"   主勝概率: {pred['probabilities']['home_win']:.1%}")
    
    # 4. LSTM 狀態
    print("\n[4] LSTM 狀態追蹤:")
    lstm = TeamFormLSTM()
    for i in range(10):
        lstm.add_match("TeamB", goals_scored=2-i//3, goals_conceded=1, xg=1.5, 
                      possession=55, shots_on_target=4, result='W', is_home=True)
    form = lstm.predict_team_form("TeamB")
    print(f"   狀態分數: {form['form_score']:.3f} ({form['trend']})")
    
    # 5. RL 投注
    print("\n[5] RL 投注策略:")
    rl = BettingRLAgent(bankroll=1000)
    decision = rl.place_bet(edge=0.1, confidence=0.8, odds=2.2,
                           home_form=0.7, away_form=0.4, predicted_prob=0.55)
    print(f"   投注比例: {decision['bet_pct']:.1%}")
    print(f"   投注金額: ${decision['bet_amount']:.2f}")
    
    print("\n" + "="*60)
    print("測試完成!")
    print("="*60)
