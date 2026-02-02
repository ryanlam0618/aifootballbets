"""
檢查 Excel 檔案當前狀態
"""
import pandas as pd
import os
from config import settings

print("=" * 50)
print("Excel 檔案狀態檢查")
print("=" * 50)

filepath = settings.EXCEL_FILEPATH
print(f"\n檔案路徑: {filepath}")
print(f"檔案存在: {os.path.exists(filepath)}")

if os.path.exists(filepath):
    try:
        df = pd.read_excel(filepath)
        print(f"總行數 (含標題): {len(df) + 1}")
        print(f"資料筆數: {len(df)}")
        print(f"\n欄位名稱: {list(df.columns)}")
        print(f"\n最後 5 筆資料:")
        print(df.tail(5).to_string())
    except Exception as e:
        print(f"讀取錯誤: {e}")
else:
    print("檔案不存在，無法讀取")
