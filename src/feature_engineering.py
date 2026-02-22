# -*- coding: utf-8 -*-
"""
特徵工程模組

用於從原始數據生成機器學習特徵：
- 基礎統計特徵
- 滾動窗口特徵
- 交互特徵
- 比率特徵
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta


class FeatureEngineer:
    """
    特徵工程師
    
    從足球比賽數據生成 ML 特徵
    """
    
    def __init__(self, decay_rate: float = 0.1):
        """
        Args:
            decay_rate: 指數衰減率（用於加權平均）
        """
        self.decay_rate = decay_rate
        self.team_cache = {}  # 球隊緩存
    
    def create_basic_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        創建基礎特徵
        
        Args:
            df: 包含比賽數據的 DataFrame
            
        Returns:
            添加了新特徵的 DataFrame
        """
        data = df.copy()
        
        # 1. 基礎差異特徵
        data['goal_diff'] = data['home_goals'] - data['away_goals']
        data['shot_diff'] = data['home_shots'] - data['away_shots']
        data['corner_diff'] = data['home_corners'] - data['away_corners']
        
        # 2. 比率特徵
        data['home_shot_accuracy'] = np.where(
            data['home_shots'] > 0,
            data['home_shots_on'] / data['home_shots'],
            0
        )
        data['away_shot_accuracy'] = np.where(
            data['away_shots'] > 0,
            data['away_shots_on'] / data['away_shots'],
            0
        )
        
        # 3. xG 相關特徵
        if 'home_xg_total' in data.columns and 'away_xg_total' in data.columns:
            data['xg_diff'] = data['home_xg_total'] - data['away_xg_total']
            data['xg_total'] = data['home_xg_total'] + data['away_xg_total']
            
            # xG vs 實際進球
            data['home_xg_minus_goals'] = data['home_xg_total'] - data['home_goals']
            data['away_xg_minus_goals'] = data['away_xg_total'] - data['away_goals']
        
        # 4. xGOT 相關特徵
        if 'home_xgot_total' in data.columns:
            data['xgot_diff'] = data['home_xgot_total'] - data['away_xgot_total']
            data['home_xgot_vs_xg'] = data['home_xgot_total'] - data.get('home_xg_total', 0)
            data['away_xgot_vs_xg'] = data['away_xgot_total'] - data.get('away_xg_total', 0)
        
        # 5. 控球率特徵
        if 'home_poss' in data.columns:
            data['poss_diff'] = data['home_poss'] - data.get('away_poss', 50)
        
        return data
    
    def create_rolling_features(self, df: pd.DataFrame, window_size: int = 5) -> pd.DataFrame:
        """
        創建滾動窗口特徵
        
        Args:
            df: 比賽數據
            window_size: 滾動窗口大小
            
        Returns:
            添加了滾動特徵的 DataFrame
        """
        data = df.copy()
        data = data.sort_values('match_date')
        
        # 對每個球隊計算滾動特徵
        for team in data['home_team'].unique():
            # 主場
            home_mask = data['home_team'] == team
            away_mask = data['away_team'] == team
            
            # 主場滾動特徵
            data.loc[home_mask, 'home_rolling_goals'] = (
                data.loc[home_mask, 'home_goals']
                .rolling(window=window_size, min_periods=1)
                .mean()
            )
            data.loc[home_mask, 'home_rolling_xg'] = (
                data.loc[home_mask, 'home_xg_total']
                .rolling(window=window_size, min_periods=1)
                .mean()
            )
            
            # 客場滾動特徵
            data.loc[away_mask, 'away_rolling_goals'] = (
                data.loc[away_mask, 'away_goals']
                .rolling(window=window_size, min_periods=1)
                .mean()
            )
            data.loc[away_mask, 'away_rolling_xg'] = (
                data.loc[away_mask, 'away_xg_total']
                .rolling(window=window_size, min_periods=1)
                .mean()
            )
        
        return data
    
    def create_form_features(self, df: pd.DataFrame, n_games: int = 5) -> pd.DataFrame:
        """
        創建球隊狀態特徵
        
        Args:
            df: 比賽數據
            n_games: 用於計算狀態的比賽場數
            
        Returns:
            添加了狀態特徵的 DataFrame
        """
        data = df.copy()
        data = data.sort_values('match_date')
        
        # 初始化狀態列
        data['home_form'] = 0.0
        data['away_form'] = 0.0
        data['home_win_rate'] = 0.5
        data['away_win_rate'] = 0.5
        
        # 計算每場比賽前的狀態
        for idx in range(len(data)):
            row = data.iloc[idx]
            match_date = row['match_date']
            
            # 獲取該比賽之前的歷史
            home_team = row['home_team']
            away_team = row['away_team']
            
            # 主隊最近 n 場
            home_history = data[
                (data['match_date'] < match_date) &
                ((data['home_team'] == home_team) | (data['away_team'] == home_team))
            ].tail(n_games)
            
            away_history = data[
                (data['match_date'] < match_date) &
                ((data['home_team'] == away_team) | (data['away_team'] == away_team))
            ].tail(n_games)
            
            # 計算主隊狀態
            if len(home_history) > 0:
                home_points = 0
                for _, h in home_history.iterrows():
                    if h['home_team'] == home_team:
                        if h['home_goals'] > h['away_goals']:
                            home_points += 3
                        elif h['home_goals'] == h['away_goals']:
                            home_points += 1
                    else:
                        if h['away_goals'] > h['home_goals']:
                            home_points += 3
                        elif h['away_goals'] == h['home_goals']:
                            home_points += 1
                
                data.iloc[idx, data.columns.get_loc('home_form')] = home_points / (len(home_history) * 3)
                data.iloc[idx, data.columns.get_loc('home_win_rate')] = home_points / (len(home_history) * 3)
            
            # 計算客隊狀態
            if len(away_history) > 0:
                away_points = 0
                for _, a in away_history.iterrows():
                    if a['home_team'] == away_team:
                        if a['home_goals'] > a['away_goals']:
                            away_points += 3
                        elif a['home_goals'] == a['away_goals']:
                            away_points += 1
                    else:
                        if a['away_goals'] > a['home_goals']:
                            away_points += 3
                        elif a['away_goals'] == a['home_goals']:
                            away_points += 1
                
                data.iloc[idx, data.columns.get_loc('away_form')] = away_points / (len(away_history) * 3)
                data.iloc[idx, data.columns.get_loc('away_win_rate')] = away_points / (len(away_history) * 3)
        
        return data
    
    def create_interaction_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        創建交互特徵
        
        組合多個變量創建新特徵
        """
        data = df.copy()
        
        # xG 與狀態的交互
        if 'home_xg_total' in data.columns and 'home_form' in data.columns:
            data['home_xg_form'] = data['home_xg_total'] * data['home_form']
            data['away_xg_form'] = data.get('away_xg_total', 1) * data.get('away_form', 0.5)
        
        # 射門次數與 xG 的比率
        if 'home_shots' in data.columns and 'home_xg_total' in data.columns:
            data['home_shots_per_xg'] = np.where(
                data['home_xg_total'] > 0,
                data['home_shots'] / data['home_xg_total'],
                data['home_shots']
            )
        
        # 主場優勢指數
        if 'home_form' in data.columns:
            data['home_advantage_index'] = data['home_form'] - data.get('away_form', 0.5) + 0.1
        
        return data
    
    def create_target_variable(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        創建目標變量
        
        用於分類：
        - home_win: 主隊獲勝
        - draw: 平局
        - away_win: 客隊獲勝
        """
        data = df.copy()
        
        data['result'] = np.where(
            data['home_goals'] > data['away_goals'], 'home_win',
            np.where(data['home_goals'] == data['away_goals'], 'draw', 'away_win')
        )
        
        # 數值編碼
        data['result_encoded'] = np.where(
            data['home_goals'] > data['away_goals'], 0,
            np.where(data['home_goals'] == data['away_goals'], 1, 2)
        )
        
        return data
    
    def prepare_ml_dataset(self, df: pd.DataFrame, include_targets: bool = True) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
        """
        準備完整的 ML 數據集
        
        執行完整的特徵工程流程
        
        Args:
            df: 原始數據
            include_targets: 是否包含目標變量
            
        Returns:
            Tuple of (features, target)
        """
        # 排序
        data = df.copy()
        data = data.sort_values('match_date')
        
        # 創建特徵
        data = self.create_basic_features(data)
        data = self.create_rolling_features(data)
        data = self.create_form_features(data)
        data = self.create_interaction_features(data)
        
        # 目標變量
        if include_targets:
            data = self.create_target_variable(data)
        
        # 選擇特徵列
        exclude_cols = [
            'match_date', 'event_id', 'home_team', 'away_team', 
            'league', 'tournament_name', 'season', 'result', 'result_encoded'
        ]
        
        feature_cols = [c for c in data.columns if c not in exclude_cols]
        feature_cols = [c for c in feature_cols if data[c].dtype in [np.float64, np.int64]]
        
        X = data[feature_cols].fillna(0)
        
        if include_targets:
            y = data['result_encoded']
            return X, y
        else:
            return X, None
    
    def get_feature_names(self) -> List[str]:
        """返回所有可用特徵的名稱"""
        return [
            'goal_diff', 'shot_diff', 'corner_diff',
            'home_shot_accuracy', 'away_shot_accuracy',
            'xg_diff', 'xg_total', 'home_xg_minus_goals', 'away_xg_minus_goals',
            'xgot_diff', 'home_xgot_vs_xg', 'away_xgot_vs_xg',
            'poss_diff', 'home_rolling_goals', 'away_rolling_goals',
            'home_rolling_xg', 'away_rolling_xg',
            'home_form', 'away_form', 'home_win_rate', 'away_win_rate',
            'home_xg_form', 'away_xg_form', 'home_shots_per_xg',
            'home_advantage_index'
        ]


