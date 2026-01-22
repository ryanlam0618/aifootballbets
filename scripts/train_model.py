import pandas as pd
import numpy as np
import pickle
import os
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from config import settings

# 1. 讀取數據
print("📂 讀取歷史數據...")
if not os.path.exists(settings.HISTORY_CSV_PATH):
    print("❌ 找不到歷史數據 csv")
    exit()

try:
    df = pd.read_csv(settings.HISTORY_CSV_PATH, encoding='utf-8-sig', low_memory=False)
except:
    df = pd.read_csv(settings.HISTORY_CSV_PATH, encoding='latin-1', low_memory=False)

df.columns = df.columns.str.strip().str.lower().str.replace('\ufeff', '')

# 2. 特徵工程 (Feature Engineering)
print("🛠️ 正在構建特徵 (Feature Engineering)...")

# 轉換日期
df['date'] = pd.to_datetime(df['date'], dayfirst=True, errors='coerce')
df = df.sort_values('date')

# 目標變數：主勝(0), 平(1), 客勝(2)
conditions = [
    (df['home_goals'] > df['away_goals']),
    (df['home_goals'] == df['away_goals']),
    (df['home_goals'] < df['away_goals'])
]
df['result'] = np.select(conditions, [0, 1, 2])

# 計算滾動平均 (Rolling Means) - 過去 5 場平均進球
def calculate_rolling_stats(team_df):
    team_df['rolling_goals'] = team_df['goals'].rolling(window=5, min_periods=1).mean()
    return team_df

# 這邊需要將主客場數據拆開再合併計算，為了簡化示範，我們做一個簡單的 Elo 特徵
# 假設已有 Elo 計算邏輯，這裡直接模擬特徵
df['elo_diff'] = np.random.normal(0, 100, len(df)) # 實際應從 HistoryRepo 匯入 Elo 數值
df['home_advantage'] = 1 # 固定主場優勢特徵

# 選擇特徵欄位
features = ['elo_diff', 'home_advantage'] # 實際專案應包含 50+ 特徵
target = 'result'

# 移除空值
df_clean = df.dropna(subset=features + [target])

# 3. 訓練模型
print("🧠 開始訓練 XGBoost 模型...")
X = df_clean[features]
y = df_clean[target]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = XGBClassifier(
    n_estimators=100,
    learning_rate=0.1,
    max_depth=5,
    use_label_encoder=False,
    eval_metric='mlogloss'
)

model.fit(X_train, y_train)

# 4. 評估與儲存
preds = model.predict(X_test)
acc = accuracy_score(y_test, preds)
print(f"✅ 模型訓練完成！測試集準確率: {acc:.2%}")

model_path = os.path.join(os.path.dirname(__file__), "xgb_model.pkl")
with open(model_path, "wb") as f:
    pickle.dump(model, f)

print(f"💾 模型已儲存至: {model_path}")