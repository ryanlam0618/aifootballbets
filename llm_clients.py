import json
import re
from openai import OpenAI
from config import settings
from networking_llm import NetworkedLLM

class LLMOrchestrator:
    def _get_client(self, api_key):
        if not api_key: return None
        return OpenAI(base_url=settings.API_BASE_URL, api_key=api_key)

    def _call_model(self, client, model_name, system_prompt, user_prompt, json_mode=False):
        if not client: return None
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        try:
            kwargs = {"model": model_name, "messages": messages, "temperature": 0.7}
            if json_mode: kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**kwargs)
            if hasattr(response, 'choices'): return response.choices[0].message.content
            return str(response)
        except Exception as e:
            error_str = str(e)
            print(f"⚠️ 初次調用失敗 ({model_name}): {error_str}")
            if json_mode and ("response_format" in error_str or "500" in error_str or "400" in error_str):
                print(f"🔄 嘗試移除 JSON 強制模式並重試...")
                try:
                    if "response_format" in kwargs: del kwargs["response_format"]
                    response = client.chat.completions.create(**kwargs)
                    if hasattr(response, 'choices'): return response.choices[0].message.content
                except Exception as e2: print(f"❌ 重試依然失敗: {e2}")
            return None

    def fetch_data_helper(self, query: str):
        client = self._get_client(settings.GEMINI_API_KEY)
        return self._call_model(client, settings.MODEL_GEMINI, "You are a data assistant.", query) or "Data Error"

    def search_and_analyze_market_reaction(self, match_info: str, odds_data_input: any):
        print(f"🤖 [Grok] 正在啟動即時分析：掃描 X 與新聞 ({settings.MODEL_GROK})...")
        net_client = NetworkedLLM(settings.GROK_API_KEY, settings.API_BASE_URL)
        
        odds_text = ""
        if isinstance(odds_data_input, list):
            if odds_data_input and isinstance(odds_data_input[0], dict) and isinstance(odds_data_input[0].get('decimal_odds'), str):
                odds_text = odds_data_input[0]['decimal_odds']
            else:
                odds_text = "\n".join([f"- {p.time_offset}: {p.decimal_odds} ({p.bookmaker})" for p in odds_data_input])
        else:
            odds_text = str(odds_data_input)

        system_prompt = "你是由 xAI 開發的 Grok，擁有即時存取 X (Twitter) 數據的能力。"
        user_content = f"""
        比賽：{match_info}
        【任務】找出這場比賽的最新狀況（首發、傷停），並結合以下【全盤口賠率】進行分析。
        【賠率數據】\n{odds_text}
        請回答：
        1. 雙方最新傷停與狀態（重要！）。
        2. 市場主力資金流向了哪個盤口？
        3. 這是誘盤還是合理調整？
        """
        
        result = net_client.chat_with_search(
            model=settings.MODEL_GROK,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
            search_enabled=True 
        )
        return result if result else "Grok 分析失敗。"

    def analyze_with_super_prompt(self, match_context: dict, odds_data_package: dict, math_model_results: dict) -> dict:
        print(f"🤖 [ChatGPT] 正在執行最終決策 (結合數學+市場+異常檢測) ({settings.MODEL_GPT})...")
        client = self._get_client(settings.OPENAI_API_KEY)
        
        # 使用您指定的 Prompt，並插入首發陣容
        prompt_content = f"""
        你是世界級的足球量化分析師與風險控管專家。請根據以下數據進行決策：
        
        【1. 數學模型 (歷史數據驅動)】
        - 泊松/Dixon-Coles/Elo: {json.dumps(math_model_results, ensure_ascii=False)}
        
        【2. 市場面 (Grok 即時情報)】
        {json.dumps(odds_data_package, ensure_ascii=False)}

        【3. 首發陣容 (JSON 數據)】
        {json.dumps(match_context.get('lineup', {}), ensure_ascii=False)}
              
        【4. 異常檢測指令 (Sanity Check) - 非常重要！】
        - 請計算「市場賠率隱含勝率」(1/Odds)。
        - **對比**: 將「數學模型勝率」與「市場隱含勝率」進行對比。
        - **警告**: 如果兩者差距超過 10% (例如模型說 60%，市場賠率 5.0 暗示 20%)，這通常代表數學模型使用的歷史數據已過時（如未考慮核心球員受傷）。
        - **決策邏輯**: 
            - 如果 Grok 情報顯示該隊有重大傷停或狀態極差，而數學模型卻看好該隊 -> **請判定為「模型失真」，建議 [No Bet] 或反向下注**。
            - 在 Grok 情報也支持該隊被低估時，視為 Value Bet。
        
        請輸出 JSON 格式:
        {{
            "recommendation": {{
                "market": "1x2 / Asian Handicap x.x / Over/Under x.x / No Bet",
                "selection": "Home / Away / Over / Under / None",
                "model_probability": 0.xx,
                "implied_probability": 0.xx, 
                "reasoning": "解釋為何推薦或為何放棄 (提及模型與市場的差異)..."
            }}
        }}
        """

        result = self._call_model(client, settings.MODEL_GPT, "Output JSON only.", prompt_content, json_mode=True)
        
        try:
            if result:
                json_match = re.search(r"\{.*\}", result, re.DOTALL)
                if json_match: return json.loads(json_match.group(0))
                return json.loads(result)
            else:
                return {"recommendation": {"market": "Error", "reasoning": "Empty Response"}}
        except:
            return {"recommendation": {"market": "Error", "reasoning": "JSON Parse Error"}}

llm = LLMOrchestrator()