class TimeSeriesFeatureGenerator:
    """
    時間序列特徵生成器
    
    為 LSTM 等時間序列模型生成序列特徵
    """
    
    def __init__(self, sequence_length: int = 10):
        self.sequence_length = sequence_length
    
    def create_sequences(self, df: pd.DataFrame, team: str, 
                        features: List[str]) -> Tuple[np.ndarray, np.ndarray]:
        """
        為指定球隊創建序列數據
        
        Args:
            df: 比賽數據
            team: 球隊名稱
            features: 用於序列的特徵列表
            
        Returns:
            Tuple of (X, y) 序列數據
        """
        # 獲取球隊所有比賽
        team_matches = df[
            (df['home_team'] == team) | (df['away_team'] == team)
        ].sort_values('match_date')
        
        if len(team_matches) < self.sequence_length:
            return np.array([]), np.array([])
        
        sequences = []
        targets = []
        
        for i in range(len(team_matches) - self.sequence_length):
            seq = team_matches.iloc[i:i + self.sequence_length]
            target = team_matches.iloc[i + self.sequence_length]
            
            # 提取特徵
            seq_features = []
            for _, row in seq.iterrows():
                is_home = row['home_team'] == team
                
                if is_home:
                    features_vec = [row.get(f, 0) for f in features]
                else:
                    # 對於客場，反轉某些特徵
                    features_vec = []
                    for f in features:
                        if f.startswith('home_'):
                            f = f.replace('home_', 'away_')
                        elif f.startswith('away_'):
                            f = f.replace('away_', 'home_')
                        features_vec.append(-row.get(f, 0) if 'diff' in f else row.get(f, 0))
                
                seq_features.append(features_vec)
            
            sequences.append(seq_features)
            
            # 目標：下一場的結果
            if is_home:
                goals = target['home_goals']
            else:
                goals = target['away_goals']
            targets.append(goals)
        
        return np.array(sequences), np.array(targets)


