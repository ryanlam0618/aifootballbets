import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

print("="*60)
print("修復 CSV 文件 (移除 Git 衝突標記)")
print("="*60)

DATA_PATH = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\data\big_five_history.csv"
BACKUP_PATH = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\data\big_five_history_conflicted.csv"

print("\n[1] 備份衝突文件...")
with open(DATA_PATH, 'r', encoding='utf-8-sig') as f:
    content = f.read()

with open(BACKUP_PATH, 'w', encoding='utf-8-sig') as f:
    f.write(content)
print(f"    備份到: {BACKUP_PATH}")

print("\n[2] 移除衝突標記並保存...")
# 移除衝突標記行
lines = content.split('\n')
clean_lines = [line for line in lines if not line.startswith('<<<<<<<') 
               and not line.startswith('>>>>>>>') 
               and not line.startswith('=======')]

# 重新組合格式錯誤的行
# 某些行可能有過多字段，需要清理
clean_content = '\n'.join(clean_lines)

with open(DATA_PATH, 'w', encoding='utf-8-sig') as f:
    f.write(clean_content)
print("    衝突標記已移除")

print("\n[3] 讀取並驗證...")
df = pd.read_csv(DATA_PATH, encoding='utf-8-sig', low_memory=False, on_bad_lines='skip')
print(f"    記錄數: {len(df)}")
print(f"    欄位數: {len(df.columns)}")
print(f"    欄位名稱: {list(df.columns)[:10]}")

print("\n[4] 檢查必要欄位...")
# 確保必要的欄位存在
if 'home_team' not in df.columns and 'HomeTeam' in df.columns:
    print("    添加 home_team, away_team, home_goals, away_goals...")
    df['home_team'] = df['HomeTeam'].astype(str).str.strip()
    df['away_team'] = df['AwayTeam'].astype(str).str.strip()
    df['home_goals'] = pd.to_numeric(df['FTHG'], errors='coerce').fillna(0).astype(int)
    df['away_goals'] = pd.to_numeric(df['FTAG'], errors='coerce').fillna(0).astype(int)
    df.to_csv(DATA_PATH, index=False)
    print("    欄位已添加並保存")

# 檢查
if 'home_team' in df.columns:
    print(f"    有效球隊: {df['home_team'].nunique()}")
    print(f"    有效記錄: {len(df.dropna(subset=['home_team']))}")
else:
    print("    ⚠️ 仍然缺少 home_team 欄位")

print("\n" + "="*60)
print("✅ CSV 文件修復完成！")
print("="*60)
