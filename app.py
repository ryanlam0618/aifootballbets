import sys
import os
import json
import re
import difflib
import pandas as pd

# 強制設定輸出編碼
sys.stdout.reconfigure(encoding='utf-8')

try:
    from config import settings
    # 匯入 LEAGUE_OPTIONS
    from src.data_modules import HistoryRepo, RealOddsFetcher, OddsPoint, LEAGUE_OPTIONS
    from src.llm_clients import llm
    from src.finance import calculate_kelly_stake, ExcelLogger
    from src.math_models import PoissonModel, MonteCarloSimulator, DixonColesModel
    from src.math_models_v2 import OptimizedDixonColes, MonteCarloSimulator as MCSim_v2
    # 導入 v3 數學模型改進
    from src.math_models_v3 import (
        NegativeBinomialModel,           # 負二項分布進球模型
        DynamicKEloSystem,              # 動態K因子 Elo
        MonteCarloSimulatorV3,          # 蒙地卡羅模擬 V3
        ConfidenceKelly                 # 信心度 Kelly
    )
    # 導入高級模型
    from src.advanced_models import (
        ExponentialDecayXGForecaster,   # 指數衰減 xG
        BayesianGoalModel,              # 貝葉斯進球模型
        TeamFormLSTM,                  # LSTM 時序模型
        BettingRLAgent                  # RL 投注策略
    )
    from src.injury_api import InjuryDataAggregator, get_injury_report
    from src.lineup_api import LineupAggregator, get_lineup
except ImportError as e:
    print(f"模組載入失敗: {e}", flush=True)
    sys.exit(1)


# ============================================
# Load Historical Team Names from CSV
# ============================================
HISTORICAL_TEAMS = {}
try:
    # 從 CSV 加載歷史數據的球隊名稱
    df_hist = pd.read_csv(settings.HISTORY_CSV_PATH)
    all_teams_hist = set(df_hist['home_team'].unique()) | set(df_hist['away_team'].unique())
    HISTORICAL_TEAMS['csv_names'] = sorted(list(all_teams_hist))
    print(f"[INFO] 已載入 {len(HISTORICAL_TEAMS['csv_names'])} 個歷史球隊名稱")
except Exception as e:
    print(f"[WARN] 無法載入歷史球隊名稱: {e}")
    HISTORICAL_TEAMS['csv_names'] = []


# ============================================
# Load The Odds API Team Names
# ============================================
ODDS_API_TEAMS = {}
try:
    odds_teams_file = 'data/odds_api_teams.json'
    if os.path.exists(odds_teams_file):
        with open(odds_teams_file, 'r', encoding='utf-8') as f:
            ODDS_API_TEAMS = json.load(f)
        print(f"[INFO] 已載入 The Odds API 球隊數據")
    else:
        # 如果沒有本地檔案，創建空結構
        ODDS_API_TEAMS = {
            'soccer_epl': [],
            'soccer_spain_la_liga': [],
            'soccer_germany_bundesliga': [],
            'soccer_italy_serie_a': [],
            'soccer_france_ligue_one': []
        }
except Exception as e:
    print(f"[WARN] 無法載入 The Odds API 球隊數據: {e}")
    ODDS_API_TEAMS = {}


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
        if response:
            # 清理回應
            response = response.strip()
            # 嘗試解析 JSON
            import json as json_mod
            result = json_mod.loads(response)
            
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
                if hist_name.lower() in away_lower or away_lower in hist_name.lower():
                    away_matched = hist_name
                    break
            
            return {
                'home': home_matched,
                'away': away_matched,
                'confidence': result.get('confidence', 'medium')
            }
    except Exception as e:
        print(f"[WARN] Gemini matching failed: {e}")
    
    # Fallback: 返回原始輸入
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
    
    # 提取球隊名稱列表
    team_names = [t.get('name', t.get('id', '')) for t in odds_teams if t.get('name')]
    
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
            result = json_mod.loads(response.strip())
            return {
                'home': result.get('home', home_input),
                'away': result.get('away', away_input)
            }
    except Exception as e:
        print(f"[WARN] Odds API matching failed: {e}")
    
    return {'home': home_input, 'away': away_input}


