import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\data\big_five_history.csv"

print("="*60)
print("檢查 CSV 文件")
print("="*60)

with open(path, 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()[:10]
    
for i, line in enumerate(lines):
    print(f"Line {i}: {line[:200]}...")

print("\n" + "="*60)
