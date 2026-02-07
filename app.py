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
    from src.team_name_matcher import match_teams, get_team_info
except ImportError as e:
    print(f"模組載入失敗: {e}", flush=True)
    sys.exit(1)

def find_lineup_file(home_team, away_team, data_folder="data"):
    """
    查找陣容 JSON 檔案
    Args:
        home_team: 主隊名稱
        away_team: 客隊名稱
        data_folder: 資料夾路徑
    Returns:
        lineup_data (dict) 或 None
    """
    import glob

    # 清理隊名中的特殊字符
    def clean_team_name(name):
        # 移除常見的擴展字符，保持簡單的字母數字和底線
        import unicodedata
        name = unicodedata.normalize('NFKD', name)
        # 只保留字母數字和底線
        import re
        name = re.sub(r'[^a-zA-Z0-9\s]', '', name)
        return name.strip().replace(" ", "_")

    home_clean = clean_team_name(home_team)
    away_clean = clean_team_name(away_team)

    # 優先嘗試精確匹配 (主隊 vs 客隊)
    exact_pattern = f"{data_folder}/lineup/lineup_{home_clean}_vs_{away_clean}.json"
    exact_matches = glob.glob(exact_pattern)
    if exact_matches:
        with open(exact_matches[0], 'r', encoding='utf-8') as f:
            return json.load(f)

    # 嘗試反向匹配 (客隊 vs 主隊)
    reverse_pattern = f"{data_folder}/lineup/lineup_{away_clean}_vs_{home_clean}.json"
    reverse_matches = glob.glob(reverse_pattern)
    if reverse_matches:
        with open(reverse_matches[0], 'r', encoding='utf-8') as f:
            return json.load(f)

    # 模糊搜索 - 遍歷所有檔案找匹配的
    all_files = glob.glob(f"{data_folder}/lineup/*.json")
    for filepath in all_files:
        filename = os.path.basename(filepath)
        # 提取檔名中的隊名
        # 格式: lineup_HomeName_vs_AwayName.json
        match = re.match(r'lineup_(.+?)_vs_(.+?)\.json', filename)
        if match:
            file_home = match.group(1)
            file_away = match.group(2)

            # 清理檔案中的隊名
            file_home_clean = clean_team_name(file_home)
            file_away_clean = clean_team_name(file_away)

            # 使用 difflib 計算相似度
            home_score = difflib.SequenceMatcher(None, home_clean.lower(), file_home_clean.lower()).ratio()
            away_score = difflib.SequenceMatcher(None, away_clean.lower(), file_away_clean.lower()).ratio()
            
            # 計算反向匹配分數（考慮主客隊互換的情況）
            home_score_rev = difflib.SequenceMatcher(None, home_clean.lower(), file_away_clean.lower()).ratio()
            away_score_rev = difflib.SequenceMatcher(None, away_clean.lower(), file_home_clean.lower()).ratio()
            
            # 選擇最佳匹配方向
            score_normal = (home_score + away_score) / 2
            score_rev = (home_score_rev + away_score_rev) / 2
            
            if score_normal >= score_rev:
                final_score = score_normal
                min_team_match = min(home_score, away_score)
            else:
                final_score = score_rev
                min_team_match = min(home_score_rev, away_score_rev)

            # 關鍵修復：兩個隊都必須有較高匹配度 (>0.8)
            # 這確保 "Arsenal vs Chelsea" 不會錯誤匹配到 "Arsenal vs Liverpool"
            if final_score > 0.6 and min_team_match > 0.8:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)

    return None


