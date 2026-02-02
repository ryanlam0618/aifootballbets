import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

print("="*60)
print("徹底清理 CSV 文件")
print("="*60)

DATA_PATH = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\data\big_five_history.csv"

print("\n[1] 讀取 CSV 文件...")
df = pd.read_csv(DATA_PATH, encoding='utf-8-sig', low_memory=False, on_bad_lines='skip')
print(f"    原始記錄數: {len(df)}")
print(f"    原始欄位數: {len(df.columns)}")

# 清理欄位名稱 (去除 BOM 和空白)
print("\n[2] 清理欄位名稱...")
df.columns = df.columns.str.strip().str.replace('\ufeff', '').str.lower()
print(f"    清理後欄位數: {len(df.columns)}")

# 重新映射欄位
print("\n[3] 重新映射欄位...")
column_mapping = {
    "date": ["date", "match_date", "time", "日期"],
    "league": ["league", "div", "division", "聯賽"],
    "home_team": ["home_team", "hometeam", "home", "主隊"],
    "away_team": ["away_team", "awayteam", "away", "客隊"],
    "home_goals": ["home_goals", "fthg", "h_score", "hg", "主隊進球"],
    "away_goals": ["away_goals", "ftag", "a_score", "ag", "客隊進球"],
}
rename_dict = {}
for standard_col, possible_names in column_mapping.items():
    for col in df.columns:
        if col in possible_names:
            if standard_col not in rename_dict:  # 只映射一次
                rename_dict[col] = standard_col
            break
df.rename(columns=rename_dict, inplace=True)
print(f"    已重命名欄位: {list(rename_dict.keys())}")

# 移除重複欄位
print("\n[4] 移除重複欄位...")
df = df.loc[:, ~df.columns.duplicated(keep='last')]
print(f"    清理後欄位數: {len(df.columns)}")

# 確保必要欄位存在
print("\n[5] 確保必要欄位存在...")
required_cols = ['home_team', 'away_team', 'home_goals', 'away_goals']
for col in required_cols:
    if col not in df.columns:
        print(f"    ⚠️ 缺少 {col} 欄位")
    else:
        print(f"    ✅ {col} 欄位存在")

# 移除沒有 home_team 的行
print("\n[6] 清理數據...")
before = len(df)
df = df.dropna(subset=['home_team'])
df = df[df['home_team'].astype(str).str.strip() != '']
after = len(df)
print(f"    移除無效行: {before - after} 行")

# 保存
print("\n[7] 保存修復後的文件...")
df.to_csv(DATA_PATH, index=False)
print(f"    保存完成")

print("\n[8] 驗證...")
df2 = pd.read_csv(DATA_PATH, encoding='utf-8-sig', low_memory=False)
df2.columns = df2.columns.str.strip().str.replace('\ufeff', '').str.lower()
print(f"    記錄數: {len(df2)}")
print(f"    欄位數: {len(df2.columns)}")
print(f"    home_team 欄位數: {df2.columns.tolist().count('home_team')}")
if 'home_team' in df2.columns:
    print(f"    有效球隊: {df2['home_team'].nunique()}")
    print(f"    Sample: {df2['home_team'].head(3).tolist()}")

print("\n" + "="*60)
print("✅ 修復完成！")
print("="*60)