# ============================================================
# 測試
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("特徵工程模組測試")
    print("=" * 60)
    
    # 創建測試數據
    test_data = pd.DataFrame({
        'match_date': pd.date_range('2024-01-01', periods=20, freq='W'),
        'home_team': ['Team A'] * 20,
        'away_team': ['Team B'] * 20,
        'home_goals': [2, 1, 3, 0, 2, 1, 2, 3, 1, 0, 2, 1, 3, 2, 1, 0, 2, 1, 2, 3],
        'away_goals': [1, 2, 1, 2, 1, 2, 0, 1, 2, 1, 0, 2, 1, 2, 1, 2, 1, 2, 1, 0],
        'home_shots': [10, 8, 12, 6, 9, 7, 11, 13, 8, 5, 10, 7, 12, 9, 8, 6, 10, 7, 11, 14],
        'away_shots': [7, 9, 8, 10, 6, 8, 5, 7, 9, 8, 6, 9, 7, 10, 8, 9, 7, 8, 6, 5],
        'home_shots_on': [5, 4, 6, 3, 5, 4, 6, 7, 4, 2, 5, 3, 6, 5, 4, 3, 5, 4, 6, 7],
        'away_shots_on': [3, 5, 4, 5, 3, 4, 2, 3, 5, 4, 3, 5, 4, 5, 4, 5, 4, 4, 3, 2],
        'home_xg_total': [1.8, 1.2, 2.5, 0.8, 1.6, 1.1, 1.9, 2.3, 1.0, 0.6, 1.7, 1.0, 2.4, 1.8, 1.2, 0.7, 1.6, 1.1, 1.8, 2.6],
        'away_xg_total': [1.1, 1.5, 1.2, 1.8, 0.9, 1.3, 0.7, 1.0, 1.4, 1.2, 0.8, 1.4, 1.1, 1.6, 1.2, 1.5, 1.1, 1.3, 0.9, 0.6],
        'home_poss': [55, 48, 60, 45, 52, 49, 58, 62, 47, 43, 54, 48, 59, 53, 50, 44, 55, 49, 57, 63],
    })
    
    # 測試特徵工程師
    fe = FeatureEngineer()
    
    # 創建基礎特徵
    basic = fe.create_basic_features(test_data)
    print("\n基礎特徵:")
    print(basic[['goal_diff', 'xg_diff', 'home_shot_accuracy']].head())
    
    # 準備 ML 數據集
    X, y = fe.prepare_ml_dataset(test_data)
    print(f"\nML 數據集:")
    print(f"  特徵數: {X.shape[1]}")
    print(f"  樣本數: {X.shape[0]}")
    print(f"  特徵列: {X.columns.tolist()[:5]}...")
    
    # 測試時間序列生成器
    ts = TimeSeriesFeatureGenerator(sequence_length=5)
    seq_x, seq_y = ts.create_sequences(test_data, 'Team A', ['home_goals', 'home_xg_total'])
    print(f"\n時間序列:")
    print(f"  X shape: {seq_x.shape}")
    print(f"  y shape: {seq_y.shape}")
