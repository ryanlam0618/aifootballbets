from openai import OpenAI
from typing import List, Dict, Optional
import time
import httpx
import json

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

    def _parse_api_error(self, error_msg: str) -> tuple:
        """
        解析 API 錯誤訊息，返回 (error_type, should_retry)
        """
        if "502" in error_msg or "Bad Gateway" in error_msg:
            return ("502_Bad_Gateway", True)
        elif "503" in error_msg or "Service Unavailable" in error_msg:
            return ("503_Service_Unavailable", True)
        elif "504" in error_msg or "Gateway Timeout" in error_msg:
            return ("504_Gateway_Timeout", True)
        elif "500" in error_msg or "Internal Error" in error_msg:
            return ("500_Internal_Error", True)
        elif "429" in error_msg or "rate" in error_msg.lower():
            return ("429_Rate_Limit", True)
        elif "RemoteDisconnected" in error_msg or "Connection aborted" in error_msg:
            return ("Connection_Lost", True)
        elif "authentication" in error_msg.lower() or "api_key" in error_msg.lower():
            return ("Auth_Error", False)
        else:
            return ("Unknown", True)

    def chat_with_search(self, 
                        model: str, 
                        messages: List[Dict[str, str]], 
                        search_enabled: bool = True) -> str:
        """
        發送對話請求，並透過 extra_body 傳遞非標準 tool 參數 (web_search)
        """
        max_retries = 4  # 增加重試次數
        base_delay = 2   # 基礎延遲秒數
        
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
                error_type, should_retry = self._parse_api_error(error_msg)
                
                # 根據錯誤類型給出不同提示
                if error_type == "502_Bad_Gateway":
                    print(f"⚠️ 502 錯誤: 伺服器暫時無回應 (嘗試 {attempt+1}/{max_retries})")
                elif error_type == "503_Service_Unavailable":
                    print(f"⚠️ 503 錯誤: 服務暫時不可用 (嘗試 {attempt+1}/{max_retries})")
                elif error_type == "504_Gateway_Timeout":
                    print(f"⚠️ 504 錯誤: 閘道超時 (嘗試 {attempt+1}/{max_retries})")
                elif error_type == "429_Rate_Limit":
                    print(f"⚠️ 429 錯誤: 超過速率限制，延長等待時間...")
                    time.sleep(10)  # Rate limit 需要更長等待
                elif error_type == "Auth_Error":
                    print(f"❌ API 認證錯誤，請檢查 API Key")
                    return f"API Error: Authentication failed"
                else:
                    print(f"⚠️ API 錯誤 ({error_type}): {error_msg[:100]}")
                
                if should_retry and attempt < max_retries - 1:
                    # 指數退避策略
                    delay = base_delay * (2 ** attempt) + (attempt * 1)
                    print(f"⏳ 等待 {delay} 秒後重試...")
                    time.sleep(delay)
                else:
                    print(f"❌ 已達最大重試次數 ({max_retries})，放棄請求")
                    return f"API Error ({error_type}): {error_msg[:200]}"
        
        return "Error: Max retries exceeded"