#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整系統測試 - 驗證所有模組
"""

import sys
import os
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

print("="*70)
print("足球 AI 投注系統 - 完整測試")
print("="*70)

# 1. 測試配置
print("\n[1/6] 測試配置...")
try:
    from config import settings
    print(f"  [OK] 歷史數據: {settings.HISTORY_CSV_PATH}")
    print(f"  [OK] 存在: {os.path.exists(settings.HISTORY_CSV_PATH)}")
except Exception as e:
    print(f"  [ERROR] {e}")

# 2. 測試數據模組
print("\n[2/6] 測試數據模組...")
try:
    from src.data_modules import HistoryRepo, LEAGUE_OPTIONS
    repo = HistoryRepo(settings.HISTORY_CSV_PATH)
    print(f"  [OK] HistoryRepo 初始化成功")
    print(f"  [OK] 數據記錄: {len(repo.df):,} 條")
    print(f"  [OK] 聯賽數: {len(LEAGUE_OPTIONS)}")
    
    # 測試球隊搜索
    teams = repo.get_all_teams()[:5]
    print(f"  [OK] 球隊樣本: {teams}")
except Exception as e:
    print(f"  [ERROR] {e}")
    import traceback
    traceback.print_exc()

# 3. 測試數學模型
print("\n[3/6] 測試數學模型...")
try:
    from src.math_models import PoissonModel, DixonColesModel
    from src.math_models_v2 import OptimizedDixonColes, MonteCarloSimulator as MCSim
    
    poisson = PoissonModel(1.5, 1.0)
    probs = poisson.calculate_probabilities()
    print(f"  [OK] Poisson: 主勝 {probs['home_win']:.1%}")
    
    dc = DixonColesModel(1.5, 1.0)
    dc_probs = dc.calculate_probabilities()
    print(f"  [OK] Dixon-Coles: 主勝 {dc_probs['home_win']:.1%}")
    
    mc = MCSim(1.5, 1.0)
    mc_probs = mc.run_simulation()
    print(f"  [OK] MonteCarlo: 主勝 {mc_probs['mc_home_win']:.1%}")
except Exception as e:
    print(f"  [ERROR] {e}")
    import traceback
    traceback.print_exc()

# 4. 測試傷停 API
print("\n[4/6] 測試傷停 API...")
try:
    from src.injury_api import InjuryDataAggregator
    
    aggregator = InjuryDataAggregator()
    report = aggregator.get_match_injury_report("Liverpool", "Arsenal")
    
    home = report['home']
    away = report['away']
    
    print(f"  Liverpool: {len(home['injuries'])} 傷, {len(home['suspensions'])} 停, 影響 {home['total_impact']:.1f}")
    print(f"  Arsenal: {len(away['injuries'])} 傷, {len(away['suspensions'])} 停, 影響 {away['total_impact']:.1f}")
    print(f"  [OK] 傷停 API 正常")
except Exception as e:
    print(f"  [ERROR] {e}")

# 5. 測試陣容 API
print("\n[5/6] 測試陣容 API...")
try:
    from src.lineup_api import LineupAggregator
    
    aggregator = LineupAggregator()
    # 先測試 API-Football
    lineup = aggregator.api_football.get_lineup("Liverpool", "Arsenal")
    
    if lineup:
        print(f"  [OK] API-Football 陣容成功: {lineup['source']}")
        print(f"      {lineup['home_team']['name']}: {len(lineup['home_team']['starters'])} 人")
        print(f"      {lineup['away_team']['name']}: {len(lineup['away_team']['starters'])} 人")
    else:
        print(f"  [WARN] API-Football 失敗，需要手動輸入 FotMob ID")
except Exception as e:
    print(f"  [ERROR] {e}")

# 6. 測試 LLM 客戶端
print("\n[6/6] 測試 LLM 客戶端...")
try:
    from src.llm_clients import llm
    
    # 測試 API 連接
    test_result = llm.test_api_connection()
    if test_result['status'] == 'success':
        print(f"  [OK] LLM API: {test_result['provider']}")
    else:
        print(f"  [WARN] LLM API: {test_result.get('error', 'Unknown error')}")
except Exception as e:
    print(f"  [ERROR] {e}")

print("\n" + "="*70)
print("測試完成!")
print("="*70)
