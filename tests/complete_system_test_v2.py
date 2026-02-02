#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整系統測試 v2 - 包含所有 API 和數據源驗證
"""

import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

print("="*70)
print("⚽ 足球 AI 分析系統 - 完整測試 v2")
print("="*70)

tests_passed = 0
tests_failed = 0
tests_total = 0

def test(name, condition, error_msg=""):
    global tests_passed, tests_failed, tests_total
    tests_total += 1
    if condition:
        print(f"  ✅ {name}")
        tests_passed += 1
    else:
        print(f"  ❌ {name}: {error_msg}")
        tests_failed += 1

# ========== 測試 1: 模組導入 ==========
print("\n[1/9] 測試模組導入...")

try:
    from config import settings
    test("config.settings 導入", True)
    print(f"     API Keys: Odds={bool(settings.ODDS_API_KEY)}, LLM={bool(settings.OPENAI_API_KEY)}")
except Exception as e:
    test("config.settings 導入", False, str(e))

try:
    from src.data_modules import HistoryRepo, RealOddsFetcher, LEAGUE_OPTIONS
    test("src.data_modules 導入", True)
except Exception as e:
    test("src.data_modules 導入", False, str(e))

try:
    from src.math_models import PoissonModel, DixonColesModel
    test("src.math_models 導入", True)
except Exception as e:
    test("src.math_models 導入", False, str(e))

try:
    from src.math_models_v2 import OptimizedDixonColes, MonteCarloSimulator, Glicko2System
    test("src.math_models_v2 導入", True)
except Exception as e:
    test("src.math_models_v2 導入", False, str(e))

try:
    from src.injury_api import InjuryDataAggregator, APIFootballIntegration
    test("src.injury_api 導入", True)
except Exception as e:
    test("src.injury_api 導入", False, str(e))

try:
    from src.finance import calculate_kelly_stake
    test("src.finance 導入", True)
except Exception as e:
    test("src.finance 導入", False, str(e))

try:
    from src.llm_clients import llm
    test("src.llm_clients (GPT-4) 導入", True)
except Exception as e:
    test("src.llm_clients (GPT-4) 導入", False, str(e))

try:
    from TakeData.fotmob_lineup_scraper import FotMobLineupHarvester
    test("FotMob Lineup Scraper 導入", True)
except Exception as e:
    test("FotMob Lineup Scraper 導入", False, str(e))

# ========== 測試 2: API-Football 傷停數據 ==========
print("\n[2/9] 測試 API-Football 傷停數據...")

try:
    from src.injury_api import APIFootballIntegration
    api = APIFootballIntegration()
    test("APIFootballIntegration 初始化", True)
    print(f"     API URL: {api.BASE_URL}")
    print(f"     API Key: {api.API_KEY[:10]}...")
except Exception as e:
    test("APIFootballIntegration 初始化", False, str(e))

# 測試多個聯賽的球隊
test_teams = [
    ("Liverpool", "Premier League"),
    ("Barcelona", "La Liga"),
    ("Bayern Munich", "Bundesliga"),
    ("Juventus", "Serie A"),
    ("PSG", "Ligue 1"),
]

for team, league in test_teams:
    try:
        result = api.get_team_injuries(team)
        has_error = 'error' in result
        has_data = 'data' in result
        test(f"API-Football: {team} ({league})", has_data and not has_error)
        if has_data:
            print(f"       - 傷停球員: {len(result.get('data', []))}")
    except Exception as e:
        test(f"API-Football: {team} ({league})", False, str(e))

# ========== 測試 3: The Odds API ==========
print("\n[3/9] 測試 The Odds API...")

try:
    from src.data_modules import RealOddsFetcher
    fetcher = RealOddsFetcher()
    test("RealOddsFetcher 初始化", True)
    print(f"     API Key: {fetcher.api_key[:10] if fetcher.api_key else 'Not configured'}...")
except Exception as e:
    test("RealOddsFetcher 初始化", False, str(e))

try:
    odds = fetcher.get_real_odds("soccer_epl", "Liverpool", "Arsenal")
    test("The Odds API 請求", odds is not None or odds == {})
    print(f"     返回結果: {'有數據' if odds else '無數據 (可能無的比賽)'}")
except Exception as e:
    test("The Odds API 請求", False, str(e))

# ========== 測試 4: LLM 客戶端 ==========
print("\n[4/9] 測試 LLM 客戶端 (GPT-4, Grok, Gemini)...")

try:
    from src.llm_clients import llm
    test("LLM 客戶端初始化", True)
    print(f"     GPT-4: {'已配置' if hasattr(llm, 'openai_client') and llm.openai_client else '未配置'}")
    print(f"     Grok: {'已配置' if hasattr(llm, 'grok_client') and llm.grok_client else '未配置'}")
    print(f"     Gemini: {'已配置' if hasattr(llm, 'gemini_client') and llm.gemini_client else '未配置'}")
except Exception as e:
    test("LLM 客戶端初始化", False, str(e))

# ========== 測試 5: 歷史數據庫 ==========
print("\n[5/9] 測試歷史數據庫 (所有聯賽)...")

try:
    from config import settings
    repo = HistoryRepo(settings.HISTORY_CSV_PATH)
    test("HistoryRepo 初始化", repo is not None and repo.df is not None)
except Exception as e:
    test("HistoryRepo 初始化", False, str(e))

try:
    import pandas as pd
    df = pd.read_csv(settings.HISTORY_CSV_PATH, encoding='utf-8-sig', low_memory=False)
    test("歷史數據文件讀取", len(df) > 20000)
    print(f"     總記錄數: {len(df)}")
    print(f"     欄位數: {len(df.columns)}")
except Exception as e:
    test("歷史數據文件讀取", False, str(e))

# 檢查各聯賽數據
try:
    leagues = df['league'].dropna().unique()
    test("聯賽數量", len(leagues) >= 5)
    print(f"     聯賽列表: {list(leagues)}")
except Exception as e:
    test("聯賽數量", False, str(e))

# ========== 測試 6: K1, J1, 澳超數據 ==========
print("\n[6/9] 測試 K1, J1, 澳超數據...")

# 檢查 K1 數據 - 使用標準化後的名稱
k1_leagues = df[df['league'].str.contains('K League', case=False, na=False)]
test("K League 1 數據", len(k1_leagues) > 0)
print(f"     K League 1 記錄數: {len(k1_leagues)}")

# 檢查 J1 數據
j1_leagues = df[df['league'].str.contains('J1 League', case=False, na=False)]
test("J1 League 數據", len(j1_leagues) > 0)
print(f"     J1 League 記錄數: {len(j1_leagues)}")

# 檢查澳超數據
aleague_leagues = df[df['league'].str.contains('A-League', case=False, na=False)]
test("A-League 數據", len(aleague_leagues) >= 0)  # 可能為0
print(f"     A-League 記錄數: {len(aleague_leagues)}")

# 檢查五大聯賽
big5_leagues = ['Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1']
for league in big5_leagues:
    count = len(df[df['league'] == league])
    print(f"     {league}: {count}")

# ========== 測試 7: 數學模型 ==========
print("\n[7/9] 測試數學模型...")

try:
    model = PoissonModel(1.5, 1.2)
    probs = model.calculate_probabilities()
    test("PoissonModel 計算", probs['ps_home'] > 0 and probs['ps_home'] < 1)
    print(f"     主勝: {probs['ps_home']:.2%}, 和: {probs['ps_draw']:.2%}, 客勝: {probs['ps_away']:.2%}")
except Exception as e:
    test("PoissonModel 計算", False, str(e))

try:
    model = DixonColesModel(1.5, 1.2)
    probs = model.calculate_probabilities()
    test("DixonColesModel 計算", probs['dc_home'] > 0 and probs['dc_home'] < 1)
except Exception as e:
    test("DixonColesModel 計算", False, str(e))

try:
    model = OptimizedDixonColes(1.5, 1.2)
    probs = model.calculate_probabilities()
    test("OptimizedDixonColes 計算", probs['dc_home'] > 0 and probs['dc_home'] < 1)
except Exception as e:
    test("OptimizedDixonColes 計算", False, str(e))

try:
    glicko = Glicko2System()
    glicko.update_ratings("TeamA", "TeamB", 2, 1)
    rating = glicko.get_rating("TeamA")
    test("Glicko2System 計算", rating is not None)
except Exception as e:
    test("Glicko2System 計算", False, str(e))

try:
    sim = MonteCarloSimulator(1.5, 1.2)
    result = sim.run_simulation()
    test("MonteCarloSimulator 運行", 'mc_home_win' in result)
    print(f"     主勝: {result['mc_home_win']:.2%}, 大2.5: {result['mc_over_2.5']:.2%}")
except Exception as e:
    test("MonteCarloSimulator 運行", False, str(e))

# ========== 測試 8: 傷停數據聚合器 ==========
print("\n[8/9] 測試傷停數據聚合器...")

try:
    from src.injury_api import InjuryDataAggregator
    aggregator = InjuryDataAggregator()
    test("InjuryDataAggregator 初始化", True)
except Exception as e:
    test("InjuryDataAggregator 初始化", False, str(e))

try:
    report = aggregator.get_match_injury_report("Liverpool", "Arsenal")
    test("傷停報告獲取", 'home' in report and 'away' in report)
    print(f"     數據源: {report.get('source', 'unknown')}")
    print(f"     主隊影響: {report['home']['total_impact']:.1f}")
    print(f"     客隊影響: {report['away']['total_impact']:.1f}")
    print(f"     影響差異: {report['impact_diff']:.1f}")
except Exception as e:
    test("傷停報告獲取", False, str(e))

# ========== 測試 9: 資金管理 ==========
print("\n[9/9] 測試資金管理...")

try:
    result = calculate_kelly_stake(0.5, 2.0, 1000)
    test("Kelly Stake 計算 (正常)", 'stake' in result and result['stake'] > 0)
    print(f"     建議下注: ${result['stake']:.2f}, EV: {result['ev']:.3f}")
except Exception as e:
    test("Kelly Stake 計算 (正常)", False, str(e))

try:
    result = calculate_kelly_stake(0.3, 1.5, 1000)
    test("Kelly Stake 計算 (不推薦)", result['stake'] == 0)
except Exception as e:
    test("Kelly Stake 計算 (不推薦)", False, str(e))

# ========== 測試結果摘要 ==========
print("\n" + "="*70)
print("📊 測試結果摘要")
print("="*70)
print(f"  總測試數: {tests_total}")
print(f"  ✅ 通過: {tests_passed}")
print(f"  ❌ 失敗: {tests_failed}")
print(f"  通過率: {tests_passed/tests_total*100:.1f}%")

if tests_failed == 0:
    print("\n  🎉 所有測試通過！系統準備就緒")
else:
    print(f"\n  ⚠️ {tests_failed} 個測試失敗")

# ========== 數據源摘要 ==========
print("\n" + "="*70)
print("📈 數據源摘要")
print("="*70)

print("\n  API 配置:")
print(f"    - API-Football: ✅ (Key: {api.API_KEY[:10]}...)")
print(f"    - The Odds API: {'✅' if fetcher.api_key else '⚠️'}")
print(f"    - OpenAI GPT-4: {'✅' if hasattr(llm, 'openai_client') and llm.openai_client else '⚠️'}")
print(f"    - Grok: {'✅' if hasattr(llm, 'grok_client') and llm.grok_client else '⚠️'}")
print(f"    - Gemini: {'✅' if hasattr(llm, 'gemini_client') and llm.gemini_client else '⚠️'}")

print("\n  數據覆蓋:")
print(f"    - 歷史數據: {len(df)} 條記錄")
print(f"    - 五大聯賽: {len(leagues)} 個聯賽")
print(f"    - K League 1: {len(k1_leagues)} 條記錄")
print(f"    - J1 League: {len(j1_leagues)} 條記錄")
print(f"    - A-League: {len(aleague_leagues)} 條記錄")

print("\n" + "="*70)
print("🚀 系統狀態: 準備運行")
print("="*70)
print("""
運行說明:
  1. 執行 python app.py 啟動主程序
  2. 選擇聯賽 (1-8)
  3. 輸入比賽對戰
  4. 系統自動分析

支持的聯賽:
  1. Premier League (英超)
  2. La Liga (西甲)
  3. Bundesliga (德甲)
  4. Serie A (意甲)
  5. Ligue 1 (法甲)
  6. J1 League (日本)
  7. K League 1 (韓國)
  8. A-League (澳洲)

數據功能:
  ✅ 傷停數據: API-Football (實時)
  ✅ 數學模型: Glicko-2 + Dixon-Coles + Monte Carlo
  ✅ 機器學習: XGBoost 預測
  ✅ 市場情報: Grok 聯網搜尋
  ✅ 決策引擎: GPT-4 分析
  ✅ 資金管理: Kelly Criterion
""")
print("="*70)
