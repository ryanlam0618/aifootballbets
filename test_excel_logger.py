"""
Excel 記錄功能測試腳本
用於測試 ExcelLogger.log_bet 是否正確寫入資料
"""
import sys
import os

# 確保 src 目錄在路徑中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.finance import ExcelLogger, calculate_kelly_stake
from datetime import datetime

def test_excel_logging():
    print("=" * 50)
    print("Excel 記錄功能測試")
    print("=" * 50)

    # 1. 初始化 ExcelLogger
    print("\n[1] 初始化 ExcelLogger...")
    logger = ExcelLogger()
    print(f"    檔案路徑: {logger.filepath}")
    print(f"    檔案是否存在: {os.path.exists(logger.filepath)}")

    # 2. 建立測試資料
    print("\n[2] 建立測試資料...")
    match_info = {
        "league": "Test League",
        "home": "Test Home Team",
        "away": "Test Away Team"
    }
    bet_info = {
        "market": "Match Result",
        "selection": "Home",
        "odds": 2.0,
        "model_probability": 0.55
    }
    stake_info = calculate_kelly_stake(0.55, 2.0, 500)

    print(f"    比賽: {match_info['home']} vs {match_info['away']}")
    print(f"    市場: {bet_info['market']} - {bet_info['selection']}")
    print(f"    賠率: {bet_info['odds']}")
    print(f"    建議下注金額: ${stake_info['stake']:.2f}")

    # 3. 測試寫入
    print("\n[3] 執行寫入測試...")
    print("    調用 logger.log_bet()...")

    try:
        logger.log_bet(match_info, bet_info, stake_info)
        print("    log_bet() 執行完成")

        # 4. 驗證結果
        print("\n[4] 驗證寫入結果...")
        if os.path.exists(logger.filepath):
            import pandas as pd
            df = pd.read_excel(logger.filepath)
            print(f"    檔案存在: OK")
            print(f"    總行數 (含標題): {len(df) + 1}")
            print(f"    資料列數: {len(df)}")

            if len(df) > 0:
                # 顯示最後幾筆資料
                print(f"\n    檔案內容最後 3 筆:")
                print(df.tail(3).to_string())

                # 檢查是否有剛才寫入的資料
                test_data = df[df['Home'] == 'Test Home Team']
                if len(test_data) > 0:
                    print(f"\n    找到測試資料！")
                    print(f"       時間: {test_data.iloc[0]['Date']}")
                    print(f"       聯賽: {test_data.iloc[0]['League']}")
                else:
                    print(f"\n    找不到測試資料，寫入可能失敗！")
            else:
                print(f"\n    檔案為空，寫入失敗！")
        else:
            print(f"    檔案不存在！")

    except Exception as e:
        print(f"    錯誤: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 50)
    print("測試完成")
    print("=" * 50)

if __name__ == "__main__":
    # 確保 Excel 檔案已關閉
    test_excel_logging()
