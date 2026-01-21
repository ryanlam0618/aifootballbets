from openai import OpenAI
from typing import List, Dict, Optional
import time
import httpx

class NetworkedLLM:
    """
    基於 xAI 官方文件 (docs.x.ai) 的標準兼容客戶端
    針對 Grok 模型啟用 web_search 工具
    """
    def __init__(self, api_key: str, base_url: str):
        # 設定較長的 timeout，避免網路波動導致斷線
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip('/'),
            timeout=120.0,
            max_retries=2
        )

    def chat_with_search(self, 
                        model: str, 
                        messages: List[Dict[str, str]], 
                        search_enabled: bool = True) -> str:
        """
        發送對話請求，並透過 extra_body 傳遞非標準 tool 參數 (web_search)
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"🌐 發送聯網請求給 {model} (嘗試 {attempt+1}/{max_retries})...")
                
                # 準備請求參數
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "stream": False
                }

                # 根據 xAI 文件，OpenAI 兼容接口使用 tools=[{"type": "web_search"}]
                if search_enabled:
                    # 使用 extra_body 來繞過 openai sdk 的型別檢查 (因為 web_search 不是標準的 function 類型)
                    kwargs["extra_body"] = {
                        "tools": [
                            {
                                "type": "web_search",
                                "web_search": {
                                    "search_result_limit": 5,
                                    "search_context_size": "medium"
                                }
                            }
                        ]
                    }
                    # 確保 System Prompt 鼓勵使用搜尋
                    has_system = False
                    for msg in messages:
                        if msg["role"] == "system":
                            if "search" not in msg["content"]:
                                msg["content"] += " (You have access to a web_search tool. Use it to find real-time information.)"
                            has_system = True
                            break
                    if not has_system:
                        messages.insert(0, {"role": "system", "content": "You are a helpful assistant with web search capabilities."})

                response = self.client.chat.completions.create(**kwargs)

                if hasattr(response, 'choices') and len(response.choices) > 0:
                    return response.choices[0].message.content
                else:
                    return "Error: Empty response from model."

            except Exception as e:
                error_msg = str(e)
                if "RemoteDisconnected" in error_msg or "Connection aborted" in error_msg:
                    print(f"⚠️ 連線不穩定 ({error_msg})")
                else:
                    print(f"❌ API 錯誤: {error_msg}")
                
                if attempt < max_retries - 1:
                    time.sleep(3)
                else:
                    return f"Connection Failed: {error_msg}"
        
        return "Error: Max retries exceeded"