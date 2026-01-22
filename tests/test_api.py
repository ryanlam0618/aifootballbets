from openai import OpenAI
from config import settings
import sys

# 強制顯示輸出
sys.stdout.reconfigure(encoding='utf-8')

print("========================================")
print("🔗 API 連線診斷工具")
print("========================================")
print(f"測試 Base URL: {settings.API_BASE_URL}")
print(f"測試 API Key: {settings.GROK_API_KEY[:4]}****{settings.GROK_API_KEY[-4:]}")
print(f"測試 模型: {settings.MODEL_GROK}")
print("-" * 40)

client = OpenAI(
    base_url=settings.API_BASE_URL,
    api_key=settings.GROK_API_KEY
)

try:
    print("🚀 發送測試請求中...", flush=True)
    response = client.chat.completions.create(
        model=settings.MODEL_GROK,
        messages=[{"role": "user", "content": "Hi, return the word 'Success'."}],
        max_tokens=10
    )
    
    print("\n✅ 連線成功！")
    print("回傳內容:", response.choices[0].message.content)
    
except Exception as e:
    print("\n❌ 連線失敗！")
    print(f"錯誤訊息: {e}")
    print("\n💡 建議：")
    print("1. 請檢查 config.py 中的 API_BASE_URL 是否正確。")
    print("2. 嘗試將 config.py 中的網址改為 'https://relay.gpt-best.com/v1' 試試看。")
    print("3. 確認該服務商是否支援 'gpt-4o' 模型名稱。")

input("\n按 Enter 結束...")