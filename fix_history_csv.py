import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
import numpy as np

print("="*60)
print("修復歷史數據文件")
print("="*60)

DATA_PATH = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\data\big_five_history.csv"

# 定義必要的欄位
REQUIRED_COLS = [
    'Date', 'Div', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG',
    'home_team', 'away_team', 'home_goals', 'away_goals',
    'xg', 'xga', 'xG', 'xGA'
]

print(f"\n[1] 讀取 CSV 文件...")
try:
    # 使用更寬鬆的讀取方式
    df = pd.read_csv(DATA_PATH, on_bad_lines='skip', low_memory=False)
    print(f"    原始記錄數: {len(df)}")
    print(f"    原始欄位數: {len(df.columns)}")
except Exception as e:
    print(f"    讀取失敗: {e}")
    sys.exit(1)

print(f"\n[2] 檢查欄位...")
# 檢查是否存在所需的欄位
if 'home_team' not in df.columns and 'HomeTeam' in df.columns:
    print("    發現 'HomeTeam' 但沒有 'home_team'，進行轉換...")
    df['home_team'] = df['HomeTeam'].astype(str).str.strip()
    df['away_team'] = df['AwayTeam'].astype(str).str.strip()
    df['home_goals'] = pd.to_numeric(df['FTHG'], errors='coerce').fillna(0).astype(int)
    df['away_goals'] = pd.to_numeric(df['FTAG'], errors='coerce').fillna(0).astype(int)
    print("    轉換完成")

# 檢查關鍵欄位
key_cols = ['home_team', 'away_team', 'home_goals', 'away_goals']
missing_cols = [c for c in key_cols if c not in df.columns]
if missing_cols:
    print(f"    ⚠️ 缺少欄位: {missing_cols}")
else:
    print("    ✅ 所有關鍵欄位存在")

# 移除沒有 home_team 的行
before = len(df)
df = df.dropna(subset=['home_team'])
df = df[df['home_team'].astype(str).str.strip() != '']
after = len(df)
print(f"    移除無效行: {before - after} 行")

print(f"\n[3] 清理數據...")
# 確保數值欄位正確
df['home_goals'] = pd.to_numeric(df['home_goals'], errors='coerce').fillna(0).astype(int)
df['away_goals'] = pd.to_numeric(df['away_goals'], errors='coerce').fillna(0).astype(int)

# 清理日期
if 'Date' in df.columns:
    df['date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
    # 如果解析失敗，嘗試其他格式
    df['date'] = df['date'].fillna(pd.to_datetime(df['Date'], errors='coerce'))
    print(f"    日期範圍: {df['date'].min()} 到 {df['date'].max()}")

print(f"\n[4] 檢查聯賽...")
if 'Div' in df.columns:
    print(f"    聯賽數量: {df['Div'].nunique()}")
    print(f"    聯賽列表: {df['Div'].unique()[:10].tolist()}")

print(f"\n[5] 保存修復後的文件...")
BACKUP_PATH = DATA_PATH.replace('.csv', '_backup.csv')
df.to_csv(BACKUP_PATH, index=False)
print(f"    備份原文件到: {BACKUP_PATH}")

df.to_csv(DATA_PATH, index=False)
print(f"    保存修復後文件到: {DATA_PATH}")

print(f"\n[6] 最終統計...")
print(f"    總記錄數: {len(df)}")
print(f"    總欄位數: {len(df.columns)}")
print(f"    有效主隊: {df['home_team'].nunique()}")
print(f"    有效客隊: {df['away_team'].nunique()}")

print("\n" + "="*60)
print("✅ 修復完成！")
print("="*60)
