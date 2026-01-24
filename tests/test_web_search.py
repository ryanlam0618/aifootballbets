import sys
import os
from datetime import datetime

# 確保可以匯入專案模組（添加到專案根目錄）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from src.networking_llm import NetworkedLLM

# 強制輸出編碼
sys.stdout.reconfigure(encoding='utf-8')

def test_realtime_search():
    print("========================================")
    print("🧪 Grok 即時搜尋能力測試")
    print("========================================")
    
    # 檢查 Key
    if not settings.GROK_API_KEY:
        print("❌ 錯誤: config.py 中未設定 GROK_API_KEY")
        return

    print(f"API Base URL: {settings.API_BASE_URL}")
    print(f"Model: {settings.MODEL_GROK}")
    print(f"Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 40)

    # 初始化客戶端
    net_client = NetworkedLLM(settings.GROK_API_KEY, settings.API_BASE_URL)

    # 測試問題 1: X Search (Twitter)
    print("\n[測試 1] X (Twitter) 搜尋測試...")
    q1 = "用中文What are the trending topics on X (Twitter) regarding football/soccer today?"
    print(f"👉 問: {q1}")
    
    res1 = net_client.chat_with_search(
        model=settings.MODEL_GROK,
        messages=[{"role": "user", "content": q1}],
        search_enabled=True
    )
    print(f"🤖 答:\n{res1}\n")

    # 測試問題 2: Web Search (時效性驗證)
    print("-" * 40)
    print("[測試 2] Web Search 時效性驗證...")
    # 問一個昨天的比賽或新聞，強迫它上網
    q2 = f"用中文Search for the latest football match results from yesterday ({datetime.now().strftime('%Y-%m-%d')}). List two specific scores."
    print(f"👉 問: {q2}")

    res2 = net_client.chat_with_search(
        model=settings.MODEL_GROK,
        messages=[{"role": "user", "content": q2}],
        search_enabled=True
    )
    print(f"🤖 答:\n{res2}\n")

if __name__ == "__main__":
    test_realtime_search()