def main():
    print("========================================", flush=True)
    print("⚽ AI 足球分析系統 v6.5 (API Integrated) - Team Name Matcher", flush=True)
    print("========================================", flush=True)

    # 1. 選擇聯賽 (新增選單功能)
    print("\n📋 請選擇聯賽 (輸入數字):")
    # 排序並顯示選單
    sorted_keys = sorted(LEAGUE_OPTIONS.keys(), key=lambda x: int(x))
    for key in sorted_keys:
        print(f"   [{key}] {LEAGUE_OPTIONS[key]['name']}")
    
    league_idx = input("👉 選擇: ").strip()
    
    # 預設為英超
    if league_idx not in LEAGUE_OPTIONS:
        print("⚠️ 輸入無效，預設使用 Premier League")
        league_idx = "1"
        
    selected_league = LEAGUE_OPTIONS[league_idx]
    league_name = selected_league['name']
    league_key = selected_league['key'] # API 需要這個 key
    
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

    # ========== [整合] 使用 Gemini API 智能匹配球隊名稱 ==========
    print(f"\n🔗 [1.1/4] 正在整合 The Odds API 與 API-Football 數據...", flush=True)
    print(f"   原始輸入: {home} vs {away}")

    # 使用 team_name_matcher 整合兩個 API 的 ID
    match_result = match_teams(home, away)

    # 獲取標準化後的隊名
    odds_home = home  # 預設使用輸入
    odds_away = away
    api_home = home   # 預設使用輸入
    api_away = away

    # 解析配對結果
    if match_result.get('home', {}).get('matched'):
        api_home = match_result['home'].get('api_name', home)
        odds_home = match_result['home'].get('odds_name', home)
        api_home_id = match_result['home'].get('api_football_id')
        print(f"   [主隊] The Odds API: {odds_home} | API-Football ID: {api_home_id} ({api_home})")
    else:
        api_home_id = None
        print(f"   [主隊] ⚠️ 無法自動配對，使用原始名稱: {home}")

    if match_result.get('away', {}).get('matched'):
        api_away = match_result['away'].get('api_name', away)
        odds_away = match_result['away'].get('odds_name', away)
        api_away_id = match_result['away'].get('api_football_id')
        print(f"   [客隊] The Odds API: {odds_away} | API-Football ID: {api_away_id} ({api_away})")
    else:
        api_away_id = None
        print(f"   [客隊] ⚠️ 無法自動配對，使用原始名稱: {away}")

    # 檢查是否需要 Gemini 進一步匹配
    if not match_result.get('home', {}).get('matched') or not match_result.get('away', {}).get('matched'):
        print(f"   💡 提示: 如需更精確的匹配，請確認球隊名稱拼寫正確。")

    # 使用 API-Football ID 進行後續操作
    home_team_id = api_home_id if api_home_id else match_result.get('home', {}).get('api_football_id')
    away_team_id = api_away_id if api_away_id else match_result.get('away', {}).get('api_football_id')

    # 初始化
    repo = HistoryRepo(settings.HISTORY_CSV_PATH)
    odds_fetcher = RealOddsFetcher()
    logger = ExcelLogger()

    # 2.5 讀取/獲取陣容數據
    print(f"\n👕 [1.2/4] 正在獲取陣容數據...", flush=True)

    # 首先嘗試讀取本地陣容檔案 (使用用戶輸入的原始名稱)
    lineup_data = find_lineup_file(home, away)

    if lineup_data:
        print(f"   [本地] 找到陣容檔案: {lineup_data['home_team']['name']} vs {lineup_data['away_team']['name']}")
        print(f"      主隊陣容: {len(lineup_data['home_team']['starters'])} 人 | 客隊陣容: {len(lineup_data['away_team']['starters'])} 人")
    else:
        # 本地沒有，嘗試從 API 獲取 (使用 API-Football 標準化後的隊名)
        print(f"   [API] 未找到本地檔案，嘗試 API 獲取...")
        lineup_aggregator = LineupAggregator()
        lineup_data = lineup_aggregator.get_lineup(api_home, api_away)

    # 2.6 傷停數據 (已停用)
    print(f"\n[1.3/4] 傷停數據功能已停用", flush=True)
    # 使用空數據作為佔位
    injury_report = {
        'home': {'injuries': [], 'suspensions': [], 'total_impact': 0, 'key_players': []},
        'away': {'injuries': [], 'suspensions': [], 'total_impact': 0, 'key_players': []},
        'impact_diff': 0
    }
    home_injury = injury_report['home']
    away_injury = injury_report['away']

    # 計算傷停影響差異
    injury_impact_diff = 0
    print(f"\n   [INFO] 傷停數據已停用 (使用預設值 0)")

    # 3. 獲取數據 & 數學模型 (傳入 league_name 給歷史數據模組顯示用)
    print(f"\n🔍 [1/4] 執行 Glicko-2 回測與機器學習預測...", flush=True)
    match_context = repo.get_match_context(home, away, league_name)
    stats = match_context.get("stats", {})
    
    # 陣容分析
    print(f"👕 [1.5/4] 分析首發名單評分 (Lineup Rating)...", flush=True)
    lineup_prob = repo.get_lineup_prediction(home, away)
    if lineup_prob:
        print(f"   [基於首發球員評分的主勝率: {lineup_prob:.1%}")
    else:
        print("   [未找到首發名單 JSON，跳過。")

    # 數學運算 (傷停功能已停用)
    h_exp = stats.get("home_weighted_xg", 1.2)
    a_exp = stats.get("away_weighted_xg", 1.0)

    # 傷停調整已停用，使用原始 xG
    h_exp_adj = h_exp
    a_exp_adj = a_exp

    # 確保值合理
    h_exp_adj = max(0.5, min(3.5, h_exp_adj))
    a_exp_adj = max(0.5, min(3.5, a_exp_adj))

    print(f"\n   [INFO] 傷停調整已停用，使用原始 xG")
    print(f"      {odds_home} {h_exp_adj:.2f} - {a_exp_adj:.2f} {odds_away}")

    dc_model = DixonColesModel(h_exp_adj, a_exp_adj)
    dc_probs = dc_model.calculate_probabilities()

    mc_sim = MCSim_v2(h_exp_adj, a_exp_adj)
    mc_probs = mc_sim.run_simulation()

    # ========== [v3] 負二項分布進球模型 ==========
    # 比 Poisson 更準確，處理進球過離散問題
    print(f"\n   🎯 [v3] 負二項分布模型:")
    nb_model = NegativeBinomialModel(h_exp_adj, a_exp_adj, dispersion=1.5, calibrate_dispersion=False)
    nb_probs = nb_model.calculate_probabilities()
    print(f"      主勝: {nb_probs['home_win']:.1%} | 和局: {nb_probs['draw']:.1%} | 客勝: {nb_probs['away_win']:.1%}")
    print(f"      離散參數 (α): {nb_probs.get('dispersion', 1.5):.2f}")

    # ========== [v3] 動態K因子 Elo 評分系統 ==========
    # 比標準 Elo 更敏感，根據對手實力和比賽結果調整
    print(f"\n   📈 [v3] 動態K Elo 評分:")
    dynamic_elo = DynamicKEloSystem(base_k=20)
    # 使用歷史數據更新評分
    try:
        valid_df = repo.df.dropna(subset=['home_goals', 'away_goals', 'home_team', 'away_team'])
        for _, row in valid_df.tail(100).iterrows():
            try:
                dynamic_elo.update_ratings(
                    row['home_team'], row['away_team'],
                    int(row['home_goals']), int(row['away_goals'])
                )
            except:
                continue
    except:
        pass
    elo_home = dynamic_elo.get_rating(api_home)
    elo_away = dynamic_elo.get_rating(api_away)
    elo_win_prob = dynamic_elo.expected_win_prob(api_home, api_away)
    print(f"      {odds_home} 評分: {elo_home:.0f} | {odds_away} 評分: {elo_away:.0f}")
    print(f"      Elo 勝率預測: {elo_win_prob:.1%}")

    # ========== [v3] 蒙地卡羅模擬 V3 ==========
    # 使用 Gamma-Poisson 混合物，更穩定
    print(f"\n   🎲 [v3] 蒙地卡羅模擬 (10,000次):")
    mc_v3 = MonteCarloSimulatorV3(h_exp_adj, a_exp_adj, iterations=10000, use_nbinom=True, dispersion=1.5)
    mc_v3_probs = mc_v3.run_simulation()
    print(f"      主勝: {mc_v3_probs['mc_home_win']:.1%} | 和局: {mc_v3_probs['mc_draw']:.1%} | 客勝: {mc_v3_probs['mc_away_win']:.1%}")
    print(f"      大2.5: {mc_v3_probs['mc_over_2.5']:.1%}")
    print(f"      期望進球: {mc_v3_probs['expected_goals']['home']:.2f} - {mc_v3_probs['expected_goals']['away']:.2f}")

    # ========== [Advanced] 指數衰減 xG 預測 ==========
    # 近期權重更高，自適應球隊風格
    print(f"\n   📈 [Adv] 指數衰減 xG 預測:")
    
    # 預設值 (在 try block 外部定義，避免 UnboundLocalError)
    xg_forecast_home, xg_forecast_away = h_exp_adj, a_exp_adj
    home_xg_adv = {'xg': h_exp_adj, 'n_games': 0}
    away_xg_adv = {'xg': a_exp_adj, 'n_games': 0}
    
    try:
        xg_forecaster = ExponentialDecayXGForecaster(decay_rate=0.1, recency_weight=1.5, min_games=2)  # 改為 2 場
        # 使用歷史數據填充
        if hasattr(repo, 'df') and not repo.df.empty:
            valid_df = repo.df.dropna(subset=['home_team', 'away_team'])
            
            # 只使用有 xG 數據的行
            if 'xg' in valid_df.columns:
                valid_df = valid_df[valid_df['xg'].notna()]
            
            print(f"      [DEBUG] 指數衰減 xG: 載入 {len(valid_df)} 場有效比賽")
            
            # 支援不同欄位名稱
            xg_cols = valid_df.columns.tolist()
            home_xg_col = 'xg'
            away_xg_col = 'xga'
            
            print(f"      [DEBUG] 找到 xG 欄位: home={home_xg_col}, away={away_xg_col}")
            
            # ========== Fuzzy Search 球隊名稱匹配 ==========
            try:
                from fuzzywuzzy import fuzz, process
                HAS_FUZZY = True
            except ImportError:
                HAS_FUZZY = False
            
            # 建立所有可用球隊名稱列表 (使用完整數據，不僅限於 xG 數據)
            all_teams = set(list(repo.df['home_team'].unique()) + list(repo.df['away_team'].unique()))
            all_teams_list = list(all_teams)
            
            # 檢查有效數據中的球隊 (用於模型載入)
            if 'xg' in valid_df.columns:
                valid_teams = set(list(valid_df['home_team'].unique()) + list(valid_df['away_team'].unique()))
            else:
                valid_teams = all_teams
            
            # 常見縮寫/別名映射 (提高匹配準確率)
            ALIAS_MAP = {
                # English Premier League
                "manchester united": "Manchester United",
                "manchester utd": "Manchester United",
                "man utd": "Manchester United",
                "manchester city": "Manchester City",
                "man city": "Manchester City",
                "newcastle": "Newcastle United",
                "newcastle utd": "Newcastle United",
                "spurs": "Tottenham Hotspur",
                "tottenham": "Tottenham Hotspur",
                "arsenal london": "Arsenal",
                "west ham": "West Ham United",
                "wolverhampton": "Wolverhampton Wanderers",
                "wolves": "Wolverhampton Wanderers",
                "leicester": "Leicester City",
                "leeds": "Leeds United",
                "crystal palace": "Crystal Palace",
                "brighton": "Brighton & Hove Albion",
                "southampton": "Southampton",
                "fulham": "Fulham",
                "brentford": "Brentford",
                "nottingham": "Nottingham Forest",
                "villa": "Aston Villa",
                "ipswich": "Ipswich Town",
                
                # Spanish La Liga
                "atletico": "Ath Madrid",
                "atletico madrid": "Ath Madrid",
                "atlético madrid": "Ath Madrid",
                "barca": "Barcelona",
                "sevila": "Sevilla",
                "sevilla fc": "Sevilla",
                "sociedad": "Real Sociedad",
                "betis": "Real Betis",
                
                # Italian Serie A
                "inter": "Inter Milan",
                "ac milan": "AC Milan",
                "milan": "AC Milan",
                "juventus turin": "Juventus",
                "napoli": "SSC Napoli",
                "ssc napoli": "SSC Napoli",
                "as roma": "AS Roma",
                "lazio": "Lazio",
                "fiorentina": "Fiorentina",
                "torino": "Torino",
                "sampdoria": "Sampdoria",
                "udinese": "Udinese",
                "bologna": "Bologna",
                "atalanta": "Atalanta BC",
                
                # German Bundesliga
                "bayern": "Bayern Munich",
                "dortmund": "Borussia Dortmund",
                "borussia dortmund": "Borussia Dortmund",
                "leverkusen": "Bayer Leverkusen",
                "bayer leverkusen": "Bayer Leverkusen",
                "rb leipzig": "RB Leipzig",
                "leipzig": "RB Leipzig",
                "m'gladbach": "Borussia Mönchengladbach",
                "gladbach": "Borussia Mönchengladbach",
                "eintracht frankfurt": "Eintracht Frankfurt",
                "frankfurt": "Eintracht Frankfurt",
                "schalke": "Schalke 04",
                "schalke 04": "Schalke 04",
                
                # French Ligue 1
                "psg": "Paris SG",
                "paris sg": "Paris SG",
                "paris saint germain": "Paris SG",
                "lyon": "Olympique Lyonnais",
                "olympique lyonnais": "Olympique Lyonnais",
                "marseille": "Olympique de Marseille",
                "olympique marseille": "Olympique de Marseille",
                "monaco": "Monaco",
                "as monaco": "Monaco",
                "nice": "OGC Nice",
                "ogc nice": "OGC Nice",
                "lille": "Lille",
                "rennes": "Stade Rennais",
                "stade rennais": "Stade Rennais",
            }
            
            def fuzzy_match_team(input_name, team_list, threshold=60):
                """使用模糊匹配找最佳球隊名稱"""
                if not HAS_FUZZY:
                    return input_name  # fallback
                
                clean_input = input_name.lower().strip()
                
                # 調試信息
                # print(f"      [DEBUG-FUZZY] 輸入: \"{input_name}\" -> clean: \"{clean_input}\"")
                
                # 先檢查別名映射 (精確匹配)
                if clean_input in ALIAS_MAP:
                    matched = ALIAS_MAP[clean_input]
                    # print(f"      [DEBUG-FUZZY] ALIAS_MAP 命中: \"{clean_input}\" -> \"{matched}\"")
                    if matched in team_list:
                        return matched
                
                # 檢查原始名稱是否已存在於 team_list
                if input_name in team_list:
                    # print(f"      [DEBUG-FUZZY] 原始名稱命中: \"{input_name}\"")
                    return input_name
                
                # 檢查小寫版本是否在 team_list
                if clean_input in [t.lower() for t in team_list]:
                    for team in team_list:
                        if team.lower() == clean_input:
                            # print(f"      [DEBUG-FUZZY] 小寫版本命中: \"{input_name}\" -> \"{team}\"")
                            return team
                
                best_match = None
                best_score = 0
                
                for team in team_list:
                    clean_team = team.lower().strip()
                    
                    # 計算分數時保留 "united" 等關鍵詞
                    scores = [
                        fuzz.ratio(clean_input, clean_team),
                        fuzz.partial_ratio(clean_input, clean_team),
                        fuzz.token_sort_ratio(clean_input, clean_team),
                        fuzz.token_set_ratio(clean_input, clean_team),
                    ]
                    
                    team_score = max(scores)
                    
                    if team_score > best_score:
                        best_score = team_score
                        best_match = team
                
                # print(f"      [DEBUG-FUZZY] 最佳匹配: \"{best_match}\" (score: {best_score})")
                
                if best_score >= threshold:
                    return best_match
                return input_name  # fallback
            
            # 使用模糊匹配
            target_home = fuzzy_match_team(api_home, all_teams_list)
            target_away = fuzzy_match_team(api_away, all_teams_list)
            
            print(f"      [FUZZY] \"{api_home}\" -> \"{target_home}\"")
            print(f"      [FUZZY] \"{api_away}\" -> \"{target_away}\"")
            
            if home_xg_col and away_xg_col:
                match_count = 0
                mu_home_count = 0
                mu_away_count = 0
                
                # 修復：數據是按日期升序排列（最舊在前），所以用 tail() 取最新的數據
                # 擴大載入範圍到 1000 場，確保載入足夠數據
                recent_df = valid_df.tail(1000)
                
                print(f"      [DEBUG] 指數衰減 xG: 載入 {len(recent_df)} 場最近比賽")
                print(f"      [DEBUG] 數據範圍: {recent_df['date'].min()} 到 {recent_df['date'].max()}")
                
                for _, row in recent_df.iterrows():
                    try:
                        home_xg_val = float(row.get(home_xg_col, 1.5))
                        away_xg_val = float(row.get(away_xg_col, 1.0))
                        
                        # 跳過無效的 xG 值
                        if pd.isna(home_xg_val) or home_xg_val <= 0:
                            home_xg_val = float(row['home_goals']) if pd.notna(row.get('home_goals')) else 1.5
                        if pd.isna(away_xg_val) or away_xg_val <= 0:
                            away_xg_val = float(row['away_goals']) if pd.notna(row.get('away_goals')) else 1.0
                        
                        # 添加主隊數據 (直接傳入 datetime 物件)
                        xg_forecaster.add_match(row['home_team'], home_xg_val, True, row['date'])
                        # 添加客隊數據
                        xg_forecaster.add_match(row['away_team'], away_xg_val, False, row['date'])
                        
                        # 統計 Manchester United 數據
                        if row['home_team'] == target_home or row['away_team'] == target_home:
                            mu_home_count += 1
                        if row['home_team'] == target_away or row['away_team'] == target_away:
                            mu_away_count += 1
                        
                        match_count += 1
                    except:
                        continue
                
                print(f"      [DEBUG] 已載入 {match_count} 場比賽數據")
                print(f"      [DEBUG] {target_home} 載入: {mu_home_count} 場")
                print(f"      [DEBUG] {target_away} 載入: {mu_away_count} 場")
                
                # 使用匹配後的球隊名稱獲取預測
                import datetime
                ref_date = datetime.datetime.now()
                
                # 先用原始名稱嘗試
                home_result = xg_forecaster.get_team_xg(target_home, ref_date, True)
                away_result = xg_forecaster.get_team_xg(target_away, ref_date, False)
                
                # 如果沒有數據，嘗試用用戶輸入的名稱
                if home_result.get('n_games', 0) == 0:
                    home_result = xg_forecaster.get_team_xg(api_home, ref_date, True)
                if away_result.get('n_games', 0) == 0:
                    away_result = xg_forecaster.get_team_xg(api_away, ref_date, False)
        
        # 獲取預測
        import datetime
        ref_date = datetime.datetime.now()
        home_result = xg_forecaster.get_team_xg(api_home, ref_date, True)
        away_result = xg_forecaster.get_team_xg(api_away, ref_date, False)
        
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
    # 完全概率化不確定性估計
    print(f"\n   🔮 [Adv] 貝葉斯進球模型:")
    
    # 預設值
    bayes_pred = {
        'home_lambda': h_exp_adj,
        'away_lambda': a_exp_adj,
        'home_ci': (h_exp_adj * 0.5, h_exp_adj * 1.5),
        'away_ci': (a_exp_adj * 0.5, a_exp_adj * 1.5),
        'probabilities': {'home_win': nb_probs['home_win'], 'draw': nb_probs['draw'], 'away_win': nb_probs['away_win']},
        'uncertainty': {'average': 0.3, 'home': 0.3, 'away': 0.3}
    }
    
    try:
        bayes_model = BayesianGoalModel(confidence_level=0.95)
        # 使用歷史數據
        if hasattr(repo, 'df') and not repo.df.empty:
            valid_df = repo.df.dropna(subset=['home_goals', 'away_goals'])
            
            # 只使用有 xG 數據的行 (repo.df.columns 是小寫)
            if 'xg' in valid_df.columns:
                valid_df = valid_df[valid_df['xg'].notna()]
            
            print(f"      [DEBUG] Bayesian: 載入 {len(valid_df)} 場有效比賽")
            
            obs_count = 0
            mu_obs_count = 0
            if len(valid_df) >= 5:
                # 修復：數據是按日期升序排列，用 tail() 取最近的數據
                recent_valid = valid_df.tail(200)
                print(f"      [DEBUG] Bayesian: 使用最近 {len(recent_valid)} 場比賽")
                
                # 使用 xG 值，如果沒有則 fallback 到實際進球
                for _, row in recent_valid.iterrows():
                    try:
                        # 主隊觀察
                        home_xg = float(row.get('xg', 1.5)) if pd.notna(row.get('xg')) else float(row['home_goals'])
                        bayes_model.add_observation(
                            int(row['home_goals']), 
                            int(row['away_goals']),
                            home_xg=home_xg,
                            is_home=True
                        )
                        # 客隊觀察
                        away_xg = float(row.get('xga', 1.0)) if pd.notna(row.get('xga')) else float(row['away_goals'])
                        bayes_model.add_observation(
                            int(row['away_goals']),
                            int(row['home_goals']),
                            home_xg=away_xg,
                            is_home=False
                        )
                        obs_count += 2
                        
                        # 統計目標球隊
                        if row['home_team'] == target_home or row['away_team'] == target_home:
                            mu_obs_count += 1
                    except: continue
                
                if obs_count > 0:
                    bayes_pred = bayes_model.predict()
                    print(f"      [DEBUG] Bayesian: 觀察數量={obs_count}, home_lambda={bayes_pred['home_lambda']:.3f}")
                    print(f"      [DEBUG] {target_home} 觀察數: {mu_obs_count}")
                    
                    # 限制不確定性在合理範圍 (0-100%)
                    uncertainty = bayes_pred.get('uncertainty', {})
                    for key in uncertainty:
                        uncertainty[key] = min(1.0, max(0.0, uncertainty.get(key, 0.3)))
                else:
                    # Fallback
                    bayes_pred = {
                        'home_lambda': xg_forecast_home,
                        'away_lambda': xg_forecast_away,
                        'home_ci': (xg_forecast_home * 0.7, xg_forecast_home * 1.3),
                        'away_ci': (xg_forecast_away * 0.7, xg_forecast_away * 1.3),
                        'probabilities': nb_probs,
                        'uncertainty': {'average': 0.5}
                    }
            else:
                # 使用指數衰減 xG 的結果作為先驗
                bayes_pred = {
                    'home_lambda': xg_forecast_home,
                    'away_lambda': xg_forecast_away,
                    'home_ci': (xg_forecast_home * 0.7, xg_forecast_home * 1.3),
                    'away_ci': (xg_forecast_away * 0.7, xg_forecast_away * 1.3),
                    'probabilities': nb_probs,
                    'uncertainty': {'average': 0.5}
                }
        else:
            # 使用指數衰減 xG 的結果
            bayes_pred = {
                'home_lambda': xg_forecast_home,
                'away_lambda': xg_forecast_away,
                'home_ci': (xg_forecast_home * 0.7, xg_forecast_home * 1.3),
                'away_ci': (xg_forecast_away * 0.7, xg_forecast_away * 1.3),
                'probabilities': nb_probs,
                'uncertainty': {'average': 0.5}
            }
        
        print(f"      主場 λ: {bayes_pred['home_lambda']:.3f} [{bayes_pred['home_ci'][0]:.2f}-{bayes_pred['home_ci'][1]:.2f}]")
        print(f"      客場 λ: {bayes_pred['away_lambda']:.3f} [{bayes_pred['away_ci'][0]:.2f}-{bayes_pred['away_ci'][1]:.2f}]")
        probs = bayes_pred.get('probabilities', {})
        print(f"      主勝概率: {probs.get('home_win', nb_probs['home_win']):.1%}")
        print(f"      不確定性: {bayes_pred['uncertainty']['average']:.1%}")
    except Exception as e:
        print(f"      ⚠️ 貝葉斯模型失敗: {str(e)[:80]}")

    # ========== [Advanced] LSTM 狀態追蹤 ==========
    # 捕捉球隊狀態變化
    print(f"\n   📊 [Adv] LSTM 球隊狀態追蹤:")
    
    # 預設值
    home_form = {'form_score': 0.5, 'trend': 'stable', 'confidence': 'low'}
    away_form = {'form_score': 0.5, 'trend': 'stable', 'confidence': 'low'}
    
    # 檢查深度學習框架是否可用
    torch_available = False
    tf_available = False
    try:
        import torch
        torch_available = True
    except ImportError:
        pass
    
    try:
        import tensorflow as tf  # noqa: F401
        tf_available = True
    except ImportError:
        pass
    
    if not torch_available and not tf_available:
        print(f"      ⚠️ PyTorch 和 TensorFlow 都不可用，使用統計狀態追蹤")
    
    try:
        if torch_available or tf_available:
            lstm_model = TeamFormLSTM(sequence_length=10, use_attention=True, min_games=2)  # 改為 2 場
            # 使用歷史數據
            if hasattr(repo, 'df') and not repo.df.empty:
                valid_df = repo.df.dropna(subset=['home_team', 'away_team', 'home_goals', 'away_goals'])
                
                # 只使用有 xG 數據的行 (repo.df.columns 是小寫)
                if 'xg' in valid_df.columns:
                    valid_df = valid_df[valid_df['xg'].notna()]
                
                result_col = 'ftr' if 'ftr' in valid_df.columns else 'result'
                xg_col = 'xg' if 'xg' in valid_df.columns else 'home_xg'
                away_xg_col = 'xga' if 'xga' in valid_df.columns else 'away_xg'
                
                print(f"      [DEBUG] LSTM: 載入 {len(valid_df)} 場有效比賽")
                print(f"      [DEBUG] LSTM: result_col={result_col}, xG_cols={xg_col}/{away_xg_col}")
                
                # 修復：數據是按日期升序排列，用 tail() 取最近的數據
                recent_valid = valid_df.tail(300)
                print(f"      [DEBUG] LSTM: 使用最近 {len(recent_valid)} 場比賽")
                
                # Fuzzy matching 已經在上面定義，直接使用
                match_count = 0
                for _, row in recent_valid.iterrows():
                    try:
                        # 判斷主客場結果
                        result = str(row.get(result_col, 'D')).upper()
                        if result == 'W':
                            home_result, away_result = 'W', 'L'
                        elif result == 'L':
                            home_result, away_result = 'L', 'W'
                        else:
                            home_result, away_result = 'D', 'D'
                        
                        home_xg_val = float(row.get(xg_col, 1.5))
                        away_xg_val = float(row.get(away_xg_col, 1.0))
                        
                        lstm_model.add_match(row['home_team'], 
                                            goals_scored=int(row['home_goals']),
                                            goals_conceded=int(row['away_goals']),
                                            xg=home_xg_val,
                                            possession=50, shots_on_target=3,
                                            result=home_result, is_home=True)
                        lstm_model.add_match(row['away_team'],
                                            goals_scored=int(row['away_goals']),
                                            goals_conceded=int(row['home_goals']),
                                            xg=away_xg_val,
                                            possession=50, shots_on_target=3,
                                            result=away_result, is_home=False)
                        match_count += 1
                    except: continue
                
                print(f"      [DEBUG] LSTM: 已載入 {match_count} 場比賽數據")
                
                # 使用 fuzzy_match_team 進行匹配
                lstm_teams = set(list(valid_df['home_team'].unique()) + list(valid_df['away_team'].unique()))
                lstm_team_list = list(lstm_teams)
                
                lstm_home = fuzzy_match_team(api_home, lstm_team_list)
                lstm_away = fuzzy_match_team(api_away, lstm_team_list)
                
                print(f"      [FUZZY-LSTM] \"{api_home}\" -> \"{lstm_home}\"")
                print(f"      [FUZZY-LSTM] \"{api_away}\" -> \"{lstm_away}\"")
                
                home_form = lstm_model.predict_team_form(lstm_home)
                away_form = lstm_model.predict_team_form(lstm_away)
        
        # 如果 TensorFlow 不可用或 LSTM 失敗，使用基於統計的簡化狀態
        if not tf_available or home_form.get('form_score', 0) == 0.5:
            if hasattr(repo, 'df') and not repo.df.empty:
                tmp = repo.df.copy()
                tmp["hl"] = tmp["home_team"].astype(str).str.lower().str.strip()
                tmp["al"] = tmp["away_team"].astype(str).str.lower().str.strip()
                
                # 使用 fuzzy matched 名稱 (fallback)
                simple_teams = set(list(tmp["hl"].unique()) + list(tmp["al"].unique()))
                simple_home = fuzzy_match_team(api_home, list(simple_teams))
                simple_away = fuzzy_match_team(api_away, list(simple_teams))
                
                simple_home_l = simple_home.lower().strip()
                simple_away_l = simple_away.lower().strip()
                
                home_games = tmp[(tmp["hl"] == simple_home_l) | (tmp["al"] == simple_home_l)].tail(10)
                away_games = tmp[(tmp["hl"] == simple_away_l) | (tmp["al"] == simple_away_l)].tail(10)
                
                def calc_simple_form(games, team_l):
                    if games.empty:
                        return 0.5, 'stable'
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
                    
                    # 趨勢判斷
                    recent = games.tail(3)
                    older = games.head(len(games)-3) if len(games) > 3 else games.head(0)
                    r_pts = 0
                    o_pts = 0
                    for _, row in recent.iterrows():
                        if row['hl'] == team_l:
                            if row['home_goals'] > row['away_goals']: r_pts += 3
                            elif row['home_goals'] == row['away_goals']: r_pts += 1
                        else:
                            if row['away_goals'] > row['home_goals']: r_pts += 3
                            elif row['away_goals'] == row['home_goals']: r_pts += 1
                    for _, row in older.iterrows():
                        if row['hl'] == team_l:
                            if row['home_goals'] > row['away_goals']: o_pts += 3
                            elif row['home_goals'] == row['away_goals']: o_pts += 1
                        else:
                            if row['away_goals'] > row['home_goals']: o_pts += 3
                            elif row['away_goals'] == row['home_goals']: o_pts += 1
                    
                    r_avg = r_pts / max(len(recent), 1) if len(recent) > 0 else 1.5
                    o_avg = o_pts / max(len(older), 1) if len(older) > 0 else 1.5
                    
                    if r_avg > o_avg + 0.5: trend = 'improving'
                    elif r_avg < o_avg - 0.5: trend = 'declining'
                    else: trend = 'stable'
                    
                    return form_score, trend
                
                home_f, home_t = calc_simple_form(home_games, simple_home_l)
                away_f, away_t = calc_simple_form(away_games, simple_away_l)
                
                home_form = {'form_score': home_f, 'trend': home_t, 'confidence': 'medium'}
                away_form = {'form_score': away_f, 'trend': away_t, 'confidence': 'medium'}
        
        print(f"      {odds_home} 狀態: {home_form['form_score']:.2f} ({home_form['trend']})")
        print(f"      {odds_away} 狀態: {away_form['form_score']:.2f} ({away_form['trend']})")
        print(f"      信心度: {home_form['confidence']}/{away_form['confidence']}")
    except Exception as e:
        print(f"      ⚠️ 狀態追蹤失敗: {str(e)[:80]}")

    # 計算綜合勝率 (結合多個模型)
    avg_v3_prob = (nb_probs['home_win'] + mc_v3_probs['mc_home_win'] + elo_win_prob) / 3
    print(f"\n   📊 [v3] 綜合勝率: {avg_v3_prob:.1%}")

    math_results = {
        "dixon_coles": dc_probs,
        "monte_carlo": mc_probs,
    # [v3] 新增模型結果
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
    # [Advanced] 高級模型結果
        "exponential_xg": {
            "home": xg_forecast_home,
            "away": xg_forecast_away,
            "home_n": home_xg_adv.get('n_games', 0) if isinstance(home_xg_adv, dict) else 0,
            "away_n": away_xg_adv.get('n_games', 0) if isinstance(away_xg_adv, dict) else 0
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
            "home": {
                "form_score": home_form.get('form_score', 0.5),
                "trend": home_form.get('trend', 'stable'),
                "confidence": home_form.get('confidence', 'low')
            },
            "away": {
                "form_score": away_form.get('form_score', 0.5),
                "trend": away_form.get('trend', 'stable'),
                "confidence": away_form.get('confidence', 'low')
            }
        },
        # ==========
        "glicko": match_context.get("glicko", "No Data"),
        "lineup_prob": lineup_prob,
        "expected_goals": {"home": h_exp_adj, "away": a_exp_adj},
        "injury_impact": {
            "home": 0,
            "away": 0,
            "diff": 0,
            "disabled": True
        }
    }

    glicko = match_context.get("glicko", {})
    print(f"   [INFO] 傷停調整已停用")
    print(f"      {odds_home} {h_exp_adj:.2f} - {a_exp_adj:.2f} {odds_away}")
    print(f"   🏆 Glicko-2 勝率: {glicko.get('win_prob', 0):.1%}")
    print(f"   🎲 [MonteCarlo] 主: {mc_probs['mc_home_win']:.1%} | 大 2.5: {mc_probs['mc_over_2.5']:.1%}")

    # 4. 讀取全盤口賠率 (使用 API Key)
    print(f"\n📈 [2/4] 連線 API 讀取即時賠率...", flush=True)
    # 使用 The Odds API 標準化後的隊名
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

    # 5. Grok 搜尋
    print(f"\n🤖 [3/4] 請求 Grok 聯網搜尋市場情報...", flush=True)
    grok_input = odds_summary_text[:1500]
    grok_reaction = llm.search_and_analyze_market_reaction(f"{odds_home} vs {odds_away}", grok_input)
    print("\n--------- 🤖 Grok 市場觀點 ---------", flush=True)
    print(grok_reaction[:200] + "..." if len(grok_reaction) > 200 else grok_reaction, flush=True)

    # 6. ChatGPT 決策
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

    # 7. 資金計算
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
        
        # ========== [v3] 信心度 Kelly 資金管理 ==========
        print(f"\n   💰 [v3] 信心度 Kelly 資金管理:")
        try:
            # 嘗試使用 v3 信心度 Kelly
            kelly_v3 = ConfidenceKelly(
                base_fraction=0.75,  # 半Kelly
                min_edge=0.08,       # 最小優勢 8%
                initial_bankroll=settings.INITIAL_BANKROLL
            )
            
            # 獲取市場隱含概率
            market_prob = 1 / target_odds
            
            # 使用 v3 綜合勝率
            v3_prob = avg_v3_prob if 'avg_v3_prob' in dir() else prob
            
            kelly_result = kelly_v3.calculate(
                prob=v3_prob,
                odds=target_odds,
                confidence=0.7,  # 模型信心度
                model_uncertainty=0.1,
                market_prob=market_prob
            )
            
            print(f"      [信心度 Kelly]")
            print(f"         Kelly%: {kelly_result.kelly_pct:.2%}")
            print(f"         信心度調整: {kelly_result.confidence_adj:.2%}")
            print(f"         期望值: {kelly_result.ev:.3f}")
            print(f"         優勢: {kelly_result.edge:.3f}")
            print(f"         風險等級: {kelly_result.risk_level}")
            print(f"         建議投注: ${kelly_result.stake:.2f}")
            
            # 保存信心度 Kelly 結果
            kelly_v3_result = kelly_result.to_dict()
        except Exception as e:
            kelly_v3_result = stake_info
            print(f"      [信心度 Kelly 計算失敗: {e}]")
        
        # ========== [Advanced] RL 投注策略優化 ==========
        print(f"\n   🤖 [Adv] RL 投注策略:")
        try:
            # 計算邊緣
            model_prob = v3_prob if 'v3_prob' in dir() else prob
            implied_prob = 1 / target_odds
            edge = model_prob - implied_prob
            
            # 使用 LSTM 狀態數據
            home_form_score = home_form.get('form_score', 0.5) if isinstance(home_form, dict) else 0.5
            away_form_score = away_form.get('form_score', 0.5) if isinstance(away_form, dict) else 0.5
            
            # 初始化 RL agent
            rl_agent = BettingRLAgent(
                bankroll=settings.INITIAL_BANKROLL,
                learning_rate=0.1,
                discount_factor=0.95,
                exploration_rate=0.1
            )
            
            # 進行投注決策
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
            print(f"         投注比例: {rl_decision.get('bet_pct', 0):.2%}")
            print(f"         投注金額: ${rl_decision.get('bet_amount', 0):.2f}")
            print(f"         Kelly分數: {rl_decision.get('kelly_frac', 0):.3f}")
            
            # RL 建議
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