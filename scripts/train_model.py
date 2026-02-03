#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型訓練腳本 - 使用更新後的歷史數據
"""
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

print("="*70)
print("足球 AI 投注系統 - 模型訓練")
print("="*70)

# 1. 載入數據
print("\n[1/5] 載入歷史數據...")
df = pd.read_csv('data/history_data.csv')
print(f"  [OK] 載入 {len(df):,} 條記錄")

# 2. 數據預處理
print("\n[2/5] 數據預處理...")

# 確保列名正確
if 'league' not in df.columns:
    print("  [ERROR] 缺少 league 列")
    sys.exit(1)

# 過濾有效的比賽（需要有結果）
df = df[df['FTR'].notna()].copy()
print(f"  [OK] 有效比賽: {len(df):,} 條")

# 3. 特徵工程
print("\n[3/5] 特徵工程...")

# 創建目標變量
df['target'] = (df['FTR'] == 'H').astype(int)  # 主勝 = 1, 其他 = 0

# 特徵列表
feature_cols = [
    'home_weighted_xg', 'away_weighted_xg',  # xG
    'home_goals_rolling', 'away_goals_rolling',  # 進球滚动平均
    'home_xg_rolling', 'away_xg_rolling',  # xG滚动平均
    'home_concede_rolling', 'away_concede_rolling',  # 失球滚动
    'home_corners', 'away_corners',  # 角球
    'home_shots', 'away_shots',  # 射門
    'home_shots_on', 'away_shots_on',  # 射正
    'home_yellow', 'away_yellow',  # 黃牌
    'home_red', 'away_red',  # 紅牌
]

# 計算滚动平均 (需要按球隊和主/客場分組)
print("  計算滚动平均...")

def calculate_rolling(df, col, window=5):
    """計算滚动平均"""
    df[f'{col}_rolling'] = df.groupby('home_team')[col].transform(
        lambda x: x.shift(1).rolling(window=window, min_periods=1).mean()
    )
    df[f'away_{col}_rolling'] = df.groupby('away_team')[col].transform(
        lambda x: x.shift(1).rolling(window=window, min_periods=1).mean()
    )

# 使用 xG 作為主要特徵（如果可用）
if 'xG' in df.columns and df['xG'].notna().sum() > 0:
    df['home_weighted_xg'] = df['xG']
    df['away_weighted_xg'] = df['xGA']
else:
    # 使用實際進球作為替代
    df['home_weighted_xg'] = df['home_goals'].rolling(window=5, min_periods=1).transform('mean').shift(1)
    df['away_weighted_xg'] = df['away_goals'].rolling(window=5, min_periods=1).transform('mean').shift(1)

# 計算其他滚动統計
if 'home_goals' in df.columns:
    df['home_goals_rolling'] = df.groupby('home_team')['home_goals'].transform(
        lambda x: x.shift(1).rolling(window=5, min_periods=1).mean()
    )
    df['away_goals_rolling'] = df.groupby('away_team')['away_goals'].transform(
        lambda x: x.shift(1).rolling(window=5, min_periods=1).mean()
    )

if 'xG' in df.columns:
    df['home_xg_rolling'] = df.groupby('home_team')['xG'].transform(
        lambda x: x.shift(1).rolling(window=5, min_periods=1).mean()
    )
    df['away_xg_rolling'] = df.groupby('away_team')['xG'].transform(
        lambda x: x.shift(1).rolling(window=5, min_periods=1).mean()
    )
    df['home_concede_rolling'] = df.groupby('home_team')['xGA'].transform(
        lambda x: x.shift(1).rolling(window=5, min_periods=1).mean()
    )
    df['away_concede_rolling'] = df.groupby('away_team')['xGA'].transform(
        lambda x: x.shift(1).rolling(window=5, min_periods=1).mean()
    )

# 填補缺失值
for col in feature_cols:
    if col in df.columns:
        df[col] = df[col].fillna(df[col].mean())

print(f"  [OK] 特徵數: {len(feature_cols)}")

# 4. 訓練 XGBoost 模型
print("\n[4/5] 訓練 XGBoost 模型...")

try:
    import xgboost as xgb
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, brier_score_loss
    
    # 準備數據
    X = df[feature_cols].fillna(0)
    y = df['target']
    
    # 分割
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # 訓練
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        use_label_encoder=False,
        eval_metric='logloss'
    )
    
    model.fit(X_train, y_train)
    
    # 評估
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    
    acc = accuracy_score(y_test, y_pred)
    brier = brier_score_loss(y_test, y_prob)
    
    print(f"  [OK] 準確率: {acc:.1%}")
    print(f"  [OK] Brier Score: {brier:.4f}")
    
    # 特徵重要性
    importance = model.feature_importances_
    feat_imp = pd.DataFrame({
        'feature': feature_cols,
        'importance': importance
    }).sort_values('importance', ascending=False)
    
    print("\n  特徵重要性 (Top 5):")
    for i, row in feat_imp.head(5).iterrows():
        print(f"    {row['feature']}: {row['importance']:.3f}")
    
    # 保存模型
    model_path = 'data/xgb_model.json'
    model.save_model(model_path)
    print(f"\n  [OK] 模型已保存: {model_path}")
    
    success = True
    
except ImportError:
    print("  [WARN] XGBoost 未安裝，跳過 ML 模型訓練")
    print("  [INFO] 請運行: pip install xgboost")
    success = False
except Exception as e:
    print(f"  [ERROR] 訓練失敗: {e}")
    success = False

# 5. 數學模型準備
print("\n[5/5] 數學模型配置...")

# 計算聯賽平均 xG
league_xg = df.groupby('league').agg({
    'xG': 'mean',
    'xGA': 'mean'
}).round(3)

print("  聯賽平均 xG:")
for league, row in league_xg.iterrows():
    print(f"    {league}: {row['xG']:.2f} - {row['xGA']:.2f}")

# 計算主場優勢
home_advantage = df.groupby('FTR').size()
print(f"  比賽結果分布:")
print(f"    主勝 (H): {(df['FTR']=='H').sum():,} ({(df['FTR']=='H').mean()*100:.1f}%)")
print(f"    和局 (D): {(df['FTR']=='D').sum():,} ({(df['FTR']=='D').mean()*100:.1f}%)")
print(f"    客勝 (A): {(df['FTR']=='A').sum():,} ({(df['FTR']=='A').mean()*100:.1f}%)")

print("\n" + "="*70)
print("訓練完成!")
print("="*70)
print(f"\n數據摘要:")
print(f"  - 總比賽數: {len(df):,}")
print(f"  - 聯賽數: {df['league'].nunique()}")
print(f"  - 日期範圍: {df['Date'].min()} 至 {df['Date'].max()}")
print(f"  - xG 數據覆蓋: {df['xG'].notna().sum():,} ({df['xG'].notna().mean()*100:.1f}%)")
