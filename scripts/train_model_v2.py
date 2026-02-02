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

# 2. 特徵工程 (Feature Engineering)
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

# 球隊實力評分 (基於歷史戰績)
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

# 選擇特徵欄位 - 完整版 (不依賴半場比分)
features = [
    'home_advantage',
    'league_home_adv',
    'rolling_5_home_goals',
    'rolling_5_away_goals',
    'rolling_10_home_goals',
    'rolling_10_away_goals',
]

# 添加 xG 特徵 (如果可用)
if 'rolling_5_xg' in df.columns:
    features.extend(['rolling_5_xg', 'rolling_10_xg', 'rolling_5_xga', 'rolling_10_xga'])

target = 'result'

# 移除空值
df_clean = df.dropna(subset=features + [target])
print(f"Features: {len(features)}")
print(f"Feature list: {features}")
print(f"Samples after cleaning: {len(df_clean)}")

# 3. 訓練模型
print("Training XGBoost model...")
X = df_clean[features]
y = df_clean[target]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

model = XGBClassifier(
    n_estimators=200,
    learning_rate=0.05,
    max_depth=6,
    min_child_weight=3,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_alpha=0.1,
    reg_lambda=1,
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
print(f"\nFeature Importance:")
importance = model.feature_importances_
for feat, imp in sorted(zip(features, importance), key=lambda x: -x[1])[:15]:
    print(f"  {feat}: {imp:.4f}")

model_path = os.path.join(os.path.dirname(__file__), "xgb_model.pkl")
with open(model_path, "wb") as f:
    pickle.dump(model, f)

print(f"\nModel saved to: {model_path}")
