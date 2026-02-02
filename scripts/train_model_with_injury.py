import sys
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
import pickle
import os
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from config import settings

# 1. 讀取數據
print("Loading historical data...")
if not os.path.exists(settings.HISTORY_CSV_PATH):
    print("ERROR: CSV file not found")
    exit()

try:
    df = pd.read_csv(settings.HISTORY_CSV_PATH, encoding='utf-8-sig', low_memory=False)
except:
    df = pd.read_csv(settings.HISTORY_CSV_PATH, encoding='latin-1', low_memory=False)

df.columns = df.columns.str.strip().str.lower().str.replace('\ufeff', '')

# 標準化欄位名稱
column_mapping = {
    'fthg': 'home_goals',
    'ftag': 'away_goals',
    'hthg': 'ht_home_goals',
    'htag': 'ht_away_goals',
    'hometeam': 'home_team',
    'awayteam': 'away_team',
    'xg': 'xg',
    'xga': 'xga',
}
for old_col, new_col in column_mapping.items():
    if old_col in df.columns:
        df.rename(columns={old_col: new_col}, inplace=True)

# 2. 特徵工程 (Feature Engineering) - 包含傷停特徵
print("Building features...")

# 轉換日期
df['date'] = pd.to_datetime(df['date'], dayfirst=False, errors='coerce')
df = df.sort_values('date')

# 移除沒有比分數據的行
df = df.dropna(subset=['home_goals', 'away_goals'])
print(f"Valid matches: {len(df)}")

# 目標變數：主勝(0), 平(1), 客勝(2)
conditions = [
    (df['home_goals'] > df['away_goals']),
    (df['home_goals'] == df['away_goals']),
    (df['home_goals'] < df['away_goals'])
]
df['result'] = np.select(conditions, [0, 1, 2])

# 計算滾動平均 (Rolling Means)
def calculate_rolling_stats(df, team_col, goals_col, xg_col=None, windows=[5, 10]):
    for window in windows:
        df[f'rolling_{window}_{goals_col}'] = df.groupby(team_col)[goals_col].transform(
            lambda x: x.rolling(window=window, min_periods=1).mean()
        )
        if xg_col and xg_col in df.columns:
            df[f'rolling_{window}_{xg_col}'] = df.groupby(team_col)[xg_col].transform(
                lambda x: x.rolling(window=window, min_periods=1).mean()
            )
    return df

# 計算滾動統計
df = calculate_rolling_stats(df, 'home_team', 'home_goals', 'xg', [5, 10])
df = calculate_rolling_stats(df, 'away_team', 'away_goals', 'xga', [5, 10])

# 主場優勢特徵
df['home_advantage'] = 1

# 聯賽主場優勢
try:
    league_home_adv = df.groupby('div')['result'].apply(
        lambda x: (x == 0).mean() - (x == 2).mean()
    ).to_dict()
    df['league_home_adv'] = df['div'].map(league_home_adv)
except:
    df['league_home_adv'] = 0

# ========== 新增傷停特徵 (模擬) ==========
# 這些數據來自 injury_data.py
# 在實際使用時，需要從真實 API 獲取

print("Adding injury features...")

# 模擬傷停數據 (因為真實數據需要 API 接入)
# 實際部署時替換為真實數據
np.random.seed(42)  # 確保可重現

def simulate_injury_features(df):
    """模擬傷停特徵 - 實際使用時從 injury_data.py 獲取"""
    n = len(df)

    # 傷停數量 (符合現實分布: 平均 2-4 人)
    df['home_injuries'] = np.random.poisson(2.5, n)
    df['away_injuries'] = np.random.poisson(2.5, n)
    df['home_suspensions'] = np.random.poisson(0.5, n)
    df['away_suspensions'] = np.random.poisson(0.5, n)

    # 影響分數 (0-10)
    df['home_impact_score'] = df['home_injuries'] * 2.5 + df['home_suspensions'] * 3.0
    df['away_impact_score'] = df['away_injuries'] * 2.5 + df['away_suspensions'] * 3.0

    # 影響差異 (負值表示主隊更有利)
    df['impact_diff'] = df['away_impact_score'] - df['home_impact_score']

    # 核心球員傷停
    df['home_key_missing'] = (df['home_impact_score'] > 7).astype(int)
    df['away_key_missing'] = (df['away_impact_score'] > 7).astype(int)

    return df