def find_lineup_file(home_team, away_team, data_folder="data"):
    """
    查找陣容 JSON 檔案
    """
    import glob

    def clean_team_name(name):
        import unicodedata
        import re
        name = unicodedata.normalize('NFKD', name)
        name = re.sub(r'[^a-zA-Z0-9\s]', '', name)
        return name.strip().replace(" ", "_")

    home_clean = clean_team_name(home_team)
    away_clean = clean_team_name(away_team)

    # 優先嘗試精確匹配
    exact_pattern = f"{data_folder}/lineup/lineup_{home_clean}_vs_{away_clean}.json"
    exact_matches = glob.glob(exact_pattern)
    if exact_matches:
        with open(exact_matches[0], 'r', encoding='utf-8') as f:
            return json.load(f)

    # 反向匹配
    reverse_pattern = f"{data_folder}/lineup/lineup_{away_clean}_vs_{home_clean}.json"
    reverse_matches = glob.glob(reverse_pattern)
    if reverse_matches:
        with open(reverse_matches[0], 'r', encoding='utf-8') as f:
            return json.load(f)

    return None


def main():
    print("========================================", flush=True)
    print("⚽ AI Football Analysis System v6.6 (Gemini API Matching)", flush=True)
    print("========================================", flush=True)

    # 1. 選擇聯賽
    print("\n📋 請選擇聯賽 (輸入數字):")
    sorted_keys = sorted(LEAGUE_OPTIONS.keys(), key=lambda x: int(x))
    for key in sorted_keys:
        print(f"   [{key}] {LEAGUE_OPTIONS[key]['name']}")
    
    league_idx = input("👉 選擇: ").strip()
    
    if league_idx not in LEAGUE_OPTIONS:
        print("⚠️ 輸入無效，預設使用 Premier League")
        league_idx = "1"
        
    selected_league = LEAGUE_OPTIONS[league_idx]
    league_name = selected_league['name']
    league_key = selected_league['key']
    
    print(f"✅ 已選擇: {league_name} ({league_key})")

    # 2. 輸入比賽
    match_input = input("\n👉 請輸入比賽對戰組合 (Enter 預設 Bournemouth vs Tottenham): ").strip()
    if not match_input: match_input = "Bournemouth vs Tottenham"

    try:
        if re.search(r"\s+vs\.?\s+", match_input, re.IGNORECASE) or " v " in match_input:
            parts = re.split(r"\s+vs\.?\s+|\s+v\s+", match_input, flags=re.IGNORECASE)
            if len(parts) >= 2:
                home, away = parts[0].strip(), parts[1].strip()
            else:
                print("⚠️ 格式錯誤"); return
        else: 
            print("⚠️ 格式錯誤"); return
    except ValueError: return

    # ============================================
    # 使用 Gemini API 進行球隊名稱匹配
    # ============================================
    print(f"\n🔗 [1.1/4] 使用 Gemini API 匹配球隊名稱...", flush=True)
    print(f"   原始輸入: {home} vs {away}")
    print(f"   聯賽上下文: {league_name}")

    # Step 1: 匹配到歷史數據庫 (CSV)
    print(f"\n   [1/3] 匹配到歷史數據庫...")
    hist_match = match_with_gemini(home, away, HISTORICAL_TEAMS.get('csv_names', []), league_name)
    db_home = hist_match['home']
    db_away = hist_match['away']
    print(f"      [HIST] {home} -> {db_home} (confidence: {hist_match['confidence']})")
    print(f"      [HIST] {away} -> {db_away} (confidence: {hist_match['confidence']})")

    # Step 2: 匹配到 The Odds API
    print(f"\n   [2/3] 匹配到 The Odds API...")
    odds_match = match_to_odds_api(home, away, league_key)
    odds_home = odds_match['home']
    odds_away = odds_match['away']
    print(f"      [ODDS] {home} -> {odds_home}")
    print(f"      [ODDS] {away} -> {odds_away}")

    # 初始化
    repo = HistoryRepo(settings.HISTORY_CSV_PATH)
    odds_fetcher = RealOddsFetcher()
    logger = ExcelLogger()

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
        print(f"   [INFO] 未找到本地陣容檔案")
        
        # 等待用戶輸入 Fotmob Match ID
        fotmob_id = input("   👉 請輸入 Fotmob Match ID (或按 Enter 跳過): ").strip()
        
        if fotmob_id:
            try:
                from TakeData.fotmob_lineup_scraper import FotMobLineupHarvester
                harvester = FotMobLineupHarvester(fotmob_id)
                lineup_data = harvester.fetch_lineup(save_to_file=True)
                if lineup_data:
                    print(f"   [FOTMOB] 成功獲取陣容: {lineup_data['home_team']['name']} vs {lineup_data['away_team']['name']}")
            except Exception as e:
                print(f"   [FOTMOB] 獲取失敗: {e}")

    # 4. 傷停數據 (已停用)
    print(f"\n[1.3/4] 傷停數據功能已停用", flush=True)
    injury_report = {
        'home': {'injuries': [], 'total_impact': 0},
        'away': {'injuries': [], 'total_impact': 0},
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

    mc_sim = MCSim_v2(h_exp_adj, a_exp_adj)
    mc_probs = mc_sim.run_simulation()

    # ========== [v3] 負二項分布 ==========
    print(f"\n   🎯 [v3] 負二項分布模型:")
    nb_model = NegativeBinomialModel(h_exp_adj, a_exp_adj, dispersion=1.5, calibrate_dispersion=False)
    nb_probs = nb_model.calculate_probabilities()
    print(f"      主勝: {nb_probs['home_win']:.1%} | 和局: {nb_probs['draw']:.1%} | 客勝: {nb_probs['away_win']:.1%}")

    # ========== [v3] 動態K Elo ==========
    print(f"\n   📈 [v3] 動態K Elo 評分:")
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
    mc_v3 = MonteCarloSimulatorV3(h_exp_adj, a_exp_adj, iterations=10000, use_nbinom=True, dispersion=1.5)
    mc_v3_probs = mc_v3.run_simulation()
    print(f"      主勝: {mc_v3_probs['mc_home_win']:.1%} | 和局: {mc_v3_probs['mc_draw']:.1%} | 客勝: {mc_v3_probs['mc_away_win']:.1%}")

    # ========== [Advanced] 指數衰減 xG ==========
    print(f"\n   📈 [Adv] 指數衰減 xG 預測:")
    
    xg_forecast_home, xg_forecast_away = h_exp_adj, a_exp_adj
    home_xg_adv = {'xg': h_exp_adj, 'n_games': 0}
    away_xg_adv = {'xg': a_exp_adj, 'n_games': 0}
    
    try:
        xg_forecaster = ExponentialDecayXGForecaster(decay_rate=0.1, recency_weight=1.5, min_games=2)
        
        print(f"      [GEMINI] 使用 Gemini 匹配的歷史名稱: {db_home}, {db_away}")
        
        if hasattr(repo, 'df') and not repo.df.empty:
            valid_df = repo.df.dropna(subset=['home_team', 'away_team'])
            if 'xg' in valid_df.columns:
                valid_df = valid_df[valid_df['xg'].notna()]
            
            print(f"      [DEBUG] 載入 {len(valid_df)} 場有效比賽")
            
            home_xg_col = 'xg'
            away_xg_col = 'xga'
            
            if home_xg_col and away_xg_col:
                match_count = 0
                recent_df = valid_df.tail(1000)
                
                for _, row in recent_df.iterrows():
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
                
                print(f"      [DEBUG] 已載入 {match_count} 場比賽數據")
        
        import datetime
        ref_date = datetime.datetime.now()
        
        home_result = xg_forecaster.get_team_xg(db_home, ref_date, True)
        away_result = xg_forecaster.get_team_xg(db_away, ref_date, False)
        
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
                    
                    uncertainty = bayes_pred.get('uncertainty', {})
                    for key in uncertainty:
                        uncertainty[key] = min(1.0, max(0.0, uncertainty.get(key, 0.3)))
        
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

    # 計算綜合勝率
    avg_v3_prob = (nb_probs['home_win'] + mc_v3_probs['mc_home_win'] + elo_win_prob) / 3
    print(f"\n   📊 [v3] 綜合勝率: {avg_v3_prob:.1%}")

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
        "expected_goals": {"home": h_exp_adj, "away": a_exp_adj},
        "injury_impact": {"home": 0, "away": 0, "diff": 0, "disabled": True}
    }

    glicko = match_context.get("glicko", {})
    print(f"   [INFO] 傷停調整已停用")
    print(f"      {odds_home} {h_exp_adj:.2f} - {a_exp_adj:.2f} {odds_away}")
    print(f"   🏆 Glicko-2 勝率: {glicko.get('win_prob', 0):.1%}")

    # 6. 讀取即時賠率
    print(f"\n📈 [2/4] 連線 API 讀取即時賠率...", flush=True)
    all_markets = odds_fetcher.get_real_odds(league_key, odds_home, odds_away)
    
    odds_summary_text = ""
    if all_markets:
        print(f"   ✅ 成功解析 {len(all_markets)} 個投注市場")
        for market, selections in all_markets.items():
            line_str = f"   🔹 {market}: "
            for sel, stats in selections.items():
                if stats['avg']:
                    avg_o = stats['avg'][-1].decimal_odds
                    implied = (1 / avg_o) * 100
                    line_str += f"{sel}[{avg_o}|{implied:.1f}%] "
                    odds_summary_text += f"{market} {sel} -> Odds:{avg_o} (Implied:{implied:.1f}%) | "
            print(line_str)
    else:
        print("   ⚠️ 無有效賠率數據")
        odds_summary_text = "No Odds Data Available"

    # 7. Grok 搜尋
    print(f"\n🤖 [3/4] 請求 Grok 聯網搜尋市場情報...", flush=True)
    grok_input = odds_summary_text[:1500]
    grok_reaction = llm.search_and_analyze_market_reaction(f"{odds_home} vs {odds_away}", grok_input)
    print("\n--------- 🤖 Grok 市場觀點 ---------", flush=True)
    print(grok_reaction[:200] + "..." if len(grok_reaction) > 200 else grok_reaction, flush=True)

    # 8. ChatGPT 決策
    print(f"\n🧠 [4/4] ChatGPT 綜合決策...", flush=True)
    odds_data_package = {
        "full_market_odds": odds_summary_text,
        "market_reaction": grok_reaction
    }
    
    rec = llm.analyze_with_super_prompt(match_context, odds_data_package, math_results).get("recommendation", {})

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
        input("\n執行完畢，請按 Enter 離開...")
        return

    print(f"\n💰 資金管理...", flush=True)
    target_odds = None
    target_label = "Unknown"
    
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

    if not target_odds:
        try:
            user_odds = input("   👉 請手動輸入該選項賠率 (或按 Enter 跳過): ").strip()
            target_odds = float(user_odds) if user_odds else None
        except: pass

    if target_odds:
        prob = float(model_p) if isinstance(model_p, (int, float)) else 0
        stake_info = calculate_kelly_stake(prob, target_odds, settings.INITIAL_BANKROLL)
        
        print(f"\n   💰 [v3] 信心度 Kelly 資金管理:")
        try:
            kelly_v3 = ConfidenceKelly(
                base_fraction=0.75,
                min_edge=0.08,
                initial_bankroll=settings.INITIAL_BANKROLL
            )
            
            market_prob = 1 / target_odds
            v3_prob = avg_v3_prob if 'avg_v3_prob' in dir() else prob
            
            kelly_result = kelly_v3.calculate(
                prob=v3_prob,
                odds=target_odds,
                confidence=0.7,
                model_uncertainty=0.1,
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
            model_prob = v3_prob if 'v3_prob' in dir() else prob
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
                confidence=1 - bayes_pred.get('uncertainty', {}).get('average', 0.3),
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
        
        print(f"\n   [{target_label}] 賠率 {target_odds}:")
        if stake_info["stake"] > 0:
            print(f"      >>> 建議下注: ${stake_info['stake']:.2f} (EV: {stake_info['ev']:.3f})")
            if input("\n[?] 記錄注單到 Excel? (y/n): ").lower() == 'y':
                match_info = {"league": league_name, "home": odds_home, "away": odds_away}
                bet_info = {"market": rec_market, "selection": rec_selection, "odds": target_odds, "model_probability": prob}
                logger.log_bet(match_info, bet_info, stake_info)
                logger.show_stats()
        else:
            print(f"      >>> 不建議下注 (EV < 0)")

    input("\n執行完畢，請按 Enter 離開...")

if __name__ == "__main__":
    main()
