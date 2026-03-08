import sys
import os
import json
import re
import difflib
import pandas as pd
import numpy as np

# 強制設定輸出編碼
sys.stdout.reconfigure(encoding='utf-8')

try:
    from config import settings
    # 匯入 LEAGUE_OPTIONS
    from src.data_modules import HistoryRepo, RealOddsFetcher, OddsHarvesterFetcher, OddsPoint, LEAGUE_OPTIONS
    from src.llm_clients import llm
    from src.finance import calculate_kelly_stake, ExcelLogger
    from src.league_parameter_estimator import fit_league_parameters, get_league_parameters  # 新增：聯賽參數估計器
    
    # 整合後的數學模型 (v7.0) - 包含原 v2, v3 功能
    from src.math_models import (
        PoissonModel,                    # 基礎 Poisson 模型
        NegativeBinomialModel,           # 負二項分布進球模型
        DixonColesModel,                # Dixon-Coles 模型
        OptimizedDixonColes,            # 優化版 Dixon-Coles
        MonteCarloSimulator,            # 蒙地卡羅 (基礎版)
        MonteCarloSimulatorV3,          # 蒙地卡羅 V3
        Glicko2System,                  # Glicko-2 評分系統
        DynamicKEloSystem,              # 動態K因子 Elo
        LineupModel,                    # 陣容模型
        ConfidenceKelly,                # 信心度 Kelly
        calculate_kelly_stake,          # Kelly 計算工具
    )
    
    # 導入高級模型
    from src.advanced_models import (
        ExponentialDecayXGForecaster,   # 指數衰減 xG
        BayesianGoalModel,              # 貝葉斯進球模型
        TeamFormLSTM,                  # LSTM 時序模型
        BettingRLAgent,                # RL 投注策略
        XGOTEfficiencyModel,           # xGOT 效率模型
        DefensiveQualityModel,         # 防守質量模型
        ShotPositionModel              # 射門位置模型
    )
    
    # 導入數學模型 V3 (ML 集成)
    from src.math_models_v3 import (
        StackingEnsemble,              # Stacking 集成
        DutchingCalculator,            # Dutching 投注計算器
        PortfolioKelly,                # 組合 Kelly 管理
        XGBoostModel,                 # XGBoost 模型
        RandomForestModel,            # 隨機森林模型
        GradientBoostingModel,         # 梯度提升模型
        LogisticRegressionModel        # 邏輯回歸模型
    )
    
    # 導入模型評估模組
    from src.model_evaluation import (
        CrossValidator,                # 交叉驗證
        Backtester,                   # 回測系統
        ModelMonitor,                 # 模型監控
        DataValidator                 # 數據驗證
    )
    
    # 導入 Sofascore 數據載入器
    try:
        from src.sofascore_loader import SofascoreDataLoader, get_sofascore_loader
        HAS_SOFASCORE = True
    except ImportError:
        HAS_SOFASCORE = False
        print("[WARN] Sofascore loader not available")
    
    # 導入特徵工程模組
    from src.feature_engineering import (
        FeatureEngineer,              # 特徵工程
        TimeSeriesFeatureGenerator    # 時間序列特徵
    )
    
    # 導入角球模型
    from src.corner_models import (
        CornerPredictionModel,        # 角球預測
        CornerValueBetModel           # 角球價值投注
    )
    
    from src.injury_api import InjuryDataAggregator, get_injury_report
    from src.lineup_api import LineupAggregator, get_lineup
    from src.cli_helpers import parse_match_input, choose_league
except ImportError as e:
    print(f"模組載入失敗: {e}", flush=True)
    sys.exit(1)


# ============================================
# Load Historical Team Names from CSV
# ============================================
HISTORICAL_TEAMS = {}
# [v7.1] 數據驗證器
data_validator = DataValidator()

try:
    # 從 CSV 加載歷史數據的球隊名稱
    df_hist = pd.read_csv(settings.HISTORY_CSV_PATH)
    
    # [v7.1] 驗證數據質量
    validation_result = data_validator.validate_match_data(df_hist)
    if not validation_result['is_valid']:
        print(f"[WARN] 數據質量問題: {validation_result['issues']}")
        print(f"       質量分數: {validation_result['quality_score']}/100")
    
    # [v7.1] 清洗異常數據
    df_hist_clean = data_validator.clean_data(df_hist, strategy='clip')
    print(f"[INFO] 數據驗證通過，質量分數: {validation_result['quality_score']}/100")
    
    all_teams_hist = set(df_hist_clean['home_team'].unique()) | set(df_hist_clean['away_team'].unique())
    HISTORICAL_TEAMS['csv_names'] = sorted(list(all_teams_hist))
    print(f"[INFO] 已載入 {len(HISTORICAL_TEAMS['csv_names'])} 個歷史球隊名稱")
except Exception as e:
    print(f"[WARN] 無法載入歷史球隊名稱: {e}")
    HISTORICAL_TEAMS['csv_names'] = []


# ============================================
# Load The Odds API Team Names
# ============================================
ODDS_API_TEAMS = {}
ODDS_API_TEAMS_LIST = {}  # 簡化的球隊名稱列表
try:
    odds_teams_file = 'data/top5_leagues_teams.json'
    if os.path.exists(odds_teams_file):
        with open(odds_teams_file, 'r', encoding='utf-8') as f:
            ODDS_API_TEAMS = json.load(f)
        
        # 提取簡化的球隊名稱列表（按聯賽分組）
        for league_key, league_data in ODDS_API_TEAMS.items():
            teams_dict = league_data.get('teams', {})
            team_names = list(teams_dict.keys())
            ODDS_API_TEAMS_LIST[league_key] = team_names
        
        print(f"[INFO] 已載入 The Odds API 球隊數據")
    else:
        # 如果沒有本地檔案，創建空結構
        ODDS_API_TEAMS = {
            'soccer_epl': {'league_name': 'Premier League', 'teams': {}},
            'soccer_spain_la_liga': {'league_name': 'La Liga', 'teams': {}},
            'soccer_germany_bundesliga': {'league_name': 'Bundesliga', 'teams': {}},
            'soccer_italy_serie_a': {'league_name': 'Serie A', 'teams': {}},
            'soccer_france_ligue_one': {'league_name': 'Ligue 1', 'teams': {}}
        }
        ODDS_API_TEAMS_LIST = {k: [] for k in ODDS_API_TEAMS.keys()}
except Exception as e:
    print(f"[WARN] 無法載入 The Odds API 球隊數據: {e}")
    ODDS_API_TEAMS = {}
    ODDS_API_TEAMS_LIST = {}


# ============================================
# Gemini API Team Matching Functions
# ============================================
def match_with_gemini(home_input, away_input, historical_names, league_context=""):
    """
    使用 Gemini API 智能匹配球隊名稱到歷史數據庫
    返回: {'home': matched_name, 'away': matched_name, 'confidence': 'high/medium/low'}
    """
    if not historical_names:
        return {'home': home_input, 'away': away_input, 'confidence': 'low'}
    
    # 精簡歷史名稱列表 (避免超過 token limit)
    key_leagues = ['Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1']
    filtered_names = [n for n in historical_names if any(lg.lower() in n.lower() or n.lower() in lg.lower() for lg in key_leagues)]
    if len(filtered_names) > 50:
        filtered_names = filtered_names[:50]
    elif len(filtered_names) < 10:
        filtered_names = historical_names[:50]
    
    prompt = f"""Match these 2 football teams to the historical database.

Match: {home_input} vs {away_input}
League Context: {league_context}

Historical Database Names:
{', '.join(filtered_names)}

IMPORTANT RULES:
- "Villarreal" -> Villarreal (Spain, NOT English)
- "Espanyol" -> Espanol (Spain)
- "AC Milan" -> AC Milan (Italy)
- "Inter Milan" -> Inter Milan (Italy)
- "Bayern Munich" -> Bayern Munich (Germany)
- "PSG" -> Paris SG (France)
- "Man Utd" -> Manchester United (England)
- "Man City" -> Manchester City (England)
- "Tottenham" -> Tottenham Hotspur (England)
- "Napoli" -> SSC Napoli (Italy)
- "Atletico" -> Ath Madrid (Spain)

Respond in this exact format (JSON):
{{"home": "exact name from database", "away": "exact name from database", "confidence": "high/medium/low"}}"""

    try:
        response = llm.fetch_data_helper(prompt)
        
        # 檢查回應是否有效
        if not response or response == "Data Error" or len(response.strip()) == 0:
            raise ValueError("Empty or error response from LLM")
        
        # 清理回應 - 移除 markdown code blocks
        response = response.strip()
        if response.startswith("```"):
            # 移除 ```json 和 ``` 等 code block 標記
            lines = response.split('\n')
            cleaned_lines = []
            for line in lines:
                if line.strip().startswith("```"):  # 跳過 ```json 或 ```
                    continue
                cleaned_lines.append(line)
            response = '\n'.join(cleaned_lines).strip()
        
        # 嘗試解析 JSON
        import json as json_mod
        result = json_mod.loads(response)
        
        print(f"   [GEMINI] API 返回結果: {result}")
        
        # 驗證結果是否在數據庫中
        home_matched = result.get('home', home_input)
        away_matched = result.get('away', away_input)
        
        # 標準化比對
        home_lower = home_matched.lower().strip()
        away_lower = away_matched.lower().strip()
        
        for hist_name in historical_names:
            if home_lower == hist_name.lower():
                home_matched = hist_name
                break
            if hist_name.lower() in home_lower or home_lower in hist_name.lower():
                home_matched = hist_name
                break
        
        for hist_name in historical_names:
            if away_lower == hist_name.lower():
                away_matched = hist_name
                break
            if away_lower in hist_name.lower() or hist_name.lower() in away_lower:
                away_matched = hist_name
                break
        
        return {
            'home': home_matched,
            'away': away_matched,
            'confidence': result.get('confidence', 'medium')
        }
    except json.JSONDecodeError as e:
        print(f"[WARN] Gemini 返回無效 JSON: {e}")
        print(f"       原始回應: {response[:200] if response else 'None'}...")
    except Exception as e:
        print(f"[WARN] Gemini matching failed: {e}")
    
    # 最後 fallback: 返回原始輸入
    return {'home': home_input, 'away': away_input, 'confidence': 'low'}