df = simulate_injury_features(df)

# ========== 選擇特徵欄位 ==========

features = [
    # 基本特徵
    'home_advantage',
    'league_home_adv',

    # 滾動進球
    'rolling_5_home_goals',
    'rolling_5_away_goals',
    'rolling_10_home_goals',
    'rolling_10_away_goals',

    # xG 特徵
    'rolling_5_xg',
    'rolling_10_xg',
    'rolling_5_xga',
    'rolling_10_xga',

    # ========== 新增傷停特徵 ==========
    'home_injuries',
    'away_injuries',
    'home_suspensions',
    'away_suspensions',
    'home_impact_score',
    'away_impact_score',
    'impact_diff',
    'home_key_missing',
    'away_key_missing',
]

target = 'result'

# 移除空值
df_clean = df.dropna(subset=features + [target])
print(f"Features: {len(features)}")
print(f"Feature list: {features}")
print(f"Samples after cleaning: {len(df_clean)}")

# 3. 訓練模型
print("Training XGBoost model with injury features...")
X = df_clean[features]
y = df_clean[target]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

model = XGBClassifier(
    n_estimators=300,
    learning_rate=0.03,
    max_depth=5,
    min_child_weight=4,
    subsample=0.75,
    colsample_bytree=0.75,
    reg_alpha=0.3,
    reg_lambda=1.0,
    eval_metric='mlogloss',
    random_state=42
)

model.fit(X_train, y_train)

# 4. 評估與儲存
preds = model.predict(X_test)
preds_proba = model.predict_proba(X_test)

acc = accuracy_score(y_test, preds)
brier = brier_score_loss(y_test, preds_proba, labels=[0, 1, 2])
ce = log_loss(y_test, preds_proba, labels=[0, 1, 2])

print(f"\nModel training completed!")
print(f"Accuracy: {acc:.2%}")
print(f"Brier Score: {brier:.4f}")
print(f"Cross-Entropy Loss: {ce:.4f}")

# 特徵重要性
print(f"\nFeature Importance (All {len(features)} features):")
importance = model.feature_importances_
for feat, imp in sorted(zip(features, importance), key=lambda x: -x[1]):
    bar = '█' * int(imp * 50)
    print(f"  {feat:30s}: {imp:.4f} {bar}")

# 傷停特徵重要性
injury_features = [f for f in features if 'injury' in f or 'suspension' in f or 'impact' in f]
injury_importance = sum(importance[features.index(f)] for f in injury_features)
print(f"\n📊 Injury Features Total Importance: {injury_importance:.2%}")

model_path = os.path.join(os.path.dirname(__file__), "xgb_model.pkl")
with open(model_path, "wb") as f:
    pickle.dump(model, f)

print(f"\nModel saved to: {model_path}")

# 5. 生成摘要
summary = f"""
============================================================
ML Model Training Summary (With Injury Features)
============================================================

Training Data:
  - Total matches: {len(df)}
  - Valid samples: {len(df_clean)}

Model Configuration:
  - Algorithm: XGBoost Classifier
  - n_estimators: 300
  - learning_rate: 0.03
  - max_depth: 5

Features ({len(features)} total):
  - Basic: home_advantage, league_home_adv
  - Rolling Goals: rolling_5/10 home/away goals
  - xG: rolling_5/10 xG/xGA
  - Injury (NEW): home/away injuries, suspensions, impact scores

Performance Metrics:
  - Accuracy: {acc:.2%}
  - Brier Score: {brier:.4f}
  - Cross-Entropy: {ce:.4f}

Top 10 Features:
"""
for i, (feat, imp) in enumerate(sorted(zip(features, importance), key=lambda x: -x[1])[:10], 1):
    summary += f"  {i}. {feat}: {imp:.4f}\n"

summary += f"""
Injury Features Impact:
  - Total importance: {injury_importance:.2%}
  - Features: {injury_features}

============================================================
"""
print(summary)
