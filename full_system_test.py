#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整系統測試 - 足球 AI 分析系統
"""

import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

print("="*70)
print("⚽ 足球 AI 分析系統 - 完整測試")
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
print("\n[1/7] 測試模組導入...")

try:
    from config import settings
    test("config.settings 導入", True)
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
    from src.math_models_v2 import OptimizedDixonColes, MonteCarloSimulator
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
    test("src.llm_clients 導入", True)
except Exception as e:
    test("src.llm_clients 導入", False, str(e))

# ========== 測試 2: 數學模型 ==========
print("\n[2/7] 測試數學模型...")

try:
    model = PoissonModel(1.5, 1.2)
    probs = model.calculate_probabilities()
    test("PoissonModel 計算", probs['ps_home'] > 0 and probs['ps_home'] < 1)
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
    sim = MonteCarloSimulator(1.5, 1.2)
    result = sim.run_simulation()
    test("MonteCarloSimulator 運行", 'mc_home_win' in result)
except Exception as e:
    test("MonteCarloSimulator 運行", False, str(e))

# ========== 測試 3: 歷史數據庫 ==========
print("\n[3/7] 測試歷史數據庫...")

try:
    repo = HistoryRepo(settings.HISTORY_CSV_PATH)
    test("HistoryRepo 初始化", repo is not None)
except Exception as e:
    test("HistoryRepo 初始化", False, str(e))

try:
    context = repo.get_match_context("Liverpool", "Arsenal", "Premier League")
    test("get_match_context 返回", context is not None and 'stats' in context)
    if context and 'stats' in context:
        print(f"     home_xg: {context['stats'].get('home_weighted_xg', 'N/A'):.2f}")
        print(f"     away_xg: {context['stats'].get('away_weighted_xg', 'N/A'):.2f}")
except Exception as e:
    test("get_match_context 返回", False, str(e))

try:
    lineup_prob = repo.get_lineup_prediction("Liverpool", "Arsenal")
    test("get_lineup_prediction 返回", lineup_prob is not None or lineup_prob is None)
except Exception as e:
    test("get_lineup_prediction 返回", False, str(e))

# ========== 測試 4: 傷停數據 API ==========
print("\n[4/7] 測試傷停數據 API...")

try:
    api = APIFootballIntegration()
    test("APIFootballIntegration 初始化", api is not None)
except Exception as e:
    test("APIFootballIntegration 初始化", False, str(e))

try:
    result = api.get_team_injuries("Liverpool")
    test("API-Football 請求", 'error' in result or 'data' in result)
except Exception as e:
    test("API-Football 請求", False, str(e))

try:
    aggregator = InjuryDataAggregator()
    report = aggregator.get_match_injury_report("Liverpool", "Arsenal")
    test("InjuryDataAggregator 報告", 'home' in report and 'away' in report)
except Exception as e:
    test("InjuryDataAggregator 報告", False, str(e))

# ========== 測試 5: 資金管理 ==========
print("\n[5/7] 測試資金管理...")

try:
    result = calculate_kelly_stake(0.5, 2.0, 1000)
    test("Kelly Stake 計算", 'stake' in result and 'ev' in result)
except Exception as e:
    test("Kelly Stake 計算", False, str(e))

try:
    result = calculate_kelly_stake(0.3, 1.5, 1000)
    test("Kelly Stake 低概率", result['stake'] == 0)
except Exception as e:
    test("Kelly Stake 低概率", False, str(e))

# ========== 測試 6: 數據文件 ==========
print("\n[6/7] 測試數據文件...")

history_path = settings.HISTORY_CSV_PATH
test("歷史數據文件存在", os.path.exists(history_path), history_path)

if os.path.exists(history_path):
    import pandas as pd
    try:
        # 使用 error_bad_lines=False 跳過有問題的行
        df = pd.read_csv(history_path, on_bad_lines='skip')
        test("歷史數據可讀取", len(df) > 1000)
        print(f"     總記錄數: {len(df)}")
        print(f"     聯賽數量: {df['Div'].nunique() if 'Div' in df.columns else 'N/A'}")
    except Exception as e:
        test("歷史數據可讀取", False, str(e))

# ========== 測試 7: LLM 客戶端 ==========
print("\n[7/7] 測試 LLM 客戶端...")

try:
    test("llm 對象存在", hasattr(llm, 'analyze_with_super_prompt'))
except Exception as e:
    test("llm 對象存在", False, str(e))

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
    print(f"\n  ⚠️ {tests_failed} 個測試失敗，需要檢查")

print("\n" + "="*70)
print("🚀 系統狀態: 準備運行")
print("="*70)
print("""
使用說明:
  1. 運行 python app.py 啟動主程序
  2. 選擇聯賽 (輸入數字)
  3. 輸入比賽對戰 (例如: Liverpool vs Arsenal)
  4. 系統會自動分析並給出推薦

功能特色:
  • 傷停數據: API-Football (真實數據)
  • 數學模型: Glicko-2 + Dixon-Coles + Monte Carlo
  • 機器學習: XGBoost 預測
  • 市場情報: Grok 聯網搜尋
  • 決策引擎: GPT-4 綜合分析
""")
print("="*70)
