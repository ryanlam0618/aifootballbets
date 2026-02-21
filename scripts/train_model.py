#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚽ 足球 AI 模型訓練腳本 (整合版 v7.0)

功能：
- XGBoost 機器學習訓練
- 滾動平均特徵工程
- 負二項分布離散校準

作者: AI Betting System
版本: 7.0
"""

import sys
import os
import pandas as pd
import numpy as np
import pickle

# 強制 UTF-8 編碼
sys.stdout.reconfigure(encoding='utf-8')

print("=" * 70)
print("⚽ 足球 AI 投注系統 - 模型訓練 (整合版 v7.0)")
print("=" * 70)

# ============================================
# 1. 載入數據
# ============================================
print("\n[1/6] 載入歷史數據...")

possible_paths = [
    'data/history_data.csv',
    'data/test_historic.csv',
]

df = None
for path in possible_paths:
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, encoding='utf-8-sig', low_memory=False)
            print(f"  [OK] 載入: {path}")
            break
        except:
            try:
                df = pd.read_csv(path, encoding='latin-1', low_memory=False)
                print(f"  [OK] 載入: {path}")
                break
            except:
                continue

if df is None:
    print("  [ERROR] 無法找到歷史數據檔案")
    sys.exit(1)

df.columns = df.columns.str.strip().str.lower().str.replace('\ufeff', '')
print(f"  [OK] 總記錄: {len(df):,}")

# 欄位映射
column_mapping = {
    'fthg': 'home_goals', 'ftag': 'away_goals',
    'hometeam': 'home_team', 'awayteam': 'away_team',
    'xg': 'xg', 'xga': 'xga', 'league': 'league', 'div': 'div', 'date': 'date'
}
for old_col, new_col in column_mapping.items():
    if old_col in df.columns:
        df.rename(columns={old_col: new_col}, inplace=True)

# ============================================
# 2. 數據預處理
# ============================================
print("\n[2/6] 數據預處理...")

if 'date' in df.columns:
    df['date'] = pd.to_datetime(df['date'], dayfirst=False, errors='coerce')
    df = df.sort_values('date')

df = df.dropna(subset=['home_goals', 'away_goals'])
print(f"  [OK] 有效比賽: {len(df):,}")

conditions = [
    (df['home_goals'] > df['away_goals']),
    (df['home_goals'] == df['away_goals']),
    (df['home_goals'] < df['away_goals'])
]
df['result'] = np.select(conditions, [0, 1, 2])

print(f"  主勝: {(df['result']==0).mean()*100:.1f}% | 和局: {(df['result']==1).mean()*100:.1f}% | 客勝: {(df['result']==2).mean()*100:.1f}%")

# ============================================
# 3. 特徵工程
# ============================================
print("\n[3/6] 特徵工程...")

def calc_rolling(df, team_col, goals_col, xg_col=None, windows=[5, 10]):
    for w in windows:
        df[f'r{w}_{goals_col}'] = df.groupby(team_col)[goals_col].transform(
            lambda x: x.shift(1).rolling(window=w, min_periods=1).mean())
        if xg_col and xg_col in df.columns:
            df[f'r{w}_{xg_col}'] = df.groupby(team_col)[xg_col].transform(
                lambda x: x.shift(1).rolling(window=w, min_periods=1).mean())
    return df

if 'home_team' in df.columns:
    df = calc_rolling(df, 'home_team', 'home_goals', 'xg', [5, 10])
    df = calc_rolling(df, 'away_team', 'away_goals', 'xga', [5, 10])

df['home_advantage'] = 1
if 'div' in df.columns:
    try:
        lha = df.groupby('div')['result'].apply(lambda x: (x==0).mean()-(x==2).mean()).to_dict()
        df['league_home_adv'] = df['div'].map(lha)
    except: df['league_home_adv'] = 0
else: df['league_home_adv'] = 0

features = ['home_advantage', 'league_home_adv', 'r5_home_goals', 'r5_away_goals', 'r10_home_goals', 'r10_away_goals']
if 'r5_xg' in df.columns:
    features.extend(['r5_xg', 'r10_xg', 'r5_xga', 'r10_xga'])

print(f"  [OK] 特徵數: {len(features)}")

# ============================================
# 4. 訓練 XGBoost 模型
# ============================================
print("\n[4/6] 訓練 XGBoost 模型...")

df_clean = df.dropna(subset=features + ['result'])
print(f"  [OK] 訓練樣本: {len(df_clean):,}")

X = df_clean[features].fillna(0)
y = df_clean['result']

from sklearn.model_selection import train_test_split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

try:
    from xgboost import XGBClassifier
    from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
    
    model = XGBClassifier(n_estimators=200, learning_rate=0.05, max_depth=6,
        min_child_weight=3, subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=1, eval_metric='mlogloss', random_state=42, use_label_encoder=False)
    
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    preds_proba = model.predict_proba(X_test)
    
    acc = accuracy_score(y_test, preds)
    brier = brier_score_loss(y_test, preds_proba, labels=[0,1,2])
    ce = log_loss(y_test, preds_proba, labels=[0,1,2])
    
    print(f"\n  準確率: {acc:.2%} | Brier: {brier:.4f} | LogLoss: {ce:.4f}")
    
    print(f"\n  特徵重要性 (Top 5):")
    for feat, imp in sorted(zip(features, model.feature_importances_), key=lambda x: -x[1])[:5]:
        print(f"    {feat}: {imp:.4f}")
    
    model_path = os.path.join(os.path.dirname(__file__), 'xgb_model.pkl')
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    print(f"\n  [OK] 模型已保存: {model_path}")
    ml_success = True
except ImportError:
    print("  [WARN] 請安裝 XGBoost: pip install xgboost")
    ml_success = False
except Exception as e:
    print(f"  [ERROR] {e}")
    ml_success = False

# ============================================
# 5. 離散參數估計
# ============================================
print("\n[5/6] 負二項分布校準...")

def est_disp(goals, mu):
    var = np.var(goals)
    if var <= mu: return 0.1
    return max(0.1, min(3.0, (var - mu) / (mu ** 2)))

if 'home_goals' in df.columns and 'league' in df.columns:
    league_disp = {}
    for league in df['league'].unique():
        ld = df[df['league']==league]
        league_disp[league] = (est_disp(ld['home_goals'].dropna(), ld['home_goals'].mean()) + 
                               est_disp(ld['away_goals'].dropna(), ld['away_goals'].mean())) / 2
    print(f"  [OK] 離散參數已計算")
    disp_path = os.path.join(os.path.dirname(__file__), 'dispersion_params.pkl')
    with open(disp_path, "wb") as f:
        pickle.dump(league_disp, f)

# ============================================
# 6. 數據摘要
# ============================================
print("\n[6/6] 數據摘要...")
print(f"\n  總比賽: {len(df):,} | 聯賽: {df['league'].nunique() if 'league' in df.columns else 'N/A'}")
if 'xg' in df.columns:
    print(f"  xG覆蓋: {df['xg'].notna().mean()*100:.1f}%")

print("\n" + "=" * 70)
print("✅ 訓練完成!")
print("=" * 70)
print("\n後續步驟:")
print("  1. 運行 'python app.py' 啟動分析系統")
print("  2. 選擇比賽並進行分析")
