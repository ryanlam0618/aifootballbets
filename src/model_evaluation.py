# -*- coding: utf-8 -*-
"""
模型評估與驗證框架

提供：
- 交叉驗證實現
- 回測系統
- 性能指標計算
- 模型監控
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import json
from collections import defaultdict


@dataclass
class EvaluationMetrics:
    """評估指標"""
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    auc_roc: float = 0.0
    brier_score: float = 0.0
    log_loss: float = 0.0
    calibration_error: float = 0.0
    
    # 足球特定指標
    home_accuracy: float = 0.0
    away_accuracy: float = 0.0
    draw_accuracy: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'accuracy': round(self.accuracy, 4),
            'precision': round(self.precision, 4),
            'recall': round(self.recall, 4),
            'f1_score': round(self.f1_score, 4),
            'auc_roc': round(self.auc_roc, 4),
            'brier_score': round(self.brier_score, 4),
            'log_loss': round(self.log_loss, 4),
            'calibration_error': round(self.calibration_error, 4),
            'home_accuracy': round(self.home_accuracy, 4),
            'away_accuracy': round(self.away_accuracy, 4),
            'draw_accuracy': round(self.draw_accuracy, 4)
        }


@dataclass
class BacktestResult:
    """回測結果"""
    total_bets: int = 0
    winning_bets: int = 0
    total_stake: float = 0.0
    total_profit: float = 0.0
    roi: float = 0.0
    yield_pct: float = 0.0
    
    # 詳細統計
    by_market: Dict = field(default_factory=dict)
    by_odds_range: Dict = field(default_factory=dict)
    by_confidence: Dict = field(default_factory=dict)
    
    # 風險指標
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    avg_odds: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'total_bets': self.total_bets,
            'winning_bets': self.winning_bets,
            'total_stake': round(self.total_stake, 2),
            'total_profit': round(self.total_profit, 2),
            'roi': round(self.roi, 4),
            'yield_pct': round(self.yield_pct, 4),
            'max_drawdown': round(self.max_drawdown, 4),
            'sharpe_ratio': round(self.sharpe_ratio, 4),
            'win_rate': round(self.win_rate, 4),
            'avg_odds': round(self.avg_odds, 4)
        }


class CrossValidator:
    """
    交叉驗證器
    
    實現時間序列友好的交叉驗證
    """
    
    def __init__(self, n_splits: int = 5, test_size: int = 10):
        """
        Args:
            n_splits: 分割數量
            test_size: 每個測試集的比賽數
        """
        self.n_splits = n_splits
        self.test_size = test_size
    
    def time_series_split(self, df: pd.DataFrame, 
                          date_col: str = 'match_date') -> List[Tuple[pd.Index, pd.Index]]:
        """
        時間序列分割
        
        確保測試集在訓練集之後
        """
        df = df.sort_values(date_col)
        n = len(df)
        split_size = (n - self.test_size) // self.n_splits
        
        splits = []
        for i in range(self.n_splits):
            test_start = n - self.test_size - (self.n_splits - i - 1) * split_size
            test_end = test_start + self.test_size
            
            if test_start < 0:
                continue
                
            train_end = test_start
            train_idx = df.index[:train_end]
            test_idx = df.index[test_start:test_end]
            
            if len(test_idx) > 0 and len(train_idx) > self.test_size:
                splits.append((train_idx, test_idx))
        
        return splits
    
    def evaluate_model(self, df: pd.DataFrame, 
                      model_predict_fn: Callable,
                      date_col: str = 'match_date',
                      target_col: str = 'result_encoded') -> EvaluationMetrics:
        """
        評估模型
        
        Args:
            df: 數據 DataFrame
            model_predict_fn: 預測函數，輸入特徵，返回概率
            date_col: 日期列名
            target_col: 目標列名
            
        Returns:
            EvaluationMetrics
        """
        splits = self.time_series_split(df, date_col)
        
        all_predictions = []
        all_actuals = []
        
        for train_idx, test_idx in splits:
            # 訓練模型
            train_df = df.loc[train_idx]
            test_df = df.loc[test_idx]
            
            # 獲取特徵列
            exclude = [date_col, target_col, 'home_team', 'away_team', 'league', 'event_id']
            feature_cols = [c for c in df.columns if c not in exclude and df[c].dtype in [np.float64, np.int64]]
            
            if len(feature_cols) == 0:
                continue
            
            X_train = train_df[feature_cols].fillna(0)
            y_train = train_df[target_col]
            X_test = test_df[feature_cols].fillna(0)
            y_test = test_df[target_col]
            
            # 預測
            try:
                predictions = model_predict_fn(X_train, y_train, X_test)
                all_predictions.extend(predictions)
                all_actuals.extend(y_test.tolist())
            except Exception as e:
                print(f"預測錯誤: {e}")
                continue
        
        if not all_predictions:
            return EvaluationMetrics()
        
        # 計算指標
        return self._calculate_metrics(np.array(all_predictions), np.array(all_actuals))
    
    def _calculate_metrics(self, predictions: np.ndarray, actuals: np.ndarray) -> EvaluationMetrics:
        """計算各種評估指標"""
        from sklearn.metrics import (
            accuracy_score, precision_score, recall_score, f1_score,
            roc_auc_score, brier_score_loss, log_loss
        )
        
        # 轉換為類別
        pred_classes = np.argmax(predictions, axis=1) if predictions.ndim > 1 else (predictions > 0.5).astype(int)
        
        metrics = EvaluationMetrics()
        
        try:
            metrics.accuracy = accuracy_score(actuals, pred_classes)
        except:
            pass
        
        # 多類別指標
        if len(np.unique(actuals)) > 2:
            try:
                metrics.precision = precision_score(actuals, pred_classes, average='weighted')
                metrics.recall = recall_score(actuals, pred_classes, average='weighted')
                metrics.f1_score = f1_score(actuals, pred_classes, average='weighted')
            except:
                pass
        else:
            try:
                metrics.precision = precision_score(actuals, pred_classes)
                metrics.recall = recall_score(actuals, pred_classes)
                metrics.f1_score = f1_score(actuals, pred_classes)
            except:
                pass
        
        # Brier Score (概率預測質量)
        if predictions.ndim > 1:
            # 對於多類別，使用平均 Brier Score
            n_classes = predictions.shape[1]
            brier_sum = 0
            for i, actual in enumerate(actuals):
                for j in range(n_classes):
                    prob = predictions[i, j] if j < predictions.shape[1] else 0
                    brier_sum += (prob - (1 if j == actual else 0)) ** 2
            metrics.brier_score = brier_sum / (len(actuals) * n_classes)
        
        return metrics


class Backtester:
    """
    回測系統
    
    模擬投注策略的歷史表現
    """
    
    def __init__(self, 
                 initial_bankroll: float = 10000,
                 min_odds: float = 1.2,
                 max_odds: float = 10.0,
                 min_edge: float = 0.05):
        """
        Args:
            initial_bankroll: 初始資金
            min_odds: 最小赔率
            max_odds: 最大赔率
            min_edge: 最小優勢
        """
        self.initial_bankroll = initial_bankroll
        self.bankroll = initial_bankroll
        self.min_odds = min_odds
        self.max_odds = max_odds
        self.min_edge = min_edge
        
        # 歷史記錄
        self.bets = []
        self.equity_curve = [initial_bankroll]
    
    def run_backtest(self, 
                    df: pd.DataFrame,
                    prediction_fn: Callable,
                    kelly_fraction: float = 0.5) -> BacktestResult:
        """
        運行回測
        
        Args:
            df: 包含比賽數據的 DataFrame
            prediction_fn: 預測函數，輸入(home_team, away_team)，返回{'home_win': prob, 'draw': prob, 'away_win': prob, 'odds_home': odds, ...}
            kelly_fraction: Kelly 分數
            
        Returns:
            BacktestResult
        """
        self.bankroll = self.initial_bankroll
        self.bets = []
        self.equity_curve = [self.initial_bankroll]
        
        df = df.sort_values('match_date')
        
        for idx, row in df.iterrows():
            try:
                # 獲取預測
                pred = prediction_fn(row['home_team'], row['away_team'])
                
                if not pred:
                    continue
                
                # 獲取赔率
                odds = pred.get('odds_home', 2.0)
                if odds < self.min_odds or odds > self.max_odds:
                    continue
                
                # 計算優勢
                model_prob = pred.get('home_win', 0.33)
                implied_prob = 1 / odds
                edge = model_prob - implied_prob
                
                if edge < self.min_edge:
                    continue
                
                # Kelly 投注
                kelly = self._calculate_kelly(model_prob, odds)
                stake = kelly * kelly_fraction * self.bankroll
                
                # 限制最大投注
                max_stake = self.bankroll * 0.1
                stake = min(stake, max_stake)
                
                if stake < 1:
                    continue
                
                # 記錄投注
                actual_result = self._get_result(row)
                won = (actual_result == 'home_win')
                
                if won:
                    profit = stake * (odds - 1)
                    self.bankroll += profit
                else:
                    profit = -stake
                    self.bankroll -= stake
                
                self.bets.append({
                    'date': row['match_date'],
                    'home_team': row['home_team'],
                    'away_team': row['away_team'],
                    'stake': stake,
                    'odds': odds,
                    'prediction': model_prob,
                    'actual': actual_result,
                    'won': won,
                    'profit': profit,
                    'bankroll': self.bankroll
                })
                
                self.equity_curve.append(self.bankroll)
                
            except Exception as e:
                continue
        
        return self._calculate_results()
    
    def _calculate_kelly(self, prob: float, odds: float) -> float:
        """計算 Kelly 分數"""
        b = odds - 1
        p = prob
        q = 1 - p
        kelly = (b * p - q) / b if b > 0 else 0
        return max(0, kelly)
    
    def _get_result(self, row: pd.Series) -> str:
        """確定比賽結果"""
        if row['home_goals'] > row['away_goals']:
            return 'home_win'
        elif row['home_goals'] < row['away_goals']:
            return 'away_win'
        else:
            return 'draw'
    
    def _calculate_results(self) -> BacktestResult:
        """計算回測結果"""
        if not self.bets:
            return BacktestResult()
        
        total_bets = len(self.bets)
        winning_bets = sum(1 for b in self.bets if b['won'])
        total_stake = sum(b['stake'] for b in self.bets)
        total_profit = sum(b['profit'] for b in self.bets)
        
        result = BacktestResult(
            total_bets=total_bets,
            winning_bets=winning_bets,
            total_stake=total_stake,
            total_profit=total_profit,
            roi=total_profit / total_stake if total_stake > 0 else 0,
            yield_pct=(total_profit / total_stake * 100) if total_stake > 0 else 0,
            win_rate=winning_bets / total_bets if total_bets > 0 else 0,
            avg_odds=np.mean([b['odds'] for b in self.bets])
        )
        
        # 最大回撤
        equity = np.array(self.equity_curve)
        running_max = np.maximum.accumulate(equity)
        drawdowns = (running_max - equity) / running_max
        result.max_drawdown = np.max(drawdowns) if len(drawdowns) > 0 else 0
        
        # Sharpe Ratio
        if len(self.bets) > 1:
            returns = [b['profit'] / b['stake'] for b in self.bets if b['stake'] > 0]
            if returns and np.std(returns) > 0:
                result.sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252)
        
        return result
    
    def get_bet_details(self) -> pd.DataFrame:
        """獲取投注詳細信息"""
        return pd.DataFrame(self.bets)


class ModelMonitor:
    """
    模型監控系統
    
    監控模型性能和數據漂移
    """
    
    def __init__(self, model_name: str = "default"):
        self.model_name = model_name
        self.predictions_history = []
        self.actuals_history = []
        self.feature_distributions = {}
        self.performance_metrics = []
        
        # 基準指標
        self.baseline_metrics = None
        self.drift_threshold = 0.1
    
    def set_baseline(self, metrics: EvaluationMetrics):
        """設置基準指標"""
        self.baseline_metrics = metrics
    
    def record_prediction(self, 
                         features: Dict,
                         prediction: np.ndarray,
                         actual: Optional[int] = None):
        """記錄預測"""
        self.predictions_history.append({
            'timestamp': datetime.now(),
            'prediction': prediction,
            'features': features
        })
        
        if actual is not None:
            self.actuals_history.append({
                'timestamp': datetime.now(),
                'actual': actual,
                'prediction': prediction
            })
    
    def check_performance_drift(self, window_size: int = 100) -> Dict:
        """檢查性能漂移"""
        if len(self.actuals_history) < window_size:
            return {'status': 'insufficient_data'}
        
        recent = self.actuals_history[-window_size:]
        
        # 計算最近的準確率
        correct = sum(1 for p in recent 
                    if np.argmax(p['prediction']) == p['actual'])
        recent_accuracy = correct / len(recent)
        
        if self.baseline_metrics:
            baseline_accuracy = self.baseline_metrics.accuracy
            drift = recent_accuracy - baseline_accuracy
            
            return {
                'status': 'drifted' if abs(drift) > self.drift_threshold else 'stable',
                'recent_accuracy': round(recent_accuracy, 4),
                'baseline_accuracy': round(baseline_accuracy, 4),
                'drift': round(drift, 4),
                'n_samples': len(recent)
            }
        
        return {'status': 'no_baseline', 'recent_accuracy': round(recent_accuracy, 4)}
    
    def check_feature_drift(self, current_features: Dict) -> Dict:
        """檢查特徵漂移"""
        drift_report = {}
        
        for feature_name, value in current_features.items():
            if feature_name not in self.feature_distributions:
                self.feature_distributions[feature_name] = []
            
            history = self.feature_distributions[feature_name]
            history.append(value)
            
            if len(history) < 50:
                continue
            
            # 簡單的漂移檢測：均值變化
            recent = history[-50:]
            older = history[-100:-50] if len(history) >= 100 else history[:-50]
            
            if len(older) > 0:
                mean_diff = abs(np.mean(recent) - np.mean(older)) / (np.std(older) + 1e-6)
                drift_report[feature_name] = {
                    'drift_score': round(mean_diff, 4),
                    'is_drifted': mean_diff > 0.3
                }
        
        return {
            'drifted_features': [k for k, v in drift_report.items() if v.get('is_drifted')],
            'drift_details': drift_report
        }
    
    def get_performance_summary(self) -> Dict:
        """獲取性能摘要"""
        if not self.actuals_history:
            return {'status': 'no_data'}
        
        recent = self.actuals_history[-100:]
        
        correct = sum(1 for p in recent 
                    if np.argmax(p['prediction']) == p['actual'])
        
        return {
            'model_name': self.model_name,
            'total_predictions': len(self.predictions_history),
            'total_with_actuals': len(self.actuals_history),
            'recent_accuracy': round(correct / len(recent), 4) if recent else 0,
            'baseline_accuracy': round(self.baseline_metrics.accuracy, 4) if self.baseline_metrics else None
        }
    
    def export_report(self, filepath: str):
        """導出監控報告"""
        report = {
            'model_name': self.model_name,
            'generated_at': datetime.now().isoformat(),
            'performance': self.get_performance_summary(),
            'drift_check': self.check_performance_drift()
        }
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"監控報告已導出到 {filepath}")


class DataValidator:
    """
    數據驗證器
    
    檢測異常值和數據質量問題
    """
    
    def __init__(self):
        self.validation_rules = {}
        self.anomalies = []
    
    def validate_match_data(self, df: pd.DataFrame) -> Dict:
        """
        驗證比賽數據
        
        檢查：
        - 比分合理性
        - xG 值範圍
        - 赔率範圍
        - 缺失值
        """
        issues = []
        
        # 1. 比分檢查
        if 'home_goals' in df.columns:
            negative_goals = df[df['home_goals'] < 0]
            if len(negative_goals) > 0:
                issues.append({'type': 'negative_goals', 'count': len(negative_goals)})
            
            # 異常高分
            high_goals = df[df['home_goals'] > 10]
            if len(high_goals) > 0:
                issues.append({'type': 'high_home_goals', 'count': len(high_goals)})
        
        # 2. xG 檢查
        xg_cols = [c for c in df.columns if 'xg' in c.lower()]
        for col in xg_cols:
            negative_xg = df[df[col] < 0]
            if len(negative_xg) > 0:
                issues.append({'type': f'negative_{col}', 'count': len(negative_xg)})
            
            high_xg = df[df[col] > 5]
            if len(high_xg) > 0:
                issues.append({'type': f'high_{col}', 'count': len(high_xg)})
        
        # 3. 赔率檢查
        odds_cols = [c for c in df.columns if 'odds' in c.lower()]
        for col in odds_cols:
            low_odds = df[df[col] < 1.0]
            if len(low_odds) > 0:
                issues.append({'type': f'low_{col}', 'count': len(low_odds)})
        
        # 4. 缺失值檢查
        missing_summary = df.isnull().sum()
        missing_cols = missing_summary[missing_summary > 0]
        if len(missing_cols) > 0:
            issues.append({
                'type': 'missing_values',
                'columns': missing_cols.to_dict()
            })
        
        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'total_rows': len(df),
            'quality_score': max(0, 100 - len(issues) * 10)
        }
    
    def detect_outliers(self, df: pd.DataFrame, 
                       column: str,
                       method: str = 'iqr',
                       threshold: float = 3.0) -> pd.Series:
        """
        檢測異常值
        
        Args:
            df: 數據
            column: 列名
            method: 方法 ('iqr' 或 'zscore')
            threshold: 閾值
            
        Returns:
            異常值 mask
        """
        if column not in df.columns:
            return pd.Series([False] * len(df))
        
        data = df[column].fillna(0)
        
        if method == 'iqr':
            Q1 = data.quantile(0.25)
            Q3 = data.quantile(0.75)
            IQR = Q3 - Q1
            lower = Q1 - threshold * IQR
            upper = Q3 + threshold * IQR
            return (data < lower) | (data > upper)
        
        elif method == 'zscore':
            mean = data.mean()
            std = data.std()
            z_scores = np.abs((data - mean) / (std + 1e-6))
            return z_scores > threshold
        
        return pd.Series([False] * len(df))
    
    def clean_data(self, df: pd.DataFrame, 
                   strategy: str = 'remove') -> pd.DataFrame:
        """
        清洗數據
        
        Args:
            strategy: 策略 ('remove', 'clip', 'interpolate')
        """
        data = df.copy()
        
        # 1. 處理比分異常
        if 'home_goals' in data.columns:
            data.loc[data['home_goals'] < 0, 'home_goals'] = 0
            if strategy == 'clip':
                data.loc[data['home_goals'] > 10, 'home_goals'] = 10
        
        # 2. 處理 xG 異常
        xg_cols = [c for c in data.columns if 'xg' in c.lower()]
        for col in xg_cols:
            data.loc[data[col] < 0, col] = 0
            if strategy == 'clip':
                data.loc[data[col] > 5, col] = 5
        
        # 3. 填補缺失值
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        data[numeric_cols] = data[numeric_cols].fillna(data[numeric_cols].median())
        
        return data


# ============================================================
# 測試
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("模型評估框架測試")
    print("=" * 60)
    
    # 創建測試數據
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=200, freq='D')
    
    test_data = pd.DataFrame({
        'match_date': dates,
        'home_team': ['Team A'] * 200,
        'away_team': ['Team B'] * 200,
        'home_goals': np.random.randint(0, 4, 200),
        'away_goals': np.random.randint(0, 4, 200),
        'home_xg_total': np.random.uniform(0.5, 3.0, 200),
        'away_xg_total': np.random.uniform(0.5, 3.0, 200),
        'home_odds': np.random.uniform(1.5, 4.0, 200),
        'result_encoded': [0 if h > a else (1 if h == a else 2) 
                          for h, a in zip(np.random.randint(0, 4, 200), 
                                         np.random.randint(0, 4, 200))]
    })
    
    # 測試交叉驗證
    print("\n1. 測試交叉驗證...")
    cv = CrossValidator(n_splits=5, test_size=20)
    
    def dummy_model(X_train, y_train, X_test):
        return np.random.rand(len(X_test), 3)
    
    metrics = cv.evaluate_model(test_data, dummy_model)
    print(f"   準確率: {metrics.accuracy:.4f}")
    
    # 測試回測
    print("\n2. 測試回測...")
    backtester = Backtester(initial_bankroll=10000)
    
    def dummy_prediction(home, away):
        return {
            'home_win': 0.4,
            'draw': 0.3,
            'away_win': 0.3,
            'odds_home': 2.5
        }
    
    result = backtester.run_backtest(test_data, dummy_prediction)
    print(f"   總投注: {result.total_bets}")
    print(f"   ROI: {result.roi*100:.2f}%")
    
    # 測試數據驗證
    print("\n3. 測試數據驗證...")
    validator = DataValidator()
    validation = validator.validate_match_data(test_data)
    print(f"   數據有效: {validation['is_valid']}")
    print(f"   質量分數: {validation['quality_score']}")
    
    # 測試異常值檢測
    print("\n4. 測試異常值檢測...")
    outliers = validator.detect_outliers(test_data, 'home_goals', method='zscore')
    print(f"   檢測到異常: {outliers.sum()}")
