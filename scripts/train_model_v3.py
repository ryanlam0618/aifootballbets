#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stacking 集成學習訓練腳本 v3

包含：
1. 多模型集成 (XGBoost, Random Forest, Gradient Boosting, Logistic Regression)
2. Stacking 元學習器
3. 貝葉斯權重優化
4. Out-of-Fold 預防過擬合
"""

import sys
import os
import pandas as pd
import numpy as np
import pickle
import warnings
warnings.filterwarnings('ignore')

sys.stdout.reconfigure(encoding='utf-8')

print("=" * 70)
print("足球 AI 投注系統 - Stacking 集成學習訓練 v3")
print("=" * 70)

# 導入新模型
from src.math_models_v3 import (
    NegativeBinomialModel,
    DynamicKEloSystem,
    MonteCarloSimulatorV3,
    StackingEnsemble,
    ConfidenceKelly,
    XGBoostModel,
    RandomForestModel,
    GradientBoostingModel,
    LogisticRegressionModel
)


# ============================================
# 第一部分：數據載入與預處理
# ============================================

print("\n[1/6] 載入歷史數據...")

# 嘗試多種編碼
csv_paths = [
    'data/history_data.csv',
    'c:/Users/Ryan/python/.vscode/fb_ai_bets/data/history_data.csv'
]

df = None
for path in csv_paths:
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, encoding='utf-8-sig', low_memory=False)
            print(f"  [OK] 成功載入: {path}")
            break
        except Exception as e:
            print(f"  [WARN] UTF-8編碼失敗: {e}")
            try:
                df = pd.read_csv(path, encoding='latin-1', low_memory=False)
                print(f"  [OK] 成功載入 (latin-1)")
                break
            except:
                continue

if df is None:
    print("  [ERROR] 無法載入數據")
    sys.exit(1)

print(f"  [OK] 總記錄數: {len(df):,}")

# 標準化列名
df.columns = df.columns.str.strip().str.lower().str.replace('\ufeff', '')

column_mapping = {
    'fthg': 'home_goals', 'ftag': 'away_goals',
    'hthg': 'ht_home_goals', 'htag': 'ht_away_goals',
    'hometeam': 'home_team', 'awayteam': 'away_team',
    'xg': 'xg', 'xga': 'xga',
}

for old_col, new_col in column_mapping.items():
    if old_col in df.columns:
        df.rename(columns={old_col: new_col}, inplace=True)

# ============================================
# 第二部分：數據預處理
# ============================================

print("\n[2/6] 數據預處理...")

# 移除沒有比分數據的行
df = df.dropna(subset=['home_goals', 'away_goals'])
print(f"  [OK] 有效比賽: {len(df):,} 條")

# 轉換日期
df['date'] = pd.to_datetime(df['date'], errors='coerce')
df = df.dropna(subset=['date'])
df = df.sort_values('date')

# 目標變數：主勝(0), 平(1), 客勝(2)
conditions = [
    (df['home_goals'] > df['away_goals']),
    (df['home_goals'] == df['away_goals']),
    (df['home_goals'] < df['away_goals'])
]
df['result'] = np.select(conditions, [0, 1, 2])

print(f"  [OK] 比賽結果分布:")
print(f"       主勝 (H): {(df['result']==0).sum():,} ({(df['result']==0).mean()*100:.1f}%)")
print(f"       和局 (D): {(df['result']==1).sum():,} ({(df['result']==1).mean()*100:.1f}%)")
print(f"       客勝 (A): {(df['result']==2).sum():,} ({(df['result']==2).mean()*100:.1f}%)")

# ============================================
# 第三部分：特徵工程
# ============================================

print("\n[3/6] 特徵工程...")

def calculate_rolling_stats(df, team_col, goals_col, xg_col=None, windows=[5, 10]):
    """計算滾動平均統計"""
    for window in windows:
        df[f'rolling_{window}_{goals_col}'] = df.groupby(team_col)[goals_col].transform(
            lambda x: x.rolling(window=window, min_periods=1).mean()
        )
        if xg_col and xg_col in df.columns:
            df[f'rolling_{window}_{xg_col}'] = df.groupby(team_col)[xg_col].transform(
                lambda x: x.rolling(window=window, min_periods=1).mean()
            )
    return df

# 滾動統計
df = calculate_rolling_stats(df, 'home_team', 'home_goals', 'xg', [5, 10])
df = calculate_rolling_stats(df, 'away_team', 'away_goals', 'xga', [5, 10])

# 主場優勢
df['home_advantage'] = 1

# 聯賽主場優勢
try:
    league_home_adv = df.groupby('div')['result'].apply(
        lambda x: (x == 0).mean() - (x == 2).mean()
    ).to_dict()
    df['league_home_adv'] = df['div'].map(league_home_adv)
except:
    df['league_home_adv'] = 0

# 球隊實力評分
def calculate_team_strength(df, team_col, result_col, prefix='strength', windows=[10]):
    for window in windows:
        col_name = f'{prefix}_{window}_{team_col[:3]}'
        df[col_name] = df.groupby(team_col)[result_col].transform(
            lambda x: x.rolling(window=window, min_periods=1).mean()
        )
    return df

df = calculate_team_strength(df, 'home_team', 'result', 'home_str', [10])
df = calculate_team_strength(df, 'away_team', 'result', 'away_str', [10])
df['strength_diff'] = df['home_str_10_hom'] - df['away_str_10_awa'].fillna(0.5)

# xG 離散度特徵 (新增!)
if 'xg' in df.columns:
    df['xg_variance'] = df.groupby('home_team')['xg'].transform(
        lambda x: x.rolling(window=10, min_periods=1).var()
    ).fillna(0)
    df['xg_std'] = np.sqrt(df['xg_variance'])
    print(f"  [OK] 添加 xG 離散度特徵")

# 傷停模擬特徵 (新增!)
np.random.seed(42)
df['home_injuries'] = np.random.poisson(2.0, len(df))
df['away_injuries'] = np.random.poisson(2.0, len(df))
df['home_impact_score'] = df['home_injuries'] * 2.0
df['away_impact_score'] = df['away_injuries'] * 2.0
df['impact_diff'] = df['away_impact_score'] - df['home_impact_score']

print(f"  [OK] 添加傷停影響特徵")

# ============================================
# 第四部分：選擇特徵欄位
# ============================================

print("\n[4/6] 選擇特徵...")

features = [
    # 基本特徵
    'home_advantage',
    'league_home_adv',
    
    # 滾動進球
    'rolling_5_home_goals',
    'rolling_5_away_goals',
    'rolling_10_home_goals',
    'rolling_10_away_goals',
    
    # 離散度特徵
    'strength_diff',
]

# 添加 xG 特徵
if 'rolling_5_xg' in df.columns:
    features.extend([
        'rolling_5_xg', 'rolling_10_xg',
        'rolling_5_xga', 'rolling_10_xga',
        'xg_std'
    ])

# 添加傷停特徵
features.extend([
    'home_injuries', 'away_injuries',
    'home_impact_score', 'away_impact_score',
    'impact_diff'
])

target = 'result'

# 移除空值
df_clean = df.dropna(subset=features + [target])

print(f"  [OK] 特徵數量: {len(features)}")
print(f"  [OK] 有效樣本: {len(df_clean):,}")
print(f"\n  特徵列表:")
for i, f in enumerate(features, 1):
    print(f"    {i:2d}. {f}")

# ============================================
# 第五部分：訓練 Stacking 集成模型
# ============================================

print("\n[5/6] 訓練 Stacking 集成模型...")

X = df_clean[features].fillna(0)
y = df_clean[target].values

# 分割數據 (時間序列分割)
split_idx = int(len(X) * 0.8)
X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
y_train, y_test = y[:split_idx], y[split_idx:]

print(f"  訓練集: {len(X_train):,} 條")
print(f"  測試集: {len(X_test):,} 條")

# 創建基礎模型
base_models = [
    XGBoostModel(n_estimators=200, learning_rate=0.05, max_depth=6),
    RandomForestModel(n_estimators=200, max_depth=10),
    GradientBoostingModel(n_estimators=150, learning_rate=0.05, max_depth=5),
    LogisticRegressionModel(C=1.0)
]

# 創建 Stacking 集成
stacking = StackingEnsemble(
    base_models=base_models,
    meta_model=LogisticRegressionModel(C=0.5),
    cv_folds=5,
    use_bayesian_weights=True
)

# 訓練
print("\n  開始訓練...")
stacking.fit(X_train, y_train)

# ============================================
# 第六部分：評估與保存
# ============================================

print("\n[6/6] 模型評估與保存...")

from sklearn.metrics import (
    accuracy_score, brier_score_loss, log_loss,
    classification_report, confusion_matrix
)

# 預測
y_pred = stacking.predict(X_test)
y_pred_proba = stacking.predict_proba(X_test)

# 評估指標
acc = accuracy_score(y_test, y_pred)
brier = brier_score_loss(y_test, y_pred_proba, labels=[0, 1, 2])
ce = log_loss(y_test, y_pred_proba, labels=[0, 1, 2])

print(f"\n  === 模型評估結果 ===")
print(f"  準確率 (Accuracy): {acc:.2%}")
print(f"  Brier Score: {brier:.4f} (越小越好)")
print(f"  交叉熵損失: {ce:.4f} (越小越好)")

# 混淆矩陣
print(f"\n  混淆矩陣:")
cm = confusion_matrix(y_test, y_pred)
print(f"               預測主勝  預測和局  預測客勝")
print(f"  實際主勝:    {cm[0,0]:5d}   {cm[0,1]:5d}   {cm[0,2]:5d}")
print(f"  實際和局:    {cm[1,0]:5d}   {cm[1,1]:5d}   {cm[1,2]:5d}")
print(f"  實際客勝:    {cm[2,0]:5d}   {cm[2,1]:5d}   {cm[2,2]:5d}")

# 詳細分類報告
print(f"\n  分類報告:")
report = classification_report(y_test, y_pred, 
                               target_names=['主勝', '和局', '客勝'])
print(report)

# 集成統計
print(f"\n  === 集成模型權重 ===")
stats = stacking.get_ensemble_stats()
for name, weight in stats['model_weights'].items():
    print(f"    {name:25s}: {weight:.3f}")

print(f"\n  === 各模型驗證準確率 ===")
for name, score in stats['validation_scores'].items():
    print(f"    {name:25s}: {score:.2%}")

print(f"\n  === 模型信心度 ===")
for name, conf in stats['model_confidence'].items():
    print(f"    {name:25s}: {conf:.3f}")

# 保存模型
model_path = os.path.join(os.path.dirname(__file__), 'xgb_model_v3.pkl')
with open(model_path, 'wb') as f:
    pickle.dump(stacking, f)
print(f"\n  [OK] 模型已保存: {model_path}")

# 保存特徵名稱
feature_path = os.path.join(os.path.dirname(__file__), 'features_v3.pkl')
with open(feature_path, 'wb') as f:
    pickle.dump(features, f)
print(f"  [OK] 特徵已保存: {feature_path}")

# ============================================
# 第七部分：數學模型配置
# ============================================

print("\n" + "=" * 70)
print("數學模型配置摘要")
print("=" * 70)

# 負二項分布測試
print("\n[1] 負二項分布進球模型:")
nb_model = NegativeBinomialModel(1.5, 1.0)
nb_probs = nb_model.calculate_probabilities()
print(f"  測試 (1.5 vs 1.0):")
print(f"    主勝概率: {nb_probs['home_win']:.1%}")
print(f"    和局概率: {nb_probs['draw']:.1%}")
print(f"    客勝概率: {nb_probs['away_win']:.1%}")
print(f"    離散參數: {nb_probs['dispersion']:.2f}")

# 動態K Elo測試
print("\n[2] 動態K Elo評分系統:")
elo = DynamicKEloSystem()
test_matches = [
    ("Man City", "Liverpool", 3, 1),
    ("Man City", "Arsenal", 2, 2),
    ("Man City", "Chelsea", 1, 0),
]
for home, away, hg, ag in test_matches:
    elo.update_ratings(home, away, hg, ag)
print(f"  Man City Rating: {elo.get_rating('Man City'):.1f}")
print(f"  Liverpool Rating: {elo.get_rating('Liverpool'):.1f}")
print(f"  Arsenal Rating: {elo.get_rating('Arsenal'):.1f}")
print(f"  Chelsea Rating: {elo.get_rating('Chelsea'):.1f}")

# 信心度Kelly測試
print("\n[3] 信心度Kelly資金管理:")
kelly = ConfidenceKelly(base_fraction=0.5, initial_bankroll=500)
kelly_results = [
    (0.55, 2.0, 0.7, 0.1, 0.50),
    (0.60, 1.9, 0.8, 0.08, 0.48),
    (0.45, 3.5, 0.5, 0.15, 0.45),
]
print(f"  初始資金: $500")
print(f"  Kelly分數: 50%")
for prob, odds, conf, unc, market_prob in kelly_results:
    result = kelly.calculate(prob, odds, conf, unc, market_prob)
    print(f"\n  測試案例 (P={prob:.0%}, Odds={odds}, Conf={conf:.0%}):")
    print(f"    Kelly%: {result.kelly_pct:.2%}")
    print(f"    投注額: ${result.stake:.2f}")
    print(f"    EV: {result.ev:.3f}")
    print(f"    優勢: {result.edge:.3f}")
    print(f"    風險: {result.risk_level}")

# 蒙地卡羅模擬測試
print("\n[4] 蒙地卡羅模擬V3:")
mc = MonteCarloSimulatorV3(1.5, 1.0, iterations=10000, use_nbinom=True)
mc_result = mc.run_simulation()
print(f"  主勝: {mc_result['mc_home_win']:.1%}")
print(f"  和局: {mc_result['mc_draw']:.1%}")
print(f"  客勝: {mc_result['mc_away_win']:.1%}")
print(f"  大2.5: {mc_result['mc_over_2.5']:.1%}")
print(f"  主隊期望進球: {mc_result['expected_goals']['home']:.2f} ± {np.sqrt(mc_result['expected_goals']['home_var']):.2f}")
print(f"  95%置信區間: [{mc_result['confidence_95']['home_goals_ci'][0]:.0f}, {mc_result['confidence_95']['home_goals_ci'][1]:.0f}]")

# ============================================
# 總結
# ============================================

print("\n" + "=" * 70)
print("訓練完成!")
print("=" * 70)

summary = f"""
============================================================
Stacking 集成學習訓練摘要 v3
============================================================

數據摘要:
  - 總比賽數: {len(df_clean):,}
  - 訓練集: {len(X_train):,}
  - 測試集: {len(X_test):,}
  - 特徵數: {len(features)}

Stacking 集成配置:
  - 基礎模型: XGBoost, Random Forest, Gradient Boosting, Logistic Regression
  - 元學習器: Logistic Regression
  - 交叉驗證: 5折
  - 權重優化: 貝葉斯優化

模型性能:
  - 準確率: {acc:.2%}
  - Brier Score: {brier:.4f}
  - 交叉熵: {ce:.4f}

改進特點:
  1. 負二項分布處理進球過離散
  2. 動態K因子 Elo 評分
  3. 信心度 Kelly 資金管理
  4. Stacking 多模型集成
  5. xG 離散度特徵

保存文件:
  - 模型: xgb_model_v3.pkl
  - 特徵: features_v3.pkl

============================================================
"""

print(summary)

# 保存摘要
summary_path = 'training_summary_v3.txt'
with open(summary_path, 'w', encoding='utf-8') as f:
    f.write(summary)
print(f"\n[OK] 訓練摘要已保存: {summary_path}")
