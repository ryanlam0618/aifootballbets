import sys
import os
import json
import re
import difflib

# 強制設定輸出編碼，避免 Windows 下中文亂碼
sys.stdout.reconfigure(encoding='utf-8')

try:
    from config import settings
    from data_modules import HistoryRepo, RealOddsFetcher, OddsPoint
    from llm_clients import llm
    from finance import calculate_kelly_stake, ExcelLogger
    # 引入多個數學模型
    from math_models import PoissonModel, MonteCarloSimulator, DixonColesModel
    # 引入新模型 v2
    from math_models_v2 import OptimizedDixonColes, MonteCarloSimulator as MCSim_v2
except ImportError as e:
    print(f"❌ 模組載入失敗: {e}", flush=True)
    sys.exit(1)

def main():
    print("========================================", flush=True)
    print("⚽ AI 足球分析系統 v5.2 (Fix Input)", flush=True)
    print("========================================", flush=True)

    # 1. 使用者輸入
    match_input = input("\n👉 請輸入比賽對戰組合 (Enter 預設 Bournemouth vs Tottenham): ").strip()
    if not match_input: match_input = "Bournemouth vs Tottenham"

    try:
        # 加強分割邏輯，處理大小寫 "vs", "Vs", "VS", " v " 等
        if re.search(r"\s+vs\.?\s+", match_input, re.IGNORECASE) or " v " in match_input:
            parts = re.split(r"\s+vs\.?\s+|\s+v\s+", match_input, flags=re.IGNORECASE)
            if len(parts) >= 2:
                home, away = parts[0].strip(), parts[1].strip()
            else:
                print("⚠️ 格式錯誤，無法識別主客隊，請使用 '主隊 vs 客隊' 格式")
                return
        else: 
            print("⚠️ 格式錯誤，請使用 '主隊 vs 客隊'")
            return
    except ValueError: return

    league = input("請輸入聯賽 (預設 Premier League): ").strip() or "Premier League"

    # 初始化各模組
    repo = HistoryRepo(settings.HISTORY_CSV_PATH)
    odds_fetcher = RealOddsFetcher()
    logger = ExcelLogger()

    # 2. 獲取數據 & 執行數學模型
    print(f"\n🔍 [1/4] 執行 Glicko-2 回測與機器學習預測...", flush=True)
    match_context = repo.get_match_context(home, away, league)
    stats = match_context.get("stats", {})
    
    # 執行陣容分析 (Lineup Model)
    print(f"👕 [1.5/4] 分析首發名單評分 (Lineup Rating)...", flush=True)
    lineup_prob = repo.get_lineup_prediction(home, away)
    if lineup_prob:
        print(f"   👥 基於首發球員評分的主勝率: {lineup_prob:.1%}")
    else:
        print("   ⚠️ 未找到首發名單 JSON，跳過球員級別分析。")

    # 數學模型運算
    h_exp = stats.get("home_weighted_xg", 1.2)
    a_exp = stats.get("away_weighted_xg", 1.0)
    
    # (B) Dixon-Coles 模型
    dc_model = DixonColesModel(h_exp, a_exp)
    dc_probs = dc_model.calculate_probabilities()
    
    # (C) 蒙地卡羅模擬
    mc_sim = MCSim_v2(h_exp, a_exp)
    mc_probs = mc_sim.run_simulation()
    
    # 打包數學結果給 AI
    math_results = {
        "dixon_coles": dc_probs,
        "monte_carlo": mc_probs,
        "elo": match_context.get("elo", "No Data"),
        "glicko": match_context.get("glicko", "No Data"),
        "lineup_prob": lineup_prob,
        "expected_goals": {"home": h_exp, "away": a_exp}
    }
    
    # 顯示部分數學指標
    glicko = match_context.get("glicko", {})
    print(f"   ℹ️ 進球期望值: {home} {h_exp:.2f} - {a_exp:.2f} {away}")
    print(f"   🏆 Glicko-2 勝率: {glicko.get('win_prob', 0):.1%}")
    print(f"   🎲 [MonteCarlo] 主: {mc_probs['mc_home_win']:.1%} | 大 2.5: {mc_probs['mc_over_2.5']:.1%}")

    # 3. 讀取全盤口賠率
    print(f"\n📈 [2/4] 讀取全盤口即時賠率...", flush=True)
    all_markets = odds_fetcher.get_real_odds(league, home, away)
    
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

    # 4. Grok 搜尋 (情報獲取)
    print(f"\n🤖 [3/4] 請求 Grok 聯網搜尋市場情報...", flush=True)
    grok_input = odds_summary_text[:1500]
    grok_reaction = llm.search_and_analyze_market_reaction(f"{home} vs {away}", grok_input)
    
    print("\n--------- 🤖 Grok 市場觀點 ---------", flush=True)
    print(grok_reaction  + "..." if len(grok_reaction) > 200 else grok_reaction, flush=True)

    # 5. ChatGPT 決策 (決策中樞)
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

    # 6. 資金計算 (智能匹配升級版)
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
                        "market": m_name,
                        "selection": s_name,
                        "odds": stats['max'][-1].decimal_odds,
                        "key_str": f"{m_name} {s_name}".lower()
                    })
        
        target_str = f"{rec_market} {rec_selection}".lower()
        # 修正 Regex: 處理可能沒有數字的情況
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
            if str(rec_selection).lower() in cand['selection'].lower():
                score += 0.2
            
            if score > highest_score:
                highest_score = score
                best_match = cand

        if best_match and highest_score > 0.6:
            target_odds = best_match['odds']
            target_label = f"{best_match['market']} - {best_match['selection']} (Max)"
            print(f"   ✅ 自動匹配賠率: {target_label} @ {target_odds}")
        else:
            print(f"   ⚠️ 自動匹配失敗 (最高相似度: {highest_score:.2f})")
            print(f"      AI 推薦: {rec_market} {rec_selection}")

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
                match_info = {"league": league, "home": home, "away": away}
                bet_info = {"market": rec_market, "selection": rec_selection, "odds": target_odds, "model_probability": prob}
                logger.log_bet(match_info, bet_info, stake_info)
                logger.show_stats()
        else:
            print(f"      >>> 不建議下注 (EV < 0)")

    input("\n執行完畢，請按 Enter 離開...")

if __name__ == "__main__":
    main()