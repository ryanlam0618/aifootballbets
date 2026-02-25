import json
import re
from openai import OpenAI
from config import settings
from src.networking_llm import NetworkedLLM

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
            
            # 自動降級機制
            if json_mode and ("response_format" in error_str or "500" in error_str or "400" in error_str):
                print(f"🔄 嘗試移除 JSON 強制模式並重試...")
                try:
                    if "response_format" in kwargs: del kwargs["response_format"]
                    response = client.chat.completions.create(**kwargs)
                    if hasattr(response, 'choices'): return response.choices[0].message.content
                except Exception as e2:
                    print(f"❌ 重試依然失敗: {e2}")
            return None

    def fetch_data_helper(self, query: str):
        client = self._get_client(settings.GEMINI_API_KEY)
        return self._call_model(client, settings.MODEL_GEMINI, "You are a data assistant.", query) or "Data Error"

    def _format_lineup_data(self, lineup_data: dict) -> str:
        """格式化陣容數據為可讀文本"""
        if not lineup_data:
            return "無陣容數據"
        
        lines = []
        
        # 主隊
        home_team = lineup_data.get('home_team', 'Home')
        home_formation = lineup_data.get('home_formation', 'Unknown')
        lines.append(f"【{home_team}】 陣型: {home_formation}")
        
        # 首發
        home_starters = lineup_data.get('home_starters', [])
        if home_starters:
            starters_names = [f"{p.get('name', '')} ({p.get('position', '')})" for p in home_starters[:11]]
            lines.append(f"  首發: {', '.join(starters_names)}")
        
        # 後備
        home_subs = lineup_data.get('home_substitutes', [])
        if home_subs:
            subs_names = [f"{p.get('name', '')} ({p.get('position', '')})" for p in home_subs]
            lines.append(f"  後備: {', '.join(subs_names)}")
        
        # 傷停
        home_missing = lineup_data.get('home_missing_players', [])
        if home_missing:
            missing_names = [f"{p.get('name', '')} ({p.get('position', '')}): {p.get('description', 'N/A')}" for p in home_missing]
            lines.append(f"  傷停: {', '.join(missing_names)}")
        
        lines.append("")
        
        # 客隊
        away_team = lineup_data.get('away_team', 'Away')
        away_formation = lineup_data.get('away_formation', 'Unknown')
        lines.append(f"【{away_team}】 陣型: {away_formation}")
        
        # 首發
        away_starters = lineup_data.get('away_starters', [])
        if away_starters:
            starters_names = [f"{p.get('name', '')} ({p.get('position', '')})" for p in away_starters[:11]]
            lines.append(f"  首發: {', '.join(starters_names)}")
        
        # 後備
        away_subs = lineup_data.get('away_substitutes', [])
        if away_subs:
            subs_names = [f"{p.get('name', '')} ({p.get('position', '')})" for p in away_subs]
            lines.append(f"  後備: {', '.join(subs_names)}")
        
        # 傷停
        away_missing = lineup_data.get('away_missing_players', [])
        if away_missing:
            missing_names = [f"{p.get('name', '')} ({p.get('position', '')}): {p.get('description', 'N/A')}" for p in away_missing]
            lines.append(f"  傷停: {', '.join(missing_names)}")
        
        return "\n".join(lines)

    def _format_injury_data(self, injury_data: dict) -> str:
        """格式化傷停數據"""
        if not injury_data:
            return "無傷停數據"
        
        lines = []
        
        home = injury_data.get('home', {})
        away = injury_data.get('away', {})
        
        home_injuries = home.get('injuries', [])
        away_injuries = away.get('injuries', [])
        
        if home_injuries:
            lines.append(f"主隊傷停 ({len(home_injuries)}人):")
            for inj in home_injuries:
                name = inj.get('name', 'Unknown')
                pos = inj.get('position', '')
                desc = inj.get('description', 'N/A')
                lines.append(f"  - {name} ({pos}): {desc}")
        else:
            lines.append("主隊: 無傷停")
        
        if away_injuries:
            lines.append(f"客隊傷停 ({len(away_injuries)}人):")
            for inj in away_injuries:
                name = inj.get('name', 'Unknown')
                pos = inj.get('position', '')
                desc = inj.get('description', 'N/A')
                lines.append(f"  - {name} ({pos}): {desc}")
        else:
            lines.append("客隊: 無傷停")
        
        return "\n".join(lines)

    def _format_math_results(self, math_results: dict) -> str:
        """格式化數學模型結果"""
        if not math_results:
            return "無數學模型數據"
        
        lines = []
        
        # 各模型概率
        if 'negative_binomial' in math_results:
            nb = math_results['negative_binomial']
            lines.append(f"負二項分布: 主 {nb.get('home_win', 0):.1%} | 和 {nb.get('draw', 0):.1%} | 客 {nb.get('away_win', 0):.1%}")
        
        if 'monte_carlo' in math_results:
            mc = math_results['monte_carlo']
            lines.append(f"蒙地卡羅: 主 {mc.get('mc_home_win', 0):.1%} | 和 {mc.get('mc_draw', 0):.1%} | 客 {mc.get('mc_away_win', 0):.1%}")
        
        if 'dixon_coles' in math_results:
            dc = math_results['dixon_coles']
            lines.append(f"Dixon-Coles: 主 {dc.get('home_win', 0):.1%} | 和 {dc.get('draw', 0):.1%} | 客 {dc.get('away_win', 0):.1%}")
        
        if 'elo' in math_results:
            elo = math_results['elo']
            lines.append(f"Elo評分: 主 {elo.get('home_rating', 1500):.0f} | 客 {elo.get('away_rating', 1500):.0f}")
        
        if 'xg' in math_results:
            xg = math_results['xg']
            lines.append(f"xG數據: 主 {xg.get('home_xg', 0):.2f} | 客 {xg.get('away_xg', 0):.2f}")
        
        # 綜合
        if 'ensemble' in math_results:
            ens = math_results['ensemble']
            lines.append(f"綜合模型: 主 {ens.get('home_probability', 0):.1%} | 和 {ens.get('draw_probability', 0):.1%} | 客 {ens.get('away_probability', 0):.1%}")
        
        return "\n".join(lines)

    def _format_odds_data(self, odds_package: dict) -> str:
        """格式化市場賠率數據"""
        if not odds_package:
            return "無市場數據"
        
        lines = []
        
        # 處理結構化赔率數據 (新格式)
        if '1x2_home' in odds_package and '1x2_draw' in odds_package and '1x2_away' in odds_package:
            home_odds = odds_package.get('1x2_home', 0)
            draw_odds = odds_package.get('1x2_draw', 0)
            away_odds = odds_package.get('1x2_away', 0)
            lines.append(f"1x2 市場: 主 {home_odds} | 和 {draw_odds} | 客 {away_odds}")
            try:
                if home_odds > 0:
                    lines.append(f"隱含概率: 主 {1/home_odds:.1%} | 和 {1/draw_odds:.1%} | 客 {1/away_odds:.1%}")
            except:
                pass
        
        # 舊格式兼容：1x2 赔率
        elif '1x2' in odds_package:
            odds = odds_package['1x2']
            lines.append(f"1x2 市場: 主 {odds.get('home', 'N/A')} | 和 {odds.get('draw', 'N/A')} | 客 {odds_package.get('away', 'N/A')}")
            
            # 計算隱含概率
            try:
                home_odds = float(odds.get('home', 0))
                draw_odds = float(odds.get('draw', 0))
                away_odds = float(odds_package.get('away', 0))
                
                if home_odds > 0:
                    home_impl = 1 / home_odds
                    lines.append(f"隱含概率: 主 {home_impl:.1%} | 和 {1/draw_odds:.1%} | 客 {1/away_odds:.1%}")
            except:
                pass
        
        # 市場資金流向
        if 'movement' in odds_package:
            mov = odds_package['movement']
            lines.append(f"資金流向: 主 {mov.get('home', 'N/A')} | 和 {mov.get('draw', 'N/A')} | 客 {mov.get('away', 'N/A')}")
        
        # 處理 Over/Under 市場
        ou_markets = [k for k in odds_package.keys() if k.startswith('Over_Under')]
        if ou_markets:
            lines.append("\n--- 大小球市場 ---")
            for market in sorted(ou_markets):
                data = odds_package[market]
                if isinstance(data, dict):
                    over_odds = data.get('Over', data.get('over', 'N/A'))
                    under_odds = data.get('Under', data.get('under', 'N/A'))
                    lines.append(f"{market}: 大 {over_odds} | 小 {under_odds}")
        
        # 處理 Asian Handicap 市場
        ah_markets = [k for k in odds_package.keys() if k.startswith('Asian_Handicap')]
        if ah_markets:
            lines.append("\n--- 讓分盤市場 ---")
            for market in sorted(ah_markets):
                data = odds_package[market]
                if isinstance(data, dict):
                    home_odds = data.get('Home', data.get('home', 'N/A'))
                    away_odds = data.get('Away', data.get('away', 'N/A'))
                    lines.append(f"{market}: 主 {home_odds} | 客 {away_odds}")
        
        return "\n".join(lines)

    def search_and_analyze_market_reaction(self, match_info: str, odds_data_input: any, lineup_data: dict = None, injury_data: dict = None):
        """
        Grok 聯網分析：使用 xAI 的 web_search 工具
        
        新增參數：
        - lineup_data: 陣容數據
        - injury_data: 傷停數據
        """
        print(f"🤖 [Grok] 正在啟動即時分析：掃描 X 與新聞 ({settings.MODEL_GROK})...")
        net_client = NetworkedLLM(settings.GROK_API_KEY, settings.API_BASE_URL)
        
        # 格式化數據
        odds_text = ""
        if isinstance(odds_data_input, list):
            if odds_data_input and isinstance(odds_data_input[0], dict) and isinstance(odds_data_input[0].get('decimal_odds'), str):
                odds_text = odds_data_input[0]['decimal_odds']
            else:
                odds_text = "\n".join([f"- {p.time_offset}: {p.decimal_odds} ({p.bookmaker})" for p in odds_data_input])
        else:
            odds_text = str(odds_data_input)
        
        lineup_text = self._format_lineup_data(lineup_data) if lineup_data else "無陣容數據"
        injury_text = self._format_injury_data(injury_data) if injury_data else "無傷停數據"
        
        # 增強版 Prompt - 充分利用數據
        system_prompt = """You are an expert sports betting analyst with access to real-time search tools (web_search) in "X" and web.
You have deep knowledge of:
- Football tactics and formations (4-3-3, 4-2-3-1, 3-5-2, etc.)
- Player analysis and impact assessment
- Team news, injuries, suspensions
- Market movements and bookmaker behavior
- Value betting identification"""
        
        user_content = f"""
# 比賽信息
{match_info}

# 已有數據 - 陣容
{lineup_text}

# 已有數據 - 傷停
{injury_text}

# 即時市場賠率
{odds_text}

## 你的任務

1. **首發陣容分析**：
   - 檢查已有陣容數據，識別關鍵球員
   - 評估陣型是否對陣容有利
   - 注意後備深度（哪些位置缺乏替補）

2. **傷停影響評估**：
   - 已有傷停數據中，哪些球員是主力/核心球員？
   - 評估傷停對球隊戰力的實際影響（不是人數，而是質量）
   - 判斷是否有人員缺口無法彌補

3. **市場合理性檢驗**：
   - 結合陣容和傷停信息，判斷市場賠率是否合理
   - 如果市場過度高估/低估某隊，解釋原因

4. **價值機會識別**：
   - 市場是否忽視了傷停影響？
   - 陣容實力 vs 市場定價 是否存在落差？

請利用搜尋工具查找最新信息，然後提供你的分析。
"""

        # 第一次嘗試：使用 web_search
        print("🔍 [1/2] 嘗試聯網搜尋模式...")
        result = net_client.chat_with_search(
            model=settings.MODEL_GROK,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
            search_enabled=True 
        )
        
        # 檢查是否需要備用
        if result and ("Connection Failed" in result or "API Error" in result or "Error:" in result):
            print(f"⚠️ 聯網模式失敗，嘗試備用模式...")
            
            # 第二次嘗試：不使用 web_search，但仍然使用陣容數據
            print("🔍 [2/2] 嘗試本地分析模式 (無網路搜尋)...")
            simple_prompt = f"""
            作為足球分析師，分析以下比賽：
            
            【陣容數據】
            {lineup_text}
            
            【傷停數據】
            {injury_text}
            
            【市場數據】
            {odds_text[:500]}
            
            請提供簡短分析：
            1. 陣容點評（關鍵球員、陣型優劣）
            2. 傷停影響評估
            3. 可能的投注方向
            """
            result = net_client.chat_with_search(
                model=settings.MODEL_GROK,
                messages=[{"role": "system", "content": "You are a helpful sports betting analyst."}, 
                         {"role": "user", "content": simple_prompt}],
                search_enabled=False
            )
            
            if result and "Error:" not in result:
                print("✅ 備用模式成功")
                return f"[本地分析模式]\n{result}"
            else:
                return f"[⚠️ 網路不穩，無法獲取即時情報]\n基於現有數據分析：\n{lineup_text}\n{injury_text}"
        
        return result if result else "Grok 分析失敗。"

    def analyze_with_super_prompt(self, match_context: dict, odds_data_package: dict, math_model_results: dict) -> dict:
        """
        超級分析：結合數學模型、市場數據、陣容數據、傷停數據
        
        新增利用：
        - 完整陣容數據（首發+後備+陣型）
        - 傷停數據
        - 各模型詳細結果
        """
        print(f"🤖 [ChatGPT] 正在執行最終決策 (結合數學+市場+陣容+傷停) ({settings.MODEL_GPT})...")
        client = self._get_client(settings.OPENAI_API_KEY)
        
        # 提取和格式化各種數據
        lineup_data = match_context.get('lineup', {})
        injury_data = match_context.get('injury_impact', {})
        
        lineup_text = self._format_lineup_data(lineup_data)
        injury_text = self._format_injury_data(injury_data)
        math_text = self._format_math_results(math_model_results)
        odds_text = self._format_odds_data(odds_data_package)
        
        # 提取關鍵數值
        home_team = match_context.get('home_team', 'Home')
        away_team = match_context.get('away_team', 'Away')
        
        # 獲取 xG
        xg_data = match_context.get('expected_goals', {})
        home_xg = xg_data.get('home', 0)
        away_xg = xg_data.get('away', 0)
        
        # 獲取傷停影響
        home_impact = injury_data.get('home', {}).get('total_impact', 0)
        away_impact = injury_data.get('away', {}).get('total_impact', 0)
        
        prompt_content = f"""
# 你是世界級的足球量化分析師與風險控管專家

## 比賽
主隊: {home_team}
客隊: {away_team}

## 【1. 數學模型預測】(基於歷史數據)
{math_text}

預期進球: 主隊 {home_xg:.2f} | 客隊 {away_xg:.2f}

## 【2. 市場面數據】
{odds_text}

## 【3. 陣容數據】(首發、後備、陣型)
{lineup_text}

## 【4. 傷停數據】(已確認缺陣球員)
{injury_text}
主隊傷停人數: {home_impact} | 客隊傷停人數: {away_impact}

---

## 【關鍵分析任務】

### A. 異常檢測 (Sanity Check) - 最重要！
1. 計算「市場隱含勝率」(1/Decimal Odds)
2. 對比「數學模型勝率」與「市場隱含勝率」
3. **警告**: 如果差距 > 20%，代表有重大變化

### B. 陣容影響評估
1. 識別雙方的關鍵球員（核心球員通常是：主力射手、組織核心、主力門將）
2. 評估傷停是否影響核心戰力
3. 後備深度如何？替補能否填補缺口？

### C. 綜合決策邏輯
- 如果傷停導致核心球員缺陣 + 數學模型仍看好該隊 → **模型失真，應降低權重**
- 如果陣容數據顯示實力差距 + 市場未反映 → **潛在價值**
- 如果後備深度不足 + 進入下半場 → **體能劣勢**

### D. 投注決策
請根據以上分析，輸出以下格式的 JSON：
```json
{{
    "recommendation": {{
        "market": "1x2 / Asian Handicap x.x / Over/Under x.x / No Bet",
        "selection": "Home / Away / Over / Under / None",
        "model_probability": 0.xx,
        "implied_probability": 0.xx,
        "edge": 0.xx,
        "confidence": "High / Medium / Low",
        "reasoning": "詳細解釋（必須包含：陣容影響、傷停影響、市場對比）..."
    }},
    "analysis": {{
        "key_players_missing": ["球員A", "球員B"],
        "lineup_advantage": "主隊/客隊/相等",
        "injury_impact": "主隊/客隊/相等",
        "model_market_discrepancy": "差距百分比"
    }}
}}
```
```json
{{
    "recommendation": {{
        "market": "1x2 / Asian Handicap x.x / Over/Under x.x / No Bet",
        "selection": "Home / Away / Over / Under / None",
        "model_probability": 0.xx,
        "implied_probability": 0.xx,
        "edge": 0.xx,
        "confidence": "High / Medium / Low",
        "reasoning": "詳細解釋（必須包含：陣容影響、傷停影響、市場對比）..."
    }},
    "analysis": {{
        "key_players_missing": ["球員A", "球員B"],
        "lineup_advantage": "主隊/客隊/相等",
        "injury_impact": "主隊/客隊/相等",
        "model_market_discrepancy": "差距百分比"
    }}
}}
```

注意：
- reasoning 必須具體說明你如何考量陣容和傷停因素
- 如果模型看好但有核心球員傷停，請降低 confidence 等級
- "edge" 計算方式: (model_probability - implied_probability)
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
