#!/usr/bin/env python3
"""
測試 DataMerger 類別
"""
import sys
import os
from pathlib import Path

# 切換到 scripts 目錄以正確導入模組
scripts_dir = Path(__file__).parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from scrape_odds import DataMerger

# 測試用例 1: 測試合併 CSV 文件
print("=" * 60)
print("Test 1: Merge CSV files")
print("=" * 60)

# 創建測試數據
test_dir = Path(r"C:\Users\Ryan\python\.vscode\fb_ai_bets\data\archive\test")
test_dir.mkdir(parents=True, exist_ok=True)

temp_file = test_dir / "temp_test.csv"
final_file = test_dir / "final_test.csv"

# 創建臨時文件
with open(temp_file, 'w', encoding='utf-8') as f:
    f.write("name,age,city\n")
    f.write("Alice,30,NYC\n")
    f.write("Bob,25,LA\n")

print(f"Created temp file: {temp_file}")

# 測試合併（最終文件不存在，應該直接移動）
success = DataMerger.merge_csv_files(str(temp_file), str(final_file))
print(f"Merge result: {success}")

if success:
    print(f"Final file exists: {final_file.exists()}")
    if final_file.exists():
        with open(final_file, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"Final file content:\n{content}")

# 測試用例 2: 測試追加數據
print("\n" + "=" * 60)
print("Test 2: Append to existing file")
print("=" * 60)

# 創建新的臨時文件
temp_file2 = test_dir / "temp_test2.csv"
with open(temp_file2, 'w', encoding='utf-8') as f:
    f.write("name,age,city\n")
    f.write("Charlie,35,Chicago\n")
    f.write("Diana,28,Boston\n")

print(f"Created temp file 2: {temp_file2}")

# 測試追加
success2 = DataMerger.merge_csv_files(str(temp_file2), str(final_file))
print(f"Append result: {success2}")

if success2:
    with open(final_file, 'r', encoding='utf-8') as f:
        content = f.read()
        print(f"Final file content after append:\n{content}")

# 清理測試文件
print("\n" + "=" * 60)
print("Cleanup")
print("=" * 60)
if final_file.exists():
    final_file.unlink()
    print(f"Removed: {final_file}")

print("\nAll tests completed!")