def match_to_odds_api(home_input, away_input, league_key):
    """
    使用 Gemini API 匹配球隊名稱到 The Odds API
    返回: {'home': odds_name, 'away': odds_name}
    """
    if not ODDS_API_TEAMS.get(league_key):
        return {'home': home_input, 'away': away_input}
    
    odds_teams = ODDS_API_TEAMS[league_key]
    if not odds_teams:
        return {'home': home_input, 'away': away_input}
    
    # 先取得 teams 字典
    teams_dict = odds_teams.get('teams', {})
    
    # 提取球隊名稱列表
    team_names = list(teams_dict.keys())[:50]
    
    prompt = f"""Match these football teams to The Odds API names.

Input: {home_input} vs {away_input}

Available Odds API Teams:
{', '.join(team_names[:50])}

IMPORTANT:
- Use exact names from the list above
- "Manchester United" -> exact name from list
- "Barcelona" -> exact name from list

Respond in JSON format:
{{"home": "exact name from list", "away": "exact name from list"}}"""

    try:
        response = llm.fetch_data_helper(prompt)
        if response:
            import json as json_mod
            # 移除 markdown code blocks (```json ... ```)
            response_clean = response.strip()
            if response_clean.startswith('```'):
                response_clean = response_clean.split('```')[1]
                # 移除語言標籤（如 "json"）
                response_clean = response_clean.strip()
                if response_clean.startswith('json'):
                    response_clean = response_clean[4:].strip()
            result = json_mod.loads(response_clean)
            return {
                'home': result.get('home', home_input),
                'away': result.get('away', away_input)
            }
    except Exception as e:
        print(f"[WARN] Odds API matching failed: {e}")
    
    return {'home': home_input, 'away': away_input}


def match_to_json_teams(home_input, away_input, league_key):
    """
    使用 Gemini API 智能匹配球隊名稱到 data/top5_leagues_teams.json
    返回: {'home': matched_name, 'away': matched_name, 'confidence': 'high/medium/low'}
    """
    # 獲取當前聯賽的球隊名稱列表
    teams_list = ODDS_API_TEAMS_LIST.get(league_key, [])
    
    # 如果沒有特定聯賽的球隊，嘗試所有聯賽
    if not teams_list:
        for key, teams in ODDS_API_TEAMS_LIST.items():
            teams_list.extend(teams)
    
    if not teams_list:
        return {'home': home_input, 'away': away_input, 'confidence': 'low'}
    
    # 獲取聯賽名稱
    league_info = ODDS_API_TEAMS.get(league_key, {})
    league_name = league_info.get('league_name', '')
    
    # 精簡球隊名稱列表 (避免超過 token limit)
    if len(teams_list) > 50:
        teams_list = teams_list[:50]
    
    prompt = f"""Match these 2 football teams to the JSON database (top5_leagues_teams.json).

Input: {home_input} vs {away_input}
League: {league_name}

Available Teams in JSON:
{', '.join(teams_list)}

IMPORTANT RULES:
- Use EXACT names from the list above
- "Manchester United" -> "Manchester United" (not "Man Utd")
- "Tottenham" -> "Tottenham Hotspur"
- "AC Milan" -> "AC Milan"
- "Inter Milan" -> "Inter Milan"
- "Bayern Munich" -> "Bayern Munich"
- "PSG" -> "Paris Saint Germain"
- "Napoli" -> "Napoli"
- "Atletico Madrid" -> "Atlético Madrid"

Respond in this exact JSON format:
{{"home": "exact name from list", "away": "exact name from list", "confidence": "high/medium/low"}}"""

    try:
        response = llm.fetch_data_helper(prompt)
        
        # 檢查回應是否有效
        if not response or response == "Data Error" or len(response.strip()) == 0:
            raise ValueError("Empty or error response from LLM")
        
        # 清理回應 - 移除 markdown code blocks
        response = response.strip()
        if response.startswith("```"):
            lines = response.split('\n')
            cleaned_lines = []
            for line in lines:
                if line.strip().startswith("```"):
                    continue
                cleaned_lines.append(line)
            response = '\n'.join(cleaned_lines).strip()
        
        # 嘗試解析 JSON
        import json as json_mod
        result = json_mod.loads(response)
        
        print(f"   [GEMINI JSON] API 返回結果: {result}")
        
        # 驗證結果是否在數據庫中
        home_matched = result.get('home', home_input)
        away_matched = result.get('away', away_input)
        
        # 標準化比對
        home_lower = home_matched.lower().strip()
        away_lower = away_matched.lower().strip()

        
        # 檢查主隊是否在列表中
        for team_name in teams_list:
            if home_lower == team_name.lower():
                home_matched = team_name
                break
            if team_name.lower() in home_lower or home_lower in team_name.lower():
                home_matched = team_name
                break
        
        # 檢查客隊是否在列表中
        for team_name in teams_list:
            if away_lower == team_name.lower():
                away_matched = team_name
                break
            if team_name.lower() in away_lower or away_lower in team_name.lower():
                away_matched = team_name
                break
        
        return {
            'home': home_matched,
            'away': away_matched,
            'confidence': result.get('confidence', 'medium')
        }
        
    except json.JSONDecodeError as e:
        print(f"[WARN] Gemini JSON matching returned invalid JSON: {e}")
        print(f"       原始回應: {response[:200] if response else 'None'}...")
    except Exception as e:
        print(f"[WARN] Gemini JSON matching failed: {e}")
    
    # 最後 fallback: 返回原始輸入
    return {'home': home_input, 'away': away_input, 'confidence': 'low'}


def find_best_sofa_match(home_input, away_input, league_name, sofa_matches):
    """
    使用 Gemini API 從 SofaScore 比賽列表中找到最匹配的比賽

    Args:
        home_input: 主隊名稱
        away_input: 客隊名稱
        league_name: 聯賽名稱
        sofa_matches: SofaScore 比賽列表

    Returns:
        匹配的比賽信息 (dict) 或 None
    """
    if not sofa_matches:
        return None

    # 構建可用的比賽列表字符串
    match_list_str = []
    for i, m in enumerate(sofa_matches[:20]):  # 最多 20 場
        match_list_str.append(f"{i+1}. {m.get('home_team', '')} vs {m.get('away_team', '')} (ID: {m.get('event_id', '')})")

    prompt = f"""Match these input teams to the available SofaScore matches.

Input: {home_input} vs {away_input}
League: {league_name}

Available matches today:
{chr(10).join(match_list_str)}

Return ONLY the match number (1, 2, 3, etc.) that best matches the input.
If no good match, return "NONE"."""

    try:
        from src.llm_clients import llm
        response = llm.fetch_data_helper(prompt)
        response = response.strip()

        if response.isdigit():
            idx = int(response) - 1
            if 0 <= idx < len(sofa_matches):
                return sofa_matches[idx]
    except Exception as e:
        print(f"      [WARN] Gemini matching failed: {e}")

    # Fallback: 簡單字符串匹配
    for m in sofa_matches:
        home_team = m.get('home_team', '').lower()
        away_team = m.get('away_team', '').lower()
        if home_input.lower() in home_team or home_team in home_input.lower():
            if away_input.lower() in away_team or away_team in away_input.lower():
                return m

    return None


