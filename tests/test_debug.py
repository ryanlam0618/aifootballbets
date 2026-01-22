import shutil
import pathlib
import os

print("正在清理 __pycache__ ...")
current_dir = pathlib.Path(__file__).parent

count = 0
for p in current_dir.rglob("__pycache__"):
    try:
        shutil.rmtree(p)
        print(f"✅ 已刪除: {p}")
        count += 1
    except Exception as e:
        print(f"❌ 刪除失敗 {p}: {e}")

print(f"清理完成，共刪除 {count} 個快取資料夾。請重新執行 app.py")