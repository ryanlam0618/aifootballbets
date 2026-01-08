from openai import OpenAI
from typing import List, Dict, Optional
import time

class NetworkedLLM:
    """
    基於 xAI 官方文件 (docs.x.ai) 的標準兼容客戶端
    使用標準 OpenAI SDK 格式，確保與 GPT-Best/xAI 平台相容
    """
    def __init__(self, api_key: str, base_url: str):
        # 根據 xAI 文件，使用標準 OpenAI 客戶端
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip('/')
        )

    def chat_with_search(self, 
                        model: str, 
                        messages: List[Dict[str, str]], 
                        search_enabled: bool = True) -> str:
        """
        發送標準對話請求
        注意：Grok 模型的聯網能力通常是內建的或依賴模型版本，
        我們這裡使用標準協議以避免 400 格式錯誤。
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"🌐 發送標準請求給 {model} (嘗試 {attempt+1}/{max_retries})...")
                
                # 如果開啟搜尋模式，我們在 System Prompt 加強提示
                # 這是標準 OpenAI 協議中唯一能做的事（除非使用 Function Calling）
                if search_enabled:
                    # 檢查是否已有 system prompt
                    has_system = False
                    for msg in messages:
                        if msg["role"] == "system":
                            # 強化提示，要求模型運用其最新的知識庫
                            if "real-time" not in msg["content"]:
                                msg["content"] += " (Please use your internal knowledge base to reflect the latest real-time events from X/Twitter if possible.)"
                            has_system = True
                            break
                    
                    if not has_system:
                        messages.insert(0, {
                            "role": "system", 
                            "content": "You are Grok, an AI with access to real-time information. Please use your latest knowledge."
                        })

                # 發送標準請求 (移除不被支援的 tools 參數)
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    # 避免使用 stream 以簡化處理
                    stream=False
                )

                if hasattr(response, 'choices') and len(response.choices) > 0:
                    return response.choices[0].message.content
                else:
                    return "Error: Empty response from model."

            except Exception as e:
                print(f"❌ API 連線錯誤: {e}")
                if "400" in str(e):
                    return f"API Error 400: 模型或參數不被支援。請確認 config.py 中的模型名稱是否正確 (如 grok-beta)。"
                
                if attempt < max_retries - 1:
                    print("   ⏳ 等待 2 秒後重試...")
                    time.sleep(2)
                else:
                    return f"Connection Error: {str(e)}"
        
        return "Error: Max retries exceeded"
# 簡單測試區
if __name__ == "__main__":
    from config import settings

    test_client = NetworkedLLM(settings.GROK_API_KEY, settings.API_BASE_URL)
    test_messages = [
        {"role": "user", "content": "請告訴我今天有什麼足球新聞？"}
    ]
    result = test_client.chat_with_search(
        model=settings.MODEL_GROK,
        messages=test_messages,
        search_enabled=True
    )
    print("測試結果：", result)
