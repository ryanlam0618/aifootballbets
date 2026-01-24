import sys
import os
import json
import re
import difflib

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
    from TakeData.fotmob_lineup_scraper import FotMobLineupHarvester
except ImportError as e:
    print(f"❌ 模組載入失敗: {e}", flush=True)
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

            

            # 檢查是否與輸入的隊名匹配
            file_home_clean = clean_team_name(file_home)
            file_away_clean = clean_team_name(file_away)

            # 使用 difflib 計算相似度
            home_score = difflib.SequenceMatcher(None, home_clean.lower(), file_home_clean.lower()).ratio()
            away_score = difflib.SequenceMatcher(None, away_clean.lower(), file_away_clean.lower()).ratio()
            total_score = (home_score + away_score) / 2

            if total_score > 0.6:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)

    return None


def main():
    print("========================================", flush=True)
    print("⚽ AI 足球分析系統 v6.0 (API Integrated)", flush=True)
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

    # 初始化
    repo = HistoryRepo(settings.HISTORY_CSV_PATH)
    odds_fetcher = RealOddsFetcher()
    logger = ExcelLogger()

    # 2.5 讀取本地陣容檔案
    print(f"\n👕 [1.2/4] 正在讀取本地陣容資料...", flush=True)
    lineup_data = find_lineup_file(home, away)

    if lineup_data:
        print(f"   ✅ 成功讀取陣容: {lineup_data['home_team']['name']} vs {lineup_data['away_team']['name']}", flush=True)
        print(f"      主隊陣容: {len(lineup_data['home_team']['starters'])} 人", flush=True)
        print(f"      客隊陣容: {len(lineup_data['away_team']['starters'])} 人", flush=True)
    else:
        print(f"   ⚠️ 未找到本地陣容檔案，將跳過陣容分析", flush=True)

    # 3. 獲取數據 & 數學模型 (傳入 league_name 給歷史數據模組顯示用)
    print(f"\n🔍 [1/4] 執行 Glicko-2 回測與機器學習預測...", flush=True)
    match_context = repo.get_match_context(home, away, league_name)
    stats = match_context.get("stats", {})
    
    # 陣容分析
    print(f"👕 [1.5/4] 分析首發名單評分 (Lineup Rating)...", flush=True)
    lineup_prob = repo.get_lineup_prediction(home, away)
    if lineup_prob:
        print(f"   👥 基於首發球員評分的主勝率: {lineup_prob:.1%}")
    else:
        print("   ⚠️ 未找到首發名單 JSON，跳過。")

    # 數學運算
    h_exp = stats.get("home_weighted_xg", 1.2)
    a_exp = stats.get("away_weighted_xg", 1.0)
    
    dc_model = DixonColesModel(h_exp, a_exp)
    dc_probs = dc_model.calculate_probabilities()
    
    mc_sim = MCSim_v2(h_exp, a_exp)
    mc_probs = mc_sim.run_simulation()
    
    math_results = {
        "dixon_coles": dc_probs,
        "monte_carlo": mc_probs,
        "elo": match_context.get("elo", "No Data"),
        "glicko": match_context.get("glicko", "No Data"),
        "lineup_prob": lineup_prob,
        "expected_goals": {"home": h_exp, "away": a_exp}
    }
    
    glicko = match_context.get("glicko", {})
    print(f"   ℹ️ 進球期望值: {home} {h_exp:.2f} - {a_exp:.2f} {away}")
    print(f"   🏆 Glicko-2 勝率: {glicko.get('win_prob', 0):.1%}")
    print(f"   🎲 [MonteCarlo] 主: {mc_probs['mc_home_win']:.1%} | 大 2.5: {mc_probs['mc_over_2.5']:.1%}")

    # 4. 讀取全盤口賠率 (使用 API Key)
    print(f"\n📈 [2/4] 連線 API 讀取即時賠率...", flush=True)
    # 這裡傳入 league_key (例如 soccer_epl)
    all_markets = odds_fetcher.get_real_odds(league_key, home, away)
    
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
    grok_reaction = llm.search_and_analyze_market_reaction(f"{home} vs {away}", grok_input)
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
        
        print(f"   [{target_label}] 賠率 {target_odds}:")
        if stake_info["stake"] > 0:
            print(f"      >>> 建議下注: ${stake_info['stake']:.2f} (EV: {stake_info['ev']:.3f})")
            if input("\n💾 記錄注單到 Excel? (y/n): ").lower() == 'y':
                match_info = {"league": league_name, "home": home, "away": away}
                bet_info = {"market": rec_market, "selection": rec_selection, "odds": target_odds, "model_probability": prob}
                logger.log_bet(match_info, bet_info, stake_info)
                logger.show_stats()
        else:
            print(f"      >>> 不建議下注 (EV < 0)")

    input("\n執行完畢，請按 Enter 離開...")

if __name__ == "__main__":
    main()