def find_lineup_file(home_team, away_team, data_folder="data"):
    """
    查找陣容 JSON 檔案
    """
    import glob

    def clean_team_name(name):
        import unicodedata
        # re 已在模組頂部導入，這裡直接使用
        name = unicodedata.normalize('NFKD', name)
        name = re.sub(r'[^a-zA-Z0-9\s]', '', name)
        return name.strip().replace(" ", "_")

    home_clean = clean_team_name(home_team)
    away_clean = clean_team_name(away_team)

    # 優先嘗試精確匹配（無日期）
    exact_pattern = f"{data_folder}/lineup/lineup_{home_clean}_vs_{away_clean}.json"
    exact_matches = glob.glob(exact_pattern)
    if exact_matches:
        with open(exact_matches[0], 'r', encoding='utf-8') as f:
            return json.load(f)

    # 反向匹配（無日期）
    reverse_pattern = f"{data_folder}/lineup/lineup_{away_clean}_vs_{home_clean}.json"
    reverse_matches = glob.glob(reverse_pattern)
    if reverse_matches:
        with open(reverse_matches[0], 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # 嘗試帶日期的匹配
    date_pattern = f"{data_folder}/lineup/lineup_{home_clean}_vs_{away_clean}_*.json"
    date_matches = glob.glob(date_pattern)
    if date_matches:
        with open(date_matches[0], 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # 反向帶日期
    reverse_date_pattern = f"{data_folder}/lineup/lineup_{away_clean}_vs_{home_clean}_*.json"
    reverse_date_matches = glob.glob(reverse_date_pattern)
    if reverse_date_matches:
        with open(reverse_date_matches[0], 'r', encoding='utf-8') as f:
            return json.load(f)

    return None


def run_test_mode(auto_mode=False):
    """
    測試模式：使用模擬數據測試資金管理功能
    """
    sys.stdout.reconfigure(encoding='utf-8')
    print("\n" + "=" * 50, flush=True)
    print("🧪 測試模式：信心度 Kelly、RL 策略與 Excel 記錄", flush=True)
    print("=" * 50, flush=True)
    
    # 模擬數據
    league_name = "意甲"
    odds_home = "Sassuolo"
    odds_away = "Hellas Verona"
    target_odds = 1.9
    rec_market = "Asian Handicap +0.25"
    rec_selection = "Home"
    
    # 模擬概率 (模型預測 55% 勝率)
    model_p = 0.55
    implied_p = 1 / target_odds  # ~52.6%
    avg_v3_prob = model_p  # 測試用
    
    # 模擬動態信心度
    dynamic_confidence = 0.8
    model_std = 0.05
    
    print(f"\n📊 模擬數據:")
    print(f"   比賽: {odds_home} vs {odds_away}")
    print(f"   市場: {rec_market} - {rec_selection}")
    print(f"   賠率: {target_odds}")
    print(f"   模型概率: {model_p:.1%}")
    print(f"   市場隱含: {implied_p:.1%}")
    print(f"   信心度: {dynamic_confidence:.1%}")
    
    # ====== 信心度 Kelly 測試 ======
    print(f"\n   💰 [v3] 信心度 Kelly 資金管理:")
    try:
        kelly_v3 = ConfidenceKelly(
            base_fraction=0.75,
            min_edge=0.05,  # 調降至 2% 門檻，符合一般投注優勢標準
            initial_bankroll=settings.INITIAL_BANKROLL
        )
        
        market_prob = 1 / target_odds
        v3_prob = avg_v3_prob  # 使用模擬的 v3 概率
        
        kelly_result = kelly_v3.calculate(
            prob=v3_prob,
            odds=target_odds,
            confidence=dynamic_confidence,
            model_uncertainty=model_std,
            market_prob=market_prob
        )
        
        print(f"      [信心度 Kelly]")
        print(f"         Kelly%: {kelly_result.kelly_pct:.2%}")
        print(f"         期望值: {kelly_result.ev:.3f}")
        print(f"         優勢: {kelly_result.edge:.3f}")
        print(f"         建議投注: ${kelly_result.stake:.2f}")
        
        kelly_v3_result = kelly_result.to_dict()
        print(f"      ✅ to_dict() 返回: {kelly_v3_result}")
        
    except Exception as e:
        kelly_v3_result = {"stake": 0, "pct": 0, "ev": 0}
        print(f"      ❌ 信心度 Kelly 計算失敗: {e}")
    
    # ====== RL 策略測試 ======
    print(f"\n   🤖 [Adv] RL 投注策略:")
    try:
        model_prob = v3_prob
        implied_prob = 1 / target_odds
        edge = model_prob - implied_prob
        
        home_form_score = 0.6
        away_form_score = 0.4
        
        rl_agent = BettingRLAgent(
            bankroll=settings.INITIAL_BANKROLL,
            learning_rate=0.1,
            discount_factor=0.95,
            exploration_rate=0.1
        )
        
        rl_decision = rl_agent.place_bet(
            edge=edge,
            confidence=dynamic_confidence,
            odds=target_odds,
            home_form=home_form_score,
            away_form=away_form_score,
            predicted_prob=model_prob
        )
        
        print(f"      [RL 策略]")
        print(f"         邊緣 (Edge): {edge:.3f}")
        print(f"         投注金額: ${rl_decision.get('bet_amount', 0):.2f}")
        print(f"      ✅ RL 策略正常運作")
        
    except Exception as e:
        print(f"      ❌ RL 策略計算失敗: {e}")
    
    # ====== Excel 記錄測試 ======
    print(f"\n   📝 Excel 記錄測試:")
    
    # 驗證 kelly_v3_result 結構
    if 'pct' in kelly_v3_result and 'ev' in kelly_v3_result and 'stake' in kelly_v3_result:
        print(f"      ✅ stake_info 結構正確")
        print(f"         pct: {kelly_v3_result['pct']}")
        print(f"         ev: {kelly_v3_result['ev']}")
        print(f"         stake: {kelly_v3_result['stake']}")
    else:
        print(f"      ❌ stake_info 結構錯誤: {kelly_v3_result}")
        kelly_v3_result = {"stake": 10, "pct": 0.01, "ev": 0.05}  # 測試用備份
    
    # 測試記錄功能
    try:
        logger = ExcelLogger()
        
        match_info = {
            "league": league_name,
            "home": odds_home,
            "away": odds_away
        }
        bet_info = {
            "market": rec_market,
            "selection": rec_selection,
            "odds": target_odds,
            "model_probability": v3_prob
        }
        
        # 模擬用戶輸入 'y'
        print(f"\n[?] 記錄注單到 Excel? (y/n): y")
        
        # 測試記錄
        logger.log_bet(match_info, bet_info, kelly_v3_result)
        print(f"      ✅ Excel 記錄成功")
        
        # 顯示統計
        logger.show_stats()
        
    except Exception as e:
        print(f"      ❌ Excel 記錄失敗: {e}")
        import traceback
        traceback.print_exc()
    
    # ====== 最終結果 ======
    print(f"\n   [{rec_market} - {rec_selection}] 賠率 {target_odds}:")
    final_stake = kelly_v3_result.get('stake', 0)
    final_ev = kelly_v3_result.get('ev', 0)
    
    if final_stake > 0:
        print(f"      >>> 建議下注: ${final_stake:.2f} (EV: {final_ev:.3f})")
    else:
        print(f"      >>> 不建議下注 (EV < 0 或 min_edge 不足)")
    
    print("\n" + "=" * 50)
    print("🧪 測試模式完成！")
    print("=" * 50)

    if not auto_mode:
        input("\n執行完畢，請按 Enter 離開...")


def main(auto_mode=False):
    print("========================================", flush=True)
    print("⚽ AI Football Analysis System v6.6 (Gemini API Matching)", flush=True)
    print("========================================", flush=True)

    # 檢查是否為測試模式
    test_mode = False
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == '--test' or arg == 'test':
            test_mode = True
            print("\n🧪 測試模式：使用模擬數據")
    
    if test_mode:
        run_test_mode(auto_mode=auto_mode)
        return

    # 1. 選擇聯賽
    print("\n📋 請選擇聯賽 (輸入數字):")
    sorted_keys = sorted(LEAGUE_OPTIONS.keys(), key=lambda x: int(x))
    for key in sorted_keys:
        print(f"   [{key}] {LEAGUE_OPTIONS[key]['name']}")
    
    league_idx = input("👉 選擇: ").strip()
    league_idx, selected_league = choose_league(league_idx, LEAGUE_OPTIONS)

    league_name = selected_league['name']
    league_key = selected_league['key']
    
    print(f"✅ 已選擇: {league_name} ({league_key})")

    # 2. 輸入比賽
    match_input = input("\n👉 請輸入比賽對戰組合 (Enter 預設 Bournemouth vs Tottenham): ").strip()
    if not match_input: match_input = "Bournemouth vs Tottenham"

    try:
        home, away = parse_match_input(match_input)
    except ValueError:
        print("⚠️ 格式錯誤")
        return

    # ============================================
    # 使用 Gemini API 進行球隊名稱匹配
    # ============================================
    print(f"\n🔗 [1.1/4] 使用 Gemini API 匹配球隊名稱...", flush=True)
    print(f"   原始輸入: {home} vs {away}")
    print(f"   聯賽上下文: {league_name}")

    # Step 1: 匹配到歷史數據庫 (CSV)
    print(f"\n   [1/4] 匹配到歷史數據庫...")
    hist_match = match_with_gemini(home, away, HISTORICAL_TEAMS.get('csv_names', []), league_name)
    db_home = hist_match['home']
    db_away = hist_match['away']
    print(f"      [HIST] {home} -> {db_home} (confidence: {hist_match['confidence']})")
    print(f"      [HIST] {away} -> {db_away} (confidence: {hist_match['confidence']})")

    # Step 2: 匹配到 The Odds API
    print(f"\n   [2/4] 匹配到 The Odds API...")
    odds_match = match_to_odds_api(home, away, league_key)
    odds_home = odds_match['home']
    odds_away = odds_match['away']
    print(f"      [ODDS] {home} -> {odds_home}")
    print(f"      [ODDS] {away} -> {odds_away}")

    # Step 3: 匹配到 JSON 檔案 (top5_leagues_teams.json)
    print(f"\n   [3/4] 匹配到 JSON 檔案 (top5_leagues_teams.json)...")
    json_match = match_to_json_teams(home, away, league_key)
    json_home = json_match['home']
    json_away = json_match['away']
    print(f"      [JSON] {home} -> {json_home} (confidence: {json_match['confidence']})")
    print(f"      [JSON] {away} -> {json_away} (confidence: {json_match['confidence']})")
    '''
    #test code
    db_home = home
    db_away = away
    odds_home = home
    odds_away = away
    json_home = home
    json_away = away'''
    
    # 初始化
    repo = HistoryRepo(settings.HISTORY_CSV_PATH)
    
    # 優先使用 The Odds API，失敗時自動使用 OddsPortal
    print("✅ 初始化 The Odds API...")
    odds_fetcher = RealOddsFetcher()
    logger = ExcelLogger()

    # ============================================
    # 初始化聯賽參數（動態校準）
    # ============================================
    print(f"\n⚙️ [0/4] 初始化聯賽參數...")
    league_params = {}
    try:
        if hasattr(repo, 'df') and not repo.df.empty:
            # 從歷史數據擬合參數
            valid_df = repo.df.dropna(subset=['home_goals', 'away_goals', 'league'])
            if len(valid_df) >= 30:
                league_params = fit_league_parameters(valid_df, min_matches=30)
                print(f"   ✅ 已從 {len(valid_df)} 場比賽擬合聯賽參數")
                # 顯示當前聯賽的參數
                current_params = get_league_parameters(league_name)
                print(f"   📊 {league_name} 參數:")
                print(f"      α (離散): {current_params['alpha']:.3f}")
                print(f"      ρ (DC): {current_params['rho']:.3f}")
                print(f"      衰減率: {current_params['decay_rate']:.3f}")
                print(f"      τ (Glicko-2): {current_params['tau']:.3f}")
            else:
                league_params = {}
                print(f"   ⚠️ 數據不足 ({len(valid_df)} 場)，使用默認參數")
        else:
            print(f"   ⚠️ 無法載入歷史數據，使用默認參數")
    except Exception as e:
        print(f"   ⚠️ 參數擬合失敗: {str(e)[:50]}，使用默認參數")
        league_params = {}

    # 獲取當前聯賽的參數
    current_league_params = get_league_parameters(league_name)

    # 3. 讀取/獲取陣容數據
    print(f"\n👕 [1.2/4] 正在獲取陣容數據...", flush=True)

    lineup_data = find_lineup_file(db_home, db_away)
    if not lineup_data:
        lineup_data = find_lineup_file(odds_home, odds_away)
    if not lineup_data:
        lineup_data = find_lineup_file(home, away)

    if lineup_data:
        print(f"   [本地] 找到陣容檔案")
    else:
        print(f"   [INFO] 未找到本地陣容檔案，使用 SofaScore API 獲取...")

        # 使用 SofaScore API 獲取陣容
        try:
            from TakeData.sofa_lineup_scraper import SofaScoreLineupHarvester
            import datetime

            # 獲取當天比賽列表
            today = datetime.datetime.now().strftime('%Y-%m-%d')
            sofa_harvester = SofaScoreLineupHarvester()

            print(f"   [SOFA] 正在獲取 {today} {league_name} 比賽列表...")

            # 初始化瀏覽器並獲取比賽列表
            from DrissionPage import ChromiumPage, ChromiumOptions
            co = ChromiumOptions().headless()
            co.set_browser_path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
            page = ChromiumPage(co)

            # 獲取當天比賽列表
            sofa_matches = sofa_harvester.get_match_list_by_date(page, today)
            page.quit()

            if not sofa_matches:
                print(f"   [SOFA] 當天沒有找到任何比賽")
            else:
                print(f"   [SOFA] 找到 {len(sofa_matches)} 場比賽")

                # 篩選當前聯賽（支援部分匹配）
                league_matches = [m for m in sofa_matches if league_name.lower() in m.get('tournament_name', '').lower() or m.get('tournament_name', '').lower() in league_name.lower()]
                print(f"   [SOFA] {league_name} 有 {len(league_matches)} 場比賽")

                # 使用 Gemini 匹配正確的比賽
                best_match = find_best_sofa_match(odds_home, odds_away, league_name, league_matches)

                if best_match:
                    event_id = best_match.get('event_id')
                    print(f"   [SOFA] 匹配成功: {best_match.get('home_team')} vs {best_match.get('away_team')}")
                    print(f"   [SOFA] 使用 event_id: {event_id}")
                    lineup_data = SofaScoreLineupHarvester.get_lineup_by_event_id(event_id)

                    if lineup_data:
                        print(f"   [SOFA] 成功獲取陣容: {lineup_data['home_team']} vs {lineup_data['away_team']}")
                else:
                    # 嘗試手動輸入 event_id（自動模式下跳過）
                    if not auto_mode:
                        event_id = input("   👉 請輸入 SofaScore event_id (或按 Enter 跳過): ").strip()
                        if event_id:
                            lineup_data = SofaScoreLineupHarvester.get_lineup_by_event_id(event_id)
                            if lineup_data:
                                print(f"   [SOFA] 成功獲取陣容: {lineup_data['home_team']} vs {lineup_data['away_team']}")

        except Exception as e:
            print(f"   [SOFA] 獲取失敗: {e}")

    # 4. 傷停數據 (從陣容數據中獲取)
    print(f"\n[1.3/4] 正在獲取傷停數據...", flush=True)

    # 從陣容數據中提取傷停球員
    if lineup_data:
        home_missing = lineup_data.get('home_missing_players', [])
        away_missing = lineup_data.get('away_missing_players', [])

        injury_report = {
            'home': {'injuries': home_missing, 'total_impact': len(home_missing)},
            'away': {'injuries': away_missing, 'total_impact': len(away_missing)}
        }

        # 顯示傷停信息
        if home_missing:
            print(f"   [傷停] {lineup_data.get('home_team', 'Home')}:")
            for p in home_missing:
                print(f"      - {p.get('name', '')} ({p.get('position', '')}): {p.get('description', '')}")
        else:
            print(f"   [傷停] {lineup_data.get('home_team', 'Home')}: 無傷停")

        if away_missing:
            print(f"   [傷停] {lineup_data.get('away_team', 'Away')}:")
            for p in away_missing:
                print(f"      - {p.get('name', '')} ({p.get('position', '')}): {p.get('description', '')}")
        else:
            print(f"   [傷停] {lineup_data.get('away_team', 'Away')}: 無傷停")
    else:
        injury_report = {
            'home': {'injuries': [], 'total_impact': 0},
            'away': {'injuries': [], 'total_impact': 0}
        }

    home_injury = injury_report['home']
    away_injury = injury_report['away']

    # 5. 獲取歷史數據
    print(f"\n🔍 [1/4] 執行 Glicko-2 回測與機器學習預測...", flush=True)
    match_context = repo.get_match_context(db_home, db_away, league_name)
    stats = match_context.get("stats", {})
    
    # 陣容分析
    print(f"👕 [1.5/4] 分析首發名單評分...", flush=True)
    lineup_prob = repo.get_lineup_prediction(db_home, db_away)
    if lineup_prob:
        print(f"   [基於首發球員評分的主勝率: {lineup_prob:.1%}")

    # 數學運算
    h_exp = stats.get("home_weighted_xg", 1.2)
    a_exp = stats.get("away_weighted_xg", 1.0)
    h_exp_adj = max(0.5, min(3.5, h_exp))
    a_exp_adj = max(0.5, min(3.5, a_exp))

    print(f"\n   [INFO] 使用 Gemini 匹配後的 xG")
    print(f"      {odds_home} {h_exp_adj:.2f} - {a_exp_adj:.2f} {odds_away}")

    dc_model = DixonColesModel(h_exp_adj, a_exp_adj)
    dc_probs = dc_model.calculate_probabilities()

    # 使用整合版蒙地卡羅 (基礎版)
    mc_sim = MonteCarloSimulator(h_exp_adj, a_exp_adj)
    mc_probs = mc_sim.run_simulation()

    # ========== [v3] 負二項分布 ==========
    print(f"\n   🎯 [v3] 負二項分布模型:")
    alpha = current_league_params.get('alpha', 1.5)  # 動態離散參數
    nb_model = NegativeBinomialModel(h_exp_adj, a_exp_adj, dispersion=alpha)
    nb_probs = nb_model.calculate_probabilities()
    print(f"      主勝: {nb_probs['home_win']:.1%} | 和局: {nb_probs['draw']:.1%} | 客勝: {nb_probs['away_win']:.1%}")

    # ========== [v3] 動態K Elo ==========
    print(f"\n   📈 [v3] 動態K Elo 評分:")
    # Elo K 值保持固定（需要更複雜的優化才能動態調整）
    dynamic_elo = DynamicKEloSystem(base_k=20)
    try:
        valid_df = repo.df.dropna(subset=['home_goals', 'away_goals', 'home_team', 'away_team'])
        for _, row in valid_df.tail(100).iterrows():
            try:
                dynamic_elo.update_ratings(
                    row['home_team'], row['away_team'],
                    int(row['home_goals']), int(row['away_goals'])
                )
            except: continue
    except: pass
    
    elo_home = dynamic_elo.get_rating(db_home)
    elo_away = dynamic_elo.get_rating(db_away)
    elo_win_prob = dynamic_elo.expected_win_prob(db_home, db_away)
    print(f"      {odds_home} 評分: {elo_home:.0f} | {odds_away} 評分: {elo_away:.0f}")
    print(f"      Elo 勝率預測: {elo_win_prob:.1%}")

    # ========== [v3] 蒙地卡羅模擬 ==========
    print(f"\n   🎲 [v3] 蒙地卡羅模擬 (10,000次):")
    mc_v3 = MonteCarloSimulatorV3(h_exp_adj, a_exp_adj, iterations=10000, use_nbinom=True, dispersion=alpha)
    mc_v3_probs = mc_v3.run_simulation()
    print(f"      主勝: {mc_v3_probs['mc_home_win']:.1%} | 和局: {mc_v3_probs['mc_draw']:.1%} | 客勝: {mc_v3_probs['mc_away_win']:.1%}")

    # ========== [Advanced] 指數衰減 xG ==========
    print(f"\n   📈 [Adv] 指數衰減 xG 預測:")
    
    xg_forecast_home, xg_forecast_away = h_exp_adj, a_exp_adj
    home_xg_adv = {'xg': h_exp_adj, 'n_games': 0}
    away_xg_adv = {'xg': a_exp_adj, 'n_games': 0}
    
    try:
        decay_rate = current_league_params.get('decay_rate', 0.1)  # 動態衰減率
        xg_forecaster = ExponentialDecayXGForecaster(decay_rate=decay_rate, recency_weight=1.5, min_games=2)
        
        # Fallback: 使用實際進球的預測器
        xg_forecaster_goals = ExponentialDecayXGForecaster(decay_rate=decay_rate, recency_weight=1.5, min_games=2)
        
        print(f"      [GEMINI] 使用 Gemini 匹配的歷史名稱: {db_home}, {db_away}")
        
        if hasattr(repo, 'df') and not repo.df.empty:
            valid_df = repo.df.dropna(subset=['home_team', 'away_team'])
            
            # 使用 xG 數據
            valid_df_xg = valid_df.copy()
            if 'xg' in valid_df_xg.columns:
                valid_df_xg = valid_df_xg[valid_df_xg['xg'].notna()]
            
            # 使用實際進球的數據（全部）
            valid_df_goals = valid_df.dropna(subset=['home_goals', 'away_goals'])
            
            print(f"      [DEBUG] 載入 {len(valid_df)} 場有效比賽")
            print(f"      [DEBUG] 有 xG 數據: {len(valid_df_xg)} 場, 有進球數據: {len(valid_df_goals)} 場")
            
            home_xg_col = 'xg'
            away_xg_col = 'xga'
            
            if home_xg_col and away_xg_col:
                match_count = 0
                
                # 加載目標球隊的歷史數據（不限於最近1000場）
                # 確保降級球隊也有數據
                target_teams = [db_home, db_away]
                
                # 從 xG 數據加載
                for team in target_teams:
                    team_home = valid_df_xg[valid_df_xg['home_team'] == team]
                    team_away = valid_df_xg[valid_df_xg['away_team'] == team]
                    
                    for _, row in team_home.iterrows():
                        try:
                            home_xg_val = float(row.get(home_xg_col, 1.5))
                            away_xg_val = float(row.get(away_xg_col, 1.0))
                            
                            if pd.isna(home_xg_val) or home_xg_val <= 0:
                                home_xg_val = float(row['home_goals']) if pd.notna(row.get('home_goals')) else 1.5
                            if pd.isna(away_xg_val) or away_xg_val <= 0:
                                away_xg_val = float(row['away_goals']) if pd.notna(row.get('away_goals')) else 1.0
                            
                            xg_forecaster.add_match(row['home_team'], home_xg_val, True, row['date'])
                            xg_forecaster.add_match(row['away_team'], away_xg_val, False, row['date'])
                            match_count += 1
                        except: continue
                    
                    for _, row in team_away.iterrows():
                        try:
                            home_xg_val = float(row.get(home_xg_col, 1.5))
                            away_xg_val = float(row.get(away_xg_col, 1.0))
                            
                            if pd.isna(home_xg_val) or home_xg_val <= 0:
                                home_xg_val = float(row['home_goals']) if pd.notna(row.get('home_goals')) else 1.5
                            if pd.isna(away_xg_val) or away_xg_val <= 0:
                                away_xg_val = float(row['away_goals']) if pd.notna(row.get('away_goals')) else 1.0
                            
                            xg_forecaster.add_match(row['home_team'], home_xg_val, True, row['date'])
                            xg_forecaster.add_match(row['away_team'], away_xg_val, False, row['date'])
                            match_count += 1
                        except: continue
                
                # 也從進球數據加載（確保 fallback 有數據）
                for team in target_teams:
                    team_home = valid_df_goals[valid_df_goals['home_team'] == team]
                    team_away = valid_df_goals[valid_df_goals['away_team'] == team]
                    
                    for _, row in team_home.iterrows():
                        try:
                            home_goals = float(row['home_goals']) if pd.notna(row.get('home_goals')) else 1.5
                            away_goals = float(row['away_goals']) if pd.notna(row.get('away_goals')) else 1.0
                            xg_forecaster_goals.add_match(row['home_team'], home_goals, True, row['date'])
                            xg_forecaster_goals.add_match(row['away_team'], away_goals, False, row['date'])
                        except: continue
                    
                    for _, row in team_away.iterrows():
                        try:
                            home_goals = float(row['home_goals']) if pd.notna(row.get('home_goals')) else 1.5
                            away_goals = float(row['away_goals']) if pd.notna(row.get('away_goals')) else 1.0
                            xg_forecaster_goals.add_match(row['home_team'], home_goals, True, row['date'])
                            xg_forecaster_goals.add_match(row['away_team'], away_goals, False, row['date'])
                        except: continue
                
                print(f"      [DEBUG] 已載入 {match_count} 場 xG 數據")
        
        import datetime
        ref_date = datetime.datetime.now()
        
        home_result = xg_forecaster.get_team_xg(db_home, ref_date, True)
        away_result = xg_forecaster.get_team_xg(db_away, ref_date, False)
        
        # Fallback: 如果 xG 模型沒有數據，使用實際進球模型
        if home_result.get('xg') is None or home_result.get('n_games', 0) == 0:
            home_result_goals = xg_forecaster_goals.get_team_xg(db_home, ref_date, True)
            if home_result_goals.get('xg') is not None:
                home_result = home_result_goals
                print(f"      [DEBUG] {db_home} 使用實際進球數據 (n={home_result.get('n_games', 0)})")
        
        if away_result.get('xg') is None or away_result.get('n_games', 0) == 0:
            away_result_goals = xg_forecaster_goals.get_team_xg(db_away, ref_date, False)
            if away_result_goals.get('xg') is not None:
                away_result = away_result_goals
                print(f"      [DEBUG] {db_away} 使用實際進球數據 (n={away_result.get('n_games', 0)})")
        
        if isinstance(home_result, dict) and home_result.get('xg') is not None:
            xg_forecast_home = float(home_result['xg'])
            home_xg_adv = home_result
        if isinstance(away_result, dict) and away_result.get('xg') is not None:
            xg_forecast_away = float(away_result['xg'])
            away_xg_adv = away_result
        
        print(f"      {odds_home} 預測 xG: {xg_forecast_home:.2f} (n={home_xg_adv.get('n_games', 0)})")
        print(f"      {odds_away} 預測 xG: {xg_forecast_away:.2f} (n={away_xg_adv.get('n_games', 0)})")
    except Exception as e:
        print(f"      ⚠️ 指數衰減模型失敗: {str(e)[:80]}")

    # ========== [Advanced] 貝葉斯進球模型 ==========
    print(f"\n   🔮 [Adv] 貝葉斯進球模型:")
    
    bayes_pred = {
        'home_lambda': h_exp_adj,
        'away_lambda': a_exp_adj,
        'home_ci': (h_exp_adj * 0.5, h_exp_adj * 1.5),
        'away_ci': (a_exp_adj * 0.5, a_exp_adj * 1.5),
        'probabilities': {'home_win': nb_probs['home_win'], 'draw': nb_probs['draw'], 'away_win': nb_probs['away_win']},
        'uncertainty': {'average': 0.3}
    }
    print(f"      [DEBUG] Bayesian 初始 uncertainty: {bayes_pred['uncertainty']['average']}")
    
    try:
        bayes_model = BayesianGoalModel(confidence_level=0.95)
        if hasattr(repo, 'df') and not repo.df.empty:
            valid_df = repo.df.dropna(subset=['home_goals', 'away_goals'])
            if 'xg' in valid_df.columns:
                valid_df = valid_df[valid_df['xg'].notna()]
            
            print(f"      [DEBUG] Bayesian: 載入 {len(valid_df)} 場有效比賽")
            
            if len(valid_df) >= 5:
                recent_valid = valid_df.tail(200)
                obs_count = 0
                
                for _, row in recent_valid.iterrows():
                    try:
                        home_xg = float(row.get('xg', 1.5)) if pd.notna(row.get('xg')) else float(row['home_goals'])
                        bayes_model.add_observation(
                            int(row['home_goals']), int(row['away_goals']),
                            home_xg=home_xg, is_home=True
                        )
                        away_xg = float(row.get('xga', 1.0)) if pd.notna(row.get('xga')) else float(row['away_goals'])
                        bayes_model.add_observation(
                            int(row['away_goals']), int(row['home_goals']),
                            home_xg=away_xg, is_home=False
                        )
                        obs_count += 2
                    except: continue
                
                if obs_count > 0:
                    bayes_pred = bayes_model.predict()
                    print(f"      [DEBUG] Bayesian: 觀察數量={obs_count}")
                    print(f"      [DEBUG] Bayesian 預測後 uncertainty (before clamp): {bayes_pred.get('uncertainty', {}).get('average', 'N/A')}")
                    
                    uncertainty = bayes_pred.get('uncertainty', {})
                    for key in uncertainty:
                        uncertainty[key] = min(1.0, max(0.0, uncertainty.get(key, 0.3)))
                    print(f"      [DEBUG] Bayesian 預測後 uncertainty (after clamp): {uncertainty.get('average', 'N/A')}")
        
        print(f"      主場 λ: {bayes_pred['home_lambda']:.3f} [{bayes_pred['home_ci'][0]:.2f}-{bayes_pred['home_ci'][1]:.2f}]")
        print(f"      客場 λ: {bayes_pred['away_lambda']:.3f} [{bayes_pred['away_ci'][0]:.2f}-{bayes_pred['away_ci'][1]:.2f}]")
        print(f"      不確定性: {bayes_pred['uncertainty']['average']:.1%}")
    except Exception as e:
        print(f"      ⚠️ 貝葉斯模型失敗: {str(e)[:80]}")

    # ========== [Advanced] LSTM 狀態追蹤 ==========
    print(f"\n   📊 [Adv] LSTM 球隊狀態追蹤:")
    
    home_form = {'form_score': 0.5, 'trend': 'stable', 'confidence': 'low'}
    away_form = {'form_score': 0.5, 'trend': 'stable', 'confidence': 'low'}
    
    torch_available = False
    tf_available = False
    try:
        import torch
        torch_available = True
    except: pass
    try:
        import tensorflow as tf
        tf_available = True
    except: pass
    
    try:
        if torch_available or tf_available:
            lstm_model = TeamFormLSTM(sequence_length=10, use_attention=True, min_games=2)
            
            if hasattr(repo, 'df') and not repo.df.empty:
                valid_df = repo.df.dropna(subset=['home_team', 'away_team', 'home_goals', 'away_goals'])
                if 'xg' in valid_df.columns:
                    valid_df = valid_df[valid_df['xg'].notna()]
                
                result_col = 'ftr' if 'ftr' in valid_df.columns else 'result'
                xg_col = 'xg' if 'xg' in valid_df.columns else 'home_xg'
                away_xg_col = 'xga' if 'xga' in valid_df.columns else 'away_xg'
                
                print(f"      [DEBUG] LSTM: 載入 {len(valid_df)} 場有效比賽")
                
                recent_valid = valid_df.tail(300)
                match_count = 0
                
                for _, row in recent_valid.iterrows():
                    try:
                        result = str(row.get(result_col, 'D')).upper()
                        if result == 'W': home_result, away_result = 'W', 'L'
                        elif result == 'L': home_result, away_result = 'L', 'W'
                        else: home_result, away_result = 'D', 'D'
                        
                        home_xg_val = float(row.get(xg_col, 1.5))
                        away_xg_val = float(row.get(away_xg_col, 1.0))
                        
                        lstm_model.add_match(row['home_team'],
                            goals_scored=int(row['home_goals']),
                            goals_conceded=int(row['away_goals']),
                            xg=home_xg_val, possession=50, shots_on_target=3,
                            result=home_result, is_home=True)
                        lstm_model.add_match(row['away_team'],
                            goals_scored=int(row['away_goals']),
                            goals_conceded=int(row['home_goals']),
                            xg=away_xg_val, possession=50, shots_on_target=3,
                            result=away_result, is_home=False)
                        match_count += 1
                    except: continue
                
                print(f"      [DEBUG] LSTM: 已載入 {match_count} 場比賽數據")
                
                # 使用 Gemini 匹配的歷史名稱
                home_form = lstm_model.predict_team_form(db_home)
                away_form = lstm_model.predict_team_form(db_away)
        
        # Fallback: 使用基於統計的狀態
        if not tf_available or home_form.get('form_score', 0) == 0.5:
            if hasattr(repo, 'df') and not repo.df.empty:
                tmp = repo.df.copy()
                tmp["hl"] = tmp["home_team"].astype(str).str.lower().str.strip()
                tmp["al"] = tmp["away_team"].astype(str).str.lower().str.strip()
                
                db_home_l = db_home.lower().strip()
                db_away_l = db_away.lower().strip()
                
                home_games = tmp[(tmp["hl"] == db_home_l) | (tmp["al"] == db_home_l)].tail(10)
                away_games = tmp[(tmp["hl"] == db_away_l) | (tmp["al"] == db_away_l)].tail(10)
                
                def calc_simple_form(games, team_l):
                    if games.empty: return 0.5, 'stable'
                    points = 0
                    for _, row in games.iterrows():
                        if row['hl'] == team_l:
                            if row['home_goals'] > row['away_goals']: points += 3
                            elif row['home_goals'] == row['away_goals']: points += 1
                        else:
                            if row['away_goals'] > row['home_goals']: points += 3
                            elif row['away_goals'] == row['home_goals']: points += 1
                    avg_pts = points / max(len(games), 1)
                    form_score = min(1.0, avg_pts / 3.0)
                    
                    recent = games.tail(3)
                    older = games.head(len(games)-3) if len(games) > 3 else games.head(0)
                    r_pts = sum(3 if (row['home_goals'] > row['away_goals'] if row['hl'] == team_l else row['away_goals'] > row['home_goals']) else (1 if row['home_goals'] == row['away_goals'] else 0) for _, row in recent.iterrows())
                    o_pts = sum(3 if (row['home_goals'] > row['away_goals'] if row['hl'] == team_l else row['away_goals'] > row['home_goals']) else (1 if row['home_goals'] == row['away_goals'] else 0) for _, row in older.iterrows())
                    
                    r_avg = r_pts / max(len(recent), 1) if len(recent) > 0 else 1.5
                    o_avg = o_pts / max(len(older), 1) if len(older) > 0 else 1.5
                    
                    if r_avg > o_avg + 0.5: trend = 'improving'
                    elif r_avg < o_avg - 0.5: trend = 'declining'
                    else: trend = 'stable'
                    
                    return form_score, trend
                
                home_f, home_t = calc_simple_form(home_games, db_home_l)
                away_f, away_t = calc_simple_form(away_games, db_away_l)
                
                home_form = {'form_score': home_f, 'trend': home_t, 'confidence': 'medium'}
                away_form = {'form_score': away_f, 'trend': away_t, 'confidence': 'medium'}
        
        print(f"      {odds_home} 狀態: {home_form['form_score']:.2f} ({home_form['trend']})")
        print(f"      {odds_away} 狀態: {away_form['form_score']:.2f} ({away_form['trend']})")
    except Exception as e:
        print(f"      ⚠️ 狀態追蹤失敗: {str(e)[:80]}")

    # ============================================
    # [v7.1] xGOT 效率分析
    # ============================================
    print(f"\n   🎯 [v7.1] xGOT 效率分析:")
    try:
        # 首先嘗試使用 Sofascore 數據
        if HAS_SOFASCORE:
            try:
                sofa = get_sofascore_loader()
                # 獲取聯賽名稱映射
                league_name_map = {
                    'Premier League': 'Premier League',
                    'LaLiga': 'LaLiga',
                    'Bundesliga': 'Bundesliga',
                    'Serie A': 'Serie A',
                    'Ligue 1': 'Ligue 1'
                }
                sofa_league = league_name_map.get(league_name, None)
                
                # 計算 xG 統計
                home_xg_stats = sofa.calculate_team_xg_stats(db_home, is_home=True, league=sofa_league, recent_n=30)
                away_xg_stats = sofa.calculate_team_xg_stats(db_away, is_home=False, league=sofa_league, recent_n=30)
                
                print(f"      [Sofascore] {odds_home} xG: {home_xg_stats.get('xg_total', 0):.2f}, xGOT: {home_xg_stats.get('xgot_total', 0):.2f}, 進球: {home_xg_stats.get('goals', 0):.2f} (樣本: {home_xg_stats.get('n_samples', 0)})")
                print(f"      [Sofascore] {odds_away} xG: {away_xg_stats.get('xg_total', 0):.2f}, xGOT: {away_xg_stats.get('xgot_total', 0):.2f}, 進球: {away_xg_stats.get('goals', 0):.2f} (樣本: {away_xg_stats.get('n_samples', 0)})")
                
                # 計算效率分數
                home_eff_score = home_xg_stats.get('efficiency', 1.0) * 100
                away_eff_score = away_xg_stats.get('efficiency', 1.0) * 100
                
                print(f"      {odds_home} xGOT 效率: {home_eff_score/100:.2f} (樣本: {home_xg_stats.get('n_samples', 0)})")
                print(f"      {odds_away} xGOT 效率: {away_eff_score/100:.2f} (樣本: {away_xg_stats.get('n_samples', 0)})")
                
                xgot_analysis = {
                    'home_efficiency': home_eff_score / 100,
                    'away_efficiency': away_eff_score / 100,
                    'home_expected_goals': home_xg_stats.get('xg_total', h_exp_adj),
                    'away_expected_goals': away_xg_stats.get('xg_total', a_exp_adj)
                }
                
            except Exception as sofa_err:
                print(f"      [WARN] Sofascore 數據載入失敗: {str(sofa_err)[:30]}")
                raise
        else:
            # Fallback 到舊的 XGOTEfficiencyModel
            raise Exception("Sofascore not available")
            
    except Exception as e:
        # Fallback 到舊的模型
        try:
            xgot_model = XGOTEfficiencyModel(min_samples=3)
            
            if hasattr(repo, 'df') and not repo.df.empty:
                # 檢查是否有 xGOT 數據的欄位
                xgot_cols = ['home_xg_total', 'away_xg_total', 'home_xgot_total', 'away_xgot_total']
                has_xgot_data = all(col in repo.df.columns for col in xgot_cols)
                
                if has_xgot_data:
                    valid_df = repo.df.dropna(subset=['home_xg_total', 'away_xg_total', 'home_xgot_total', 'away_xgot_total'])
                else:
                    # 沒有 xGOT 数据，使用进球數據作為 fallback
                    valid_df = repo.df.dropna(subset=['home_goals', 'away_goals'])
                
                # 載入球隊數據
                for team in [db_home, db_away]:
                    team_data = valid_df[(valid_df['home_team'] == team) | (valid_df['away_team'] == team)].tail(30)
                    for _, row in team_data.iterrows():
                        try:
                            is_home = row['home_team'] == team
                            if has_xgot_data:
                                xg = float(row['home_xg_total'] if is_home else row['away_xg_total'])
                                xgot = float(row['home_xgot_total'] if is_home else row['away_xgot_total'])
                                goals = int(row['home_goals'] if is_home else row['away_goals'])
                                shots = int(row['home_shots_total'] if is_home else row['away_shots_total']) if 'home_shots_total' in row.index else 5
                            else:
                                # fallback 到預期進球
                                xg = float(row['home_goals'] if is_home else row['away_goals']) + 1.0
                                xgot = xg
                                goals = int(row['home_goals'] if is_home else row['away_goals'])
                                shots = 5
                            # 只添加有效的 xg > 0 數據
                            if xg > 0 and xgot > 0:
                                xgot_model.add_match_data(team, xg, xgot, goals, shots, is_home)
                        except: continue
                
                # 計算效率
                home_eff = xgot_model.calculate_efficiency(db_home, is_home=True)
                away_eff = xgot_model.calculate_efficiency(db_away, is_home=False)
                
                print(f"      {odds_home} xGOT 效率: {home_eff.get('efficiency_score', 50)/100:.2f} (樣本: {home_eff.get('sample_size', 0)})")
                print(f"      {odds_away} xGOT 效率: {away_eff.get('efficiency_score', 50)/100:.2f} (樣本: {away_eff.get('sample_size', 0)})")
                
                xgot_analysis = {
                    'home_efficiency': home_eff.get('efficiency_score', 50) / 100,
                    'away_efficiency': away_eff.get('efficiency_score', 50) / 100,
                    'home_expected_goals': home_eff.get('xg_total', h_exp_adj),
                    'away_expected_goals': away_eff.get('xg_total', a_exp_adj)
                }
            else:
                raise Exception("No repo data")
        except Exception as e:
            print(f"      ⚠️ xGOT 效率分析失敗: {str(e)[:50]}")
            xgot_analysis = {'home_efficiency': 1.0, 'away_efficiency': 1.0}

    # ============================================
    # [v7.1] 防守質量分析
    # ============================================
    print(f"\n   🛡️ [v7.1] 防守質量分析:")
    try:
        # 首先嘗試使用 Sofascore 數據
        if HAS_SOFASCORE:
            try:
                sofa = get_sofascore_loader()
                # 獲取聯賽名稱映射
                league_name_map = {
                    'Premier League': 'Premier League',
                    'LaLiga': 'LaLiga',
                    'Bundesliga': 'Bundesliga',
                    'Serie A': 'Serie A',
                    'Ligue 1': 'Ligue 1'
                }
                sofa_league = league_name_map.get(league_name, None)
                
                # 計算防守統計
                home_def_stats = sofa.calculate_defensive_stats(db_home, is_home=True, league=sofa_league, recent_n=30)
                away_def_stats = sofa.calculate_defensive_stats(db_away, is_home=False, league=sofa_league, recent_n=30)
                
                print(f"      [Sofascore] {odds_home} xGA: {home_def_stats.get('xga', 0):.2f}, 失球: {home_def_stats.get('goals_conceded', 0):.2f}, 撲救率: {home_def_stats.get('save_rate', 0):.2f} (樣本: {home_def_stats.get('n_samples', 0)})")
                print(f"      [Sofascore] {odds_away} xGA: {away_def_stats.get('xga', 0):.2f}, 失球: {away_def_stats.get('goals_conceded', 0):.2f}, 撲救率: {away_def_stats.get('save_rate', 0):.2f} (樣本: {away_def_stats.get('n_samples', 0)})")
                
                print(f"      {odds_home} 防守評分: {home_def_stats.get('quality_score', 0.5):.2f} (失球預期: {home_def_stats.get('xga', 1.2):.2f}, 樣本: {home_def_stats.get('n_samples', 0)})")
                print(f"      {odds_away} 防守評分: {away_def_stats.get('quality_score', 0.5):.2f} (失球預期: {away_def_stats.get('xga', 1.2):.2f}, 樣本: {away_def_stats.get('n_samples', 0)})")
                
                defense_analysis = {
                    'home_quality': home_def_stats.get('quality_score', 0.5),
                    'away_quality': away_def_stats.get('quality_score', 0.5),
                    'home_expected_conceded': home_def_stats.get('xga', 1.2),
                    'away_expected_conceded': away_def_stats.get('xga', 1.2)
                }
                
            except Exception as sofa_err:
                print(f"      [WARN] Sofascore 數據載入失敗: {str(sofa_err)[:30]}")
                raise
        else:
            raise Exception("Sofascore not available")
            
    except Exception as e:
        # Fallback 到舊的模型
        try:
            def_model = DefensiveQualityModel(min_samples=3)
            
            if hasattr(repo, 'df') and not repo.df.empty:
                # 檢查欄位名稱
                shot_col = 'home_shots_total' if 'home_shots_total' in repo.df.columns else 'home_shots'
                away_shot_col = 'away_shots_total' if 'away_shots_total' in repo.df.columns else 'away_shots'
                
                valid_df = repo.df.dropna(subset=['home_goals', 'away_goals'])
                
                for team in [db_home, db_away]:
                    team_data = valid_df[(valid_df['home_team'] == team) | (valid_df['away_team'] == team)].tail(30)
                    for _, row in team_data.iterrows():
                        try:
                            is_home = row['home_team'] == team
                            # 對手射門次數 = 主隊時用 away_shots_total，客隊時用 home_shots_total
                            xg_against = float(row['away_goals']) if is_home else float(row['home_goals'])
                            shots_against = int(row[away_shot_col]) if is_home else int(row[shot_col])
                            goals_against = int(row['away_goals']) if is_home else int(row['home_goals'])
                            def_model.add_match_data(team, xg_against, shots_against, goals_against, is_home)
                        except: continue
                
                home_def = def_model.calculate_defensive_quality(db_home, is_home=True)
                away_def = def_model.calculate_defensive_quality(db_away, is_home=False)
                
                print(f"      {odds_home} 防守評分: {home_def.get('defensive_score', 50)/100:.2f} (失球預期: {home_def.get('xga', 1.2):.2f}, 樣本: {home_def.get('sample_size', 0)})")
                print(f"      {odds_away} 防守評分: {away_def.get('defensive_score', 50)/100:.2f} (失球預期: {away_def.get('xga', 1.2):.2f}, 樣本: {away_def.get('sample_size', 0)})")
                
                defense_analysis = {
                    'home_quality': home_def.get('defensive_score', 50) / 100,
                    'away_quality': away_def.get('defensive_score', 50) / 100,
                    'home_expected_conceded': home_def.get('xga', 1.2),
                    'away_expected_conceded': away_def.get('xga', 1.2)
                }
            else:
                raise Exception("No repo data")
        except Exception as e:
            print(f"      ⚠️ 防守質量分析失敗: {str(e)[:50]}")
            defense_analysis = {'home_quality': 0.5, 'away_quality': 0.5}

    # ============================================
    # [v7.1] 角球預測
    # ============================================
    print(f"\n   📐 [v7.1] 角球預測:")
    try:
        # 首先嘗試使用 Sofascore 數據
        if HAS_SOFASCORE:
            try:
                sofa = get_sofascore_loader()
                league_name_map = {
                    'Premier League': 'Premier League',
                    'LaLiga': 'LaLiga',
                    'Bundesliga': 'Bundesliga',
                    'Serie A': 'Serie A',
                    'Ligue 1': 'Ligue 1'
                }
                sofa_league = league_name_map.get(league_name, None)
                
                # 計算角球統計
                home_corner_stats = sofa.calculate_corner_stats(db_home, is_home=True, league=sofa_league, recent_n=20)
                away_corner_stats = sofa.calculate_corner_stats(db_away, is_home=False, league=sofa_league, recent_n=20)
                
                home_corners = home_corner_stats.get('avg_corners', 5.5)
                away_corners = away_corner_stats.get('avg_corners', 4.5)
                
                print(f"      [Sofascore] {odds_home} 平均角球: {home_corners:.1f} (樣本: {home_corner_stats.get('n_samples', 0)})")
                print(f"      [Sofascore] {odds_away} 平均角球: {away_corners:.1f} (樣本: {away_corner_stats.get('n_samples', 0)})")
                
                corner_pred = {
                    'home_corners': home_corners,
                    'away_corners': away_corners,
                    'total_corners': home_corners + away_corners
                }
                
            except Exception as sofa_err:
                print(f"      [WARN] Sofascore 角球數據失敗: {str(sofa_err)[:30]}")
                raise
        else:
            raise Exception("Sofascore not available")
            
    except Exception as e:
        # Fallback 到舊的 CornerPredictionModel
        try:
            corner_model = CornerPredictionModel(decay_rate=0.15)
            
            if hasattr(repo, 'df') and not repo.df.empty:
                valid_df = repo.df.dropna(subset=['home_corners', 'away_corners'])
                
                # 遍歷球隊數據
                for team in [db_home, db_away]:
                    team_data = valid_df[(valid_df['home_team'] == team) | (valid_df['away_team'] == team)].tail(20)
                    for _, row in team_data.iterrows():
                        try:
                            is_home = row['home_team'] == team
                            corners = row['home_corners'] if is_home else row['away_corners']
                            if pd.notna(corners):
                                # 使用正確的方法 add_match_data
                                corner_model.add_match_data(
                                    league=league_name,
                                    home_team=db_home,
                                    away_team=db_away,
                                    home_corners=int(row['home_corners']) if is_home else 0,
                                    away_corners=int(row['away_corners']) if not is_home else 0
                                )
                        except Exception as e:
                            continue
            
            # 使用正確的方法 predict_corners
            corner_pred = corner_model.predict_corners(
                league=league_name,
                home_team=db_home,
                away_team=db_away
            )
        except Exception:
            corner_pred = {'home_corners': 5.5, 'away_corners': 4.5, 'total_corners': 10.0}
        
        print(f"      {odds_home} 預測角球: {corner_pred.get('home_corners', 5.5):.1f}")
        print(f"      {odds_away} 預測角球: {corner_pred.get('away_corners', 4.5):.1f}")
        print(f"      預測總角球: {corner_pred.get('total_corners', 10.0):.1f}")
        
        # 角球價值投注 (延遲到 all_markets 取得後)
        corner_value = None  # 先設為 None，稍後在有 all_markets 時再初始化
        
        corner_analysis = {
            'home_corners': corner_pred.get('home_corners', 5.5),
            'away_corners': corner_pred.get('away_corners', 4.5),
            'total_corners': corner_pred.get('total_corners', 10.0)
        }
    except Exception as e:
        print(f"      ⚠️ 角球預測失敗: {str(e)[:50]}")
        corner_analysis = {'home_corners': 5.5, 'away_corners': 4.5, 'total_corners': 10.0}

    # 計算綜合勝率
    avg_v3_prob = (nb_probs['home_win'] + mc_v3_probs['mc_home_win'] + elo_win_prob) / 3
    print(f"\n   📊 [v3] 綜合勝率: {avg_v3_prob:.1%}")


    # ============================================
    # 計算動態信心度（基於模型分歧）
    # ============================================
    # 收集各模型的主勝概率
    model_probs = [
        nb_probs['home_win'],
        mc_v3_probs['mc_home_win'],
        elo_win_prob,
        dc_probs.get('home_win', avg_v3_prob),
    ]
    # 計算模型分歧（標準差）
    model_std = np.std(model_probs) if len(model_probs) > 1 else 0
    # 信心度 = 1 - 分歧程度（標準差越大，信心越低）
    # 範圍：0.3 到 0.9
    dynamic_confidence = max(0.3, min(0.9, 1.0 - model_std * 2))
    print(f"   📈 動態信心度: {dynamic_confidence:.1%} (模型標準差: {model_std:.3f})")

    math_results = {
        "dixon_coles": dc_probs,
        "monte_carlo": mc_probs,
        "negative_binomial": {
            "home_win": nb_probs['home_win'],
            "draw": nb_probs['draw'],
            "away_win": nb_probs['away_win'],
            "dispersion": nb_probs.get('dispersion', 1.5)
        },
        "dynamic_elo": {
            "home_rating": elo_home,
            "away_rating": elo_away,
            "home_win_prob": elo_win_prob
        },
        "monte_carlo_v3": mc_v3_probs,
        "avg_v3_prob": avg_v3_prob,
        "exponential_xg": {
            "home": xg_forecast_home,
            "away": xg_forecast_away,
            "home_n": home_xg_adv.get('n_games', 0),
            "away_n": away_xg_adv.get('n_games', 0)
        },
        "bayesian": {
            "home_lambda": bayes_pred.get('home_lambda', h_exp_adj),
            "away_lambda": bayes_pred.get('away_lambda', a_exp_adj),
            "home_ci": bayes_pred.get('home_ci', (h_exp_adj*0.5, h_exp_adj*1.5)),
            "away_ci": bayes_pred.get('away_ci', (a_exp_adj*0.5, a_exp_adj*1.5)),
            "probabilities": bayes_pred.get('probabilities', nb_probs),
            "uncertainty": bayes_pred.get('uncertainty', {'average': 0.3})
        },
        "lstm_form": {
            "home": home_form,
            "away": away_form
        },
        "glicko": match_context.get("glicko", "No Data"),
        "lineup_prob": lineup_prob,
        "lineup": lineup_data,  # 新增：完整陣容數據
        "expected_goals": {"home": h_exp_adj, "away": a_exp_adj},
        "injury_impact": {
            "home": home_injury,
            "away": away_injury,
            "diff": home_injury.get('total_impact', 0) - away_injury.get('total_impact', 0),
            "disabled": False,
            "home_players": home_injury.get('injuries', []),
            "away_players": away_injury.get('injuries', [])
        }
    }

    glicko = match_context.get("glicko", {})
    print(f"   [INFO] 傷停調整: 主隊 {home_injury.get('total_impact', 0)} 人, 客隊 {away_injury.get('total_impact', 0)} 人")
    print(f"      {odds_home} {h_exp_adj:.2f} - {a_exp_adj:.2f} {odds_away}")
    print(f"   🏆 Glicko-2 勝率: {glicko.get('win_prob', 0):.1%}")

    # 6. 讀取即時賠率
    print(f"\n📈 [2/4] 連線 API 讀取即時賠率...", flush=True)
    all_markets = odds_fetcher.get_real_odds(league_key, odds_home, odds_away)
    
    # 如果 The Odds API 沒有數據，自動使用 OddsPortal
    if not all_markets:
        print("   ⚠️ The Odds API 無效數據，正在切換到 OddsPortal...")
        odds_fetcher = OddsHarvesterFetcher()
        all_markets = odds_fetcher.get_real_odds(league_key, odds_home, odds_away)
        if all_markets:
            print("   ✅ OddsPortal 數據獲取成功")
    
    odds_summary_text = ""
    if all_markets:
        print(f"   ✅ 成功解析 {len(all_markets)} 個投注市場")
        
        # 構建結構化赔率數據 (用於 ChatGPT)
        structured_odds = {}
        for market, selections in all_markets.items():
            market_key = market.replace(' ', '_').replace('/', '_')
            market_odds = {}
            for sel, stats in selections.items():
                if stats['avg']:
                    avg_o = stats['avg'][-1].decimal_odds
                    implied = (1 / avg_o) * 100
                    market_odds[sel.lower()] = avg_o
                    
                    # 1x2 市場特別處理
                    if market == '1x2':
                        if 'home' in sel.lower():
                            structured_odds['1x2_home'] = avg_o
                        elif 'draw' in sel.lower():
                            structured_odds['1x2_draw'] = avg_o
                        elif 'away' in sel.lower():
                            structured_odds['1x2_away'] = avg_o
            
            structured_odds[market_key] = market_odds
            
            # 打印終端輸出
            line_str = f"   🔹 {market}: "
            for sel, stats in selections.items():
                if stats['avg']:
                    avg_o = stats['avg'][-1].decimal_odds
                    implied = (1 / avg_o) * 100
                    line_str += f"{sel}[{avg_o}|{implied:.1f}%] "
                    odds_summary_text += f"{market} {sel} -> Odds:{avg_o} (Implied:{implied:.1f}%) | "
            print(line_str)
    else:
        print("⚠️ 無有效賠率數據")
        odds_summary_text = "No Odds Data Available"
        structured_odds = {}

    # ============================================
    # [v7.1] 角球價值投注 (延遲到取得 all_markets 後)
    # ============================================
    try:
        if corner_value is not None and all_markets:
            # 嘗試找到角球市場
            corner_odds_over = None
            corner_odds_under = None
            bookie_line = 10.5
            for market, selections in all_markets.items():
                if 'corner' in market.lower():
                    for sel, stats in selections.items():
                        if stats.get('avg'):
                            odds = stats['avg'][-1].decimal_odds
                            if 'over' in sel.lower():
                                corner_odds_over = odds
                            elif 'under' in sel.lower():
                                corner_odds_under = odds
                    # 嘗試從市場名稱解析盤口
                    match = re.search(r'(\d+\.?\d*)', market)
                    if match:
                        bookie_line = float(match.group(1))
            
            if corner_odds_over and corner_odds_under:
                value_bets = corner_value.find_value_bets(
                    league=league_name,
                    home_team=db_home,
                    away_team=db_away,
                    bookie_line=bookie_line,
                    bookie_odds_over=corner_odds_over,
                    bookie_odds_under=corner_odds_under
                )
                if value_bets and value_bets.get('has_value'):
                    print(f"   💡 角球價值投注: {value_bets.get('recommended', 'N/A')}")
    except Exception as e:
        print(f"   ⚠️ 角球價值投注失敗: {str(e)[:50]}")
    
    #input("test stop")
    # 7. Grok 搜尋 (傳入陣容和傷停數據)
    print(f"\n🤖 [3/4] 請求 Grok 聯網搜尋市場情報...", flush=True)
    grok_input = odds_summary_text[:1500]
    grok_reaction = llm.search_and_analyze_market_reaction(
        f"{odds_home} vs {odds_away}",
        grok_input,
        lineup_data=lineup_data,      # 傳入陣容數據
        injury_data=injury_report     # 傳入傷停數據
    )
    print("\n--------- 🤖 Grok 市場觀點 ---------", flush=True)
    print(grok_reaction[:200] + "..." if len(grok_reaction) > 200 else grok_reaction, flush=True)

    # 8. ChatGPT 決策
    print(f"\n🧠 [4/4] ChatGPT 綜合決策...", flush=True)
    
    # 添加 expected_goals 到 match_context (供 LLM 使用)
    match_context["expected_goals"] = {"home": h_exp_adj, "away": a_exp_adj}
    match_context["lineup"] = lineup_data  # 添加陣容數據到 match_context
    match_context["injury_impact"] = {
        "home": home_injury,
        "away": away_injury,
        "diff": home_injury.get('total_impact', 0) - away_injury.get('total_impact', 0),
        "disabled": False,
        "home_players": home_injury.get('injuries', []),
        "away_players": away_injury.get('injuries', [])
    }
    
    odds_data_package = {
        "full_market_odds": odds_summary_text,
        "market_reaction": grok_reaction,
        **structured_odds  # 展開結構化赔率數據 (包含 1x2 等)
    }
    
    rec = llm.analyze_with_super_prompt(match_context, odds_data_package, math_results, market_intelligence=grok_reaction).get("recommendation", {})

    print("\n--------- 💡 最終推薦結果 ---------", flush=True)
    rec_market = rec.get('market', 'N/A')
    rec_selection = rec.get('selection', 'N/A')
    model_p = rec.get('model_probability', 0)
    implied_p = rec.get('implied_probability', 0)
    
    print(f"下注項目: [{rec_market}] {rec_selection}", flush=True)
    if isinstance(model_p, (int, float)) and isinstance(implied_p, (int, float)):
        print(f"模型勝率: {model_p:.1%} vs 市場隱含: {implied_p:.1%}", flush=True)
    
    print(f"分析理由: {rec.get('reasoning')}", flush=True)

    # 9. 資金計算
    if "No Bet" in str(rec_market) or "Error" in str(rec_market):
        print("\n🚫 系統建議觀望 (No Bet)，跳過資金計算。")
        if not auto_mode:
            input("\n執行完畢，請按 Enter 離開...")
        return

    print(f"\n💰 資金管理...", flush=True)
    target_odds = None
    target_label = "Unknown"
    
    # 預設使用 model_p 作為概率，後續會嘗試覆蓋為 v3_prob
    v3_prob = model_p
    
    if all_markets:
        candidates = []
        for m_name, selections in all_markets.items():
            for s_name, stats in selections.items():
                if stats['max']:
                    candidates.append({
                        "market": m_name, "selection": s_name,
                        "odds": stats['max'][-1].decimal_odds, "key_str": f"{m_name} {s_name}".lower()
                    })
        
        target_str = f"{rec_market} {rec_selection}".lower()
        rec_nums = re.findall(r"[-+]?\d*\.\d+|[-+]?\d+", str(rec_market))
        best_match = None
        highest_score = 0.0
        
        for cand in candidates:
            cand_nums = re.findall(r"[-+]?\d*\.\d+|[-+]?\d+", cand['market'])
            nums_valid = True
            if rec_nums:
                for num in rec_nums:
                    if num not in cand_nums:
                        nums_valid = False; break
            if not nums_valid: continue
            
            score = difflib.SequenceMatcher(None, target_str, cand['key_str']).ratio()
            if str(rec_selection).lower() in cand['selection'].lower(): score += 0.2
            if score > highest_score:
                highest_score = score
                best_match = cand

        if best_match and highest_score > 0.6:
            target_odds = best_match['odds']
            target_label = f"{best_match['market']} - {best_match['selection']} (Max)"
            print(f"   ✅ 自動匹配賠率: {target_label} @ {target_odds}")

    if not target_odds and not auto_mode:
        try:
            user_odds = input("   👉 請手動輸入該選項賠率 (或按 Enter 跳過): ").strip()
            target_odds = float(user_odds) if user_odds else None
        except (ValueError, TypeError):
            pass

    if target_odds:
        prob = float(model_p) if isinstance(model_p, (int, float)) else 0
        stake_info = calculate_kelly_stake(prob, target_odds, settings.INITIAL_BANKROLL)
        
        print(f"\n   💰 [v3] 信心度 Kelly 資金管理:")
        try:
            kelly_v3 = ConfidenceKelly(
                base_fraction=settings.KELLY_FRACTION,
                min_edge=settings.MIN_EDGE,
                initial_bankroll=settings.INITIAL_BANKROLL
            )
            
            market_prob = 1 / target_odds
            
            # 修復: 優先使用 LLM 返回的 model_p，而非 avg_v3_prob
            # 因為 avg_v3_prob 是主勝概率，不適用於其他投注類型 (如 Under/Over, AH 等)
            if model_p > 0 and model_p < 1:
                # 使用 LLM 返回的正確概率
                v3_prob = model_p
            elif 'avg_v3_prob' in locals() and avg_v3_prob > 0:
                # 回退到 avg_v3_prob (僅當 LLM 沒有返回有效概率時)
                v3_prob = avg_v3_prob
            else:
                # 最終回退
                v3_prob = prob if prob > 0 else 0.5
            
            kelly_result = kelly_v3.calculate(
                prob=v3_prob,
                odds=target_odds,
                confidence=dynamic_confidence,  # 使用動態信心度
                model_uncertainty=model_std,   # 使用模型分歧作為不確定性
                market_prob=market_prob
            )
            
            print(f"      [信心度 Kelly]")
            print(f"         Kelly%: {kelly_result.kelly_pct:.2%}")
            print(f"         期望值: {kelly_result.ev:.3f}")
            print(f"         優勢: {kelly_result.edge:.3f}")
            print(f"         建議投注: ${kelly_result.stake:.2f}")
            
            kelly_v3_result = kelly_result.to_dict()
        except Exception as e:
            kelly_v3_result = stake_info
            print(f"      [信心度 Kelly 計算失敗: {e}]")
        
        print(f"\n   🤖 [Adv] RL 投注策略:")
        try:
            # 使用 v3_prob (如果可用) 或回退到 prob
            model_prob = v3_prob if 'v3_prob' in locals() and v3_prob is not None else prob
            implied_prob = 1 / target_odds
            edge = model_prob - implied_prob
            
            home_form_score = home_form.get('form_score', 0.5) if isinstance(home_form, dict) else 0.5
            away_form_score = away_form.get('form_score', 0.5) if isinstance(away_form, dict) else 0.5
            
            rl_agent = BettingRLAgent(
                bankroll=settings.INITIAL_BANKROLL,
                learning_rate=0.1,
                discount_factor=0.95,
                exploration_rate=0.1
            )
            
            rl_decision = rl_agent.place_bet(
                edge=edge,
                confidence=dynamic_confidence,  # 使用動態信心度（基於模型分歧）
                odds=target_odds,
                home_form=home_form_score,
                away_form=away_form_score,
                predicted_prob=model_prob
            )
            
            print(f"      [RL 策略]")
            print(f"         邊緣 (Edge): {edge:.3f}")
            print(f"         投注金額: ${rl_decision.get('bet_amount', 0):.2f}")
            
            if rl_decision.get('bet_amount', 0) > 0:
                print(f"         >>> RL 建議投注: ${rl_decision['bet_amount']:.2f}")
            
        except Exception as e:
            print(f"      [RL 策略計算失敗: {str(e)[:50]}]")
        
        # ============================================
        # [v7.1] Dutching 投注選項
        # ============================================
        print(f"\n   📊 [v7.1] Dutching 投注選項:")
        try:
            if all_markets and '1x2_home' in structured_odds:
                dutching = DutchingCalculator(target_return=0.5)  # 目標回報 50%
                
                odds_dict = {
                    'home': structured_odds.get('1x2_home', 2.0),
                    'draw': structured_odds.get('1x2_draw', 3.5),
                    'away': structured_odds.get('1x2_away', 3.0)
                }
                
                # 使用模型概率 (key name must match: probabilities)
                probabilities = {
                    'home': nb_probs.get('home_win', 0.33),
                    'draw': nb_probs.get('draw', 0.33),
                    'away': nb_probs.get('away_win', 0.33)
                }
                
                # Kelly + Dutching 結合 (修正參數名稱)
                dutch_kelly = dutching.calculate_kelly_dutching(
                    odds_dict=odds_dict,
                    probabilities=probabilities,
                    kelly_fraction=0.5
                )
                
                if dutch_kelly and dutch_kelly.get('bets'):
                    print(f"      [Dutching 投注]")
                    for selection, bet_data in dutch_kelly['bets'].items():
                        stake = bet_data.get('kelly_pct', 0) * 100  # 假設 bankroll = 100
                        print(f"         {selection}: ${stake:.2f} @ {bet_data.get('odds', 0):.2f}")
                    print(f"      總 Kelly%: ${dutch_kelly.get('total_kelly', 0)*100:.2f}")
                    print(f"      狀態: {dutch_kelly.get('status', 'N/A')}")
                else:
                    print(f"      [Dutching] 無足夠優勢，跳過")
            else:
                print(f"      [Dutching] 1x2 市場數據不足")
        except Exception as e:
            print(f"      [Dutching] 計算失敗: {str(e)[:80]}")
        
        print(f"\n   [{target_label}] 賠率 {target_odds}:")
        # 使用 ConfidenceKelly 的結果
        final_stake = kelly_v3_result.get('stake', 0)
        final_ev = kelly_v3_result.get('ev', 0)
        final_pct = kelly_v3_result.get('pct', 0)
        
        if final_stake > 0:
            print(f"      >>> 建議下注: ${final_stake:.2f} (EV: {final_ev:.3f})")
            should_log = auto_mode or input("\n[?] 記錄注單到 Excel? (y/n): ").lower() == 'y'
            if should_log:
                match_info = {"league": league_name, "home": odds_home, "away": odds_away}
                bet_info = {"market": rec_market, "selection": rec_selection, "odds": target_odds, "model_probability": v3_prob}
                logger.log_bet(match_info, bet_info, kelly_v3_result)
                logger.show_stats()
        else:
            print(f"      >>> 不建議下注 (EV < 0)")

    if not auto_mode:
        input("\n執行完畢，請按 Enter 離開...")

if __name__ == "__main__":
    auto_mode = os.getenv("AUTO_MODE", "0").lower() in {"1", "true", "yes", "on"}
    main(auto_mode=auto_mode)
