import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

print("="*60)
print("修復重複欄位問題")
print("="*60)

DATA_PATH = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\data\big_five_history.csv"

print("\n[1] 讀取 CSV 文件...")
df = pd.read_csv(DATA_PATH, encoding='utf-8-sig', low_memory=False, on_bad_lines='skip')
print(f"    原始記錄數: {len(df)}")
print(f"    原始欄位數: {len(df.columns)}")

# 檢查重複欄位
print("\n[2] 檢查重複欄位...")
duplicate_cols = []
for col in df.columns:
    count = df.columns.tolist().count(col)
    if count > 1:
        duplicate_cols.append(col)
        
if duplicate_cols:
    print(f"    發現重複欄位: {set(duplicate_cols)}")
else:
    print("    沒有發現重複欄位")

# 移除重複欄位 (保留最後一個)
print("\n[3] 移除重複欄位...")
df = df.loc[:, ~df.columns.duplicated(keep='last')]
print(f"    清理後欄位數: {len(df.columns)}")

# 確保必要欄位存在
print("\n[4] 檢查必要欄位...")
if 'home_team' not in df.columns and 'HomeTeam' in df.columns:
    print("    添加 home_team 欄位...")
    df['home_team'] = df['HomeTeam'].astype(str).str.strip()
    df['away_team'] = df['AwayTeam'].astype(str).str.strip()
    df['home_goals'] = pd.to_numeric(df['FTHG'], errors='coerce').fillna(0).astype(int)
    df['away_goals'] = pd.to_numeric(df['FTAG'], errors='coerce').fillna(0).astype(int)

# 移除沒有 home_team 的行
print("\n[5] 清理數據...")
before = len(df)
df = df.dropna(subset=['home_team'])
df = df[df['home_team'].astype(str).str.strip() != '']
after = len(df)
print(f"    移除無效行: {before - after} 行")

# 保存
print("\n[6] 保存修復後的文件...")
df.to_csv(DATA_PATH, index=False)
print(f"    保存完成")

print("\n[7] 驗證...")
df2 = pd.read_csv(DATA_PATH, encoding='utf-8-sig', low_memory=False)
print(f"    記錄數: {len(df2)}")
print(f"    欄位數: {len(df2.columns)}")
print(f"    home_team 欄位數: {df2.columns.tolist().count('home_team')}")
print(f"    有效球隊: {df2['home_team'].nunique()}")
print(f"    聯賽數量: {df2['league'].nunique() if 'league' in df2.columns else df2['Div'].nunique()}")

print("\n" + "="*60)
print("✅ 修復完成！")
print("="*60)
