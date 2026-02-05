#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 足球分析系統 v7.0 (Enhanced with Math Models v3)
"""

import sys
import os
import json
import re
import pickle
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

try:
    from config import settings
    from src.data_modules import HistoryRepo, RealOddsFetcher, LEAGUE_OPTIONS
    from src.llm_clients import llm
    from src.finance import ExcelLogger
    from src.math_models_v3 import (
        NegativeBinomialModel, OptimizedNegativeBinomialDC,
        DynamicKEloSystem, DynamicGlicko2System,
        MonteCarloSimulatorV3, ConfidenceKelly
    )
    from src.injury_api import InjuryDataAggregator
except ImportError as e:
    print(f"模組載入失敗: {e}")
    sys.exit(1)

def find_lineup_file(home, away, folder="data"):
    import glob
    def clean(name):
        import unicodedata, re
        name = unicodedata.normalize('NFKD', name)
        return re.sub(r'[^a-zA-Z0-9\s]', '', name).strip().replace(" ", "_")
    hc, ac = clean(home), clean(away)
    for pattern in [f"{folder}/lineup/lineup_{hc}_vs_{ac}.json",
                    f"{folder}/lineup/lineup_{ac}_vs_{hc}.json"]:
        matches = glob.glob(pattern)
        if matches:
            with open(matches[0], 'r', encoding='utf-8') as f:
                return json.load(f)
    return None

def convert_to_native(obj):
    """將 numpy/Python 類型轉換為可序列化的類型"""
    if isinstance(obj, dict):
        return {k: convert_to_native(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_native(i) for i in obj]
    elif isinstance(obj, (np.integer, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj

def main():
    print("="*70)
    print("AI 足球分析系統 v7.0 (Enhanced v3)")
    print("="*70)
    
    print("\n📋 選擇聯賽:")
    for k in list(LEAGUE_OPTIONS.keys())[:10]:
        print(f"   [{k}] {LEAGUE_OPTIONS[k]['name']}")
    
    idx = input("👉 選擇: ").strip() or "1"
    if idx not in LEAGUE_OPTIONS: idx = "1"
    league = LEAGUE_OPTIONS[idx]
    
    match_input = input("\n👉 比賽 (主隊 vs 客隊): ").strip() or "Bournemouth vs Tottenham"
    parts = re.split(r'\s+vs\.?\s+|\s+v\s+', match_input, flags=re.IGNORECASE)
    if len(parts) < 2: print("⚠️ 格式錯誤"); return
    home, away = parts[0].strip(), parts[1].strip()
    
    print(f"\n🔍 分析: {home} vs {away}")
    
    repo = HistoryRepo(settings.HISTORY_CSV_PATH)
    odds_fetcher = RealOddsFetcher()
    logger = ExcelLogger()
    
    # 傷停數據
    print(f"\n[1/5] 傷停數據...")
    injury = InjuryDataAggregator().get_match_injury_report(home, away)
    inj_diff = injury['impact_diff']
    print(f"   {home}: 傷停 {injury['home']['total_impact']:.0f}")
    print(f"   {away}: 傷停 {injury['away']['total_impact']:.0f}")
    
    # 陣容
    print(f"\n[2/5] 陣容數據...")
    lineup = find_lineup_file(home, away)
    print(f"   {'✅ 找到' if lineup else '⚠️ 未找到'}")
    
    # 數學模型
    print(f"\n[3/5] 數學模型 v3...")
    ctx = repo.get_match_context(home, away, league['name'])
    stats = ctx.get("stats", {})
    
    h_exp = stats.get("home_weighted_xg", 1.3) * (1 - inj_diff * 0.02)
    a_exp = stats.get("away_weighted_xg", 1.1) * (1 + inj_diff * 0.02)
    h_exp, a_exp = max(0.5, min(3.5, h_exp)), max(0.5, min(3.5, a_exp))
    
    print(f"   xG調整: {home} {h_exp:.2f} - {a_exp:.2f} {away}")
    
    # 負二項分布
    print(f"\n   🎯 負二項分布:")
    nb = NegativeBinomialModel(h_exp, a_exp)
    nb_probs = nb.calculate_probabilities()
    print(f"      主勝: {nb_probs['home_win']:.1%} | 和: {nb_probs['draw']:.1%} | 客勝: {nb_probs['away_win']:.1%}")
    print(f"      離散參數: {nb_probs['dispersion']:.2f}")
    
    # 蒙地卡羅 V3 (使用 Gamma-Poisson 混合物，模擬過離散)
    print(f"\n   🎲 蒙地卡羅 V3:")
    mc = MonteCarloSimulatorV3(h_exp, a_exp, iterations=10000, use_nbinom=True, dispersion=1.5)
    mc_res = mc.run_simulation()
    print(f"      主勝: {mc_res['mc_home_win']:.1%} | 大2.5: {mc_res['mc_over_2.5']:.1%}")
    print(f"      期望進球: {mc_res['expected_goals']['home']:.2f} - {mc_res['expected_goals']['away']:.2f}")
    
    # 動態K Elo
    print(f"\n   📈 動態K Elo:")
    elo = DynamicKEloSystem()
    try:
        for _, r in repo.df.dropna(subset=['home_goals']).tail(100).iterrows():
            try:
                elo.update_ratings(r['home_team'], r['away_team'], int(r['home_goals']), int(r['away_goals']))
            except: pass
    except: pass
    elo_prob = elo.expected_win_prob(home, away)
    print(f"      {home} 評分: {elo.get_rating(home):.0f} | {away} 評分: {elo.get_rating(away):.0f}")
    print(f"      Elo勝率: {elo_prob:.1%}")
    
    # 綜合勝率
    avg_prob = (nb_probs['home_win'] + mc_res['mc_home_win'] + elo_prob) / 3
    print(f"\n   📊 綜合勝率: {avg_prob:.1%}")
    
    # 準備數學結果 (轉換為可序列化格式)
    math_results_clean = {
        "negative_binomial": {
            "home_win": float(nb_probs['home_win']),
            "draw": float(nb_probs['draw']),
            "away_win": float(nb_probs['away_win']),
            "dispersion": float(nb_probs.get('dispersion', 1.5)),
            "model": "NegativeBinomial"
        },
        "monte_carlo": {
            "home_win": float(mc_res['mc_home_win']),
            "draw": float(mc_res['mc_draw']),
            "away_win": float(mc_res['mc_away_win']),
            "over_2_5": float(mc_res['mc_over_2.5']),
            "expected_goals_home": float(mc_res['expected_goals']['home']),
            "expected_goals_away": float(mc_res['expected_goals']['away']),
            "model": "MonteCarlo_NegBinomial"
        },
        "elo_system": {
            "home_rating": float(elo.get_rating(home)),
            "away_rating": float(elo.get_rating(away)),
            "home_win_prob": float(elo_prob),
            "model": "DynamicK_Elo"
        },
        "expected_goals": {"home": float(h_exp), "away": float(a_exp)},
        "injury_impact": {
            "home": float(injury['home']['total_impact']),
            "away": float(injury['away']['total_impact']),
            "diff": float(inj_diff)
        }
    }
    
    # 賠率
    print(f"\n[4/5] 即時賠率...")
    markets = odds_fetcher.get_real_odds(league['key'], home, away)
    odds_text = ""
    if markets:
        print(f"   ✅ {len(markets)} 市場")
        for m, sels in markets.items():
            for sel, st in sels.items():
                if st['avg']:
                    o = st['avg'][-1].decimal_odds
                    odds_text += f"{m} {sel}->{o} "
    else:
        print("   ⚠️ 無數據")
    
    # LLM 分析
    print(f"\n[5/5] LLM分析...")
    rec = llm.analyze_with_super_prompt(ctx, {"full_market_odds": odds_text[:1500]}, math_results_clean).get("recommendation", {})
    
    print("\n💡 推薦:", rec.get('market', 'N/A'), rec.get('selection', 'N/A'))
    print("理由:", rec.get('reasoning', 'N/A')[:200])
    
    # Kelly
    print(f"\n💰 信心度 Kelly v3...")
    kelly = ConfidenceKelly(base_fraction=0.5, min_edge=0.08, initial_bankroll=settings.INITIAL_BANKROLL)
    
    target_odds = None
    if markets:
        for sels in markets.values():
            for st in sels.values():
                if st['avg']:
                    target_odds = st['avg'][-1].decimal_odds
                    break
    
    if target_odds:
        res = kelly.calculate(avg_prob, target_odds, confidence=0.7, market_prob=1/target_odds)
        print(f"   Kelly%: {res.kelly_pct:.2%} | EV: {res.ev:.3f} | 優勢: {res.edge:.3f}")
        print(f"   風險: {res.risk_level} | 建議投注: ${res.stake:.2f}")
        
        if res.stake > 0 and input("\n記錄到Excel? (y/n): ").lower() == 'y':
            logger.log_bet({"league": league['name'], "home": home, "away": away},
                          {"market": rec.get('market',''), "selection": rec.get('selection',''),
                           "odds": target_odds, "model_probability": avg_prob},
                          res.to_dict())
            logger.show_stats()
    
    # 診斷
    print("\n📊 模型診斷 v3:")
    print(f"   負二項: alpha={nb_probs.get('dispersion',1.5):.2f}")
    print(f"   蒙地卡羅: 10,000次, 負二項分布")
    print(f"   Elo: 動態K, 對手調整, 意外因子")
    
    input("\n完成，按Enter離開...")

if __name__ == "__main__":
    main()
