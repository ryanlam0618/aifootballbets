#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 足球分析系統 - Streamlit Web 界面
"""

import streamlit as st
import pandas as pd
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

# 頁面配置
st.set_page_config(
    page_title="AI 足球分析系統",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 標題
st.title("⚽ AI 足球分析系統 v6.0")
st.markdown("---")

# 側邊欄 - 聯賽選擇
with st.sidebar:
    st.header("📋 聯賽選擇")
    
    LEAGUE_OPTIONS = {
        "1": {"name": "Premier League (England)", "key": "soccer_epl"},
        "2": {"name": "La Liga (Spain)", "key": "soccer_spain_la_liga"},
        "3": {"name": "Bundesliga (Germany)", "key": "soccer_germany_bundesliga"},
        "4": {"name": "Serie A (Italy)", "key": "soccer_italy_serie_a"},
        "5": {"name": "Ligue 1 (France)", "key": "soccer_france_ligue_one"},
        "51": {"name": "J League (Japan)", "key": "soccer_japan_j_league"},
        "52": {"name": "K League 1 (South Korea)", "key": "soccer_korea_kleague1"},
        "54": {"name": "A-League (Australia)", "key": "soccer_australia_aleague"},
    }
    
    league_idx = st.selectbox(
        "選擇聯賽",
        options=list(LEAGUE_OPTIONS.keys()),
        format_func=lambda x: LEAGUE_OPTIONS[x]["name"]
    )
    
    selected_league = LEAGUE_OPTIONS[league_idx]
    st.info(f"已選擇: {selected_league['name']}")
    
    st.markdown("---")
    st.subheader("📊 系統狀態")
    
    # 檢查數據文件
    if os.path.exists('data/history_data.csv'):
        df = pd.read_csv('data/history_data.csv')
        st.success(f"✅ 歷史數據: {len(df):,} 條")
    else:
        st.error("❌ 歷史數據未找到")
    
    # 檢查模型文件
    if os.path.exists('data/xgb_model.json'):
        st.success("✅ XGBoost 模型已加載")
    else:
        st.warning("⚠️ XGBoost 模型未找到")

# 主內容區域
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("📝 比賽輸入")
    match_input = st.text_input(
        "輸入對戰組合",
        value="Liverpool vs Arsenal",
        help="格式: 主隊 vs 客隊"
    )

with col2:
    st.subheader("🔍 分析狀態")
    analyze_btn = st.button("開始分析", type="primary")

if analyze_btn and match_input:
    # 解析比賽
    if " vs " in match_input:
        parts = match_input.split(" vs ")
        home_team = parts[0].strip()
        away_team = parts[1].strip()
        
        # 載入模組
        try:
            from config import settings
            from src.data_modules import HistoryRepo, RealOddsFetcher
            from src.math_models import PoissonModel, DixonColesModel
            from src.math_models_v2 import MonteCarloSimulator as MCSim
            from src.injury_api import InjuryDataAggregator
            from src.lineup_api import LineupAggregator
        except ImportError as e:
            st.error(f"模組載入失敗: {e}")
            st.stop()
        
        # 初始化
        repo = HistoryRepo(settings.HISTORY_CSV_PATH)
        odds_fetcher = RealOddsFetcher()
        injury_aggregator = InjuryDataAggregator()
        lineup_aggregator = LineupAggregator()
        
        # ========== 獲取數據 ==========
        with st.spinner('正在獲取數據...'):
            
            # 1. 歷史數據
            match_context = repo.get_match_context(home_team, away_team, selected_league['name'])
            stats = match_context.get("stats", {})
            h2h_stats = match_context.get("h2h_stats", {})
            home_form = match_context.get("home_form", {})
            away_form = match_context.get("away_form", {})
            glicko = match_context.get("glicko", {})
            
            # 2. 傷停數據
            injury_report = injury_aggregator.get_match_injury_report(home_team, away_team)
            
            # 3. 陣容數據
            lineup = lineup_aggregator.get_lineup(home_team, away_team)
            
            # 4. 數學模型
            h_exp = stats.get("home_weighted_xg", 1.5)
            a_exp = stats.get("away_weighted_xg", 1.0)
            
            # 傷停影響
            injury_impact_diff = injury_report['impact_diff']
            injury_factor = 0.02
            h_exp_adj = h_exp * (1 - injury_impact_diff * injury_factor) if injury_impact_diff >= 0 else h_exp * (1 + abs(injury_impact_diff) * injury_factor)
            a_exp_adj = a_exp * (1 + injury_impact_diff * injury_factor) if injury_impact_diff >= 0 else a_exp * (1 - abs(injury_impact_diff) * injury_factor)
            
            # Dixon-Coles
            dc_model = DixonColesModel(h_exp_adj, a_exp_adj)
            dc_probs = dc_model.calculate_probabilities()
            
            # Monte Carlo
            mc_sim = MCSim(h_exp_adj, a_exp_adj)
            mc_probs = mc_sim.run_simulation()
        
        # ========== 顯示結果 ==========
        st.markdown("---")
        
        # 標題
        st.header(f"{home_team} vs {away_team}")
        st.caption(f"{selected_league['name']} • {match_context.get('stats', {}).get('league', 'Unknown League')}")
        
        # 三欄佈局
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            st.metric(
                "Dixon-Coles 主勝",
                f"{dc_probs['home_win']:.1%}",
                delta=f"{dc_probs['home_win'] - 0.33:.1%}" if dc_probs['home_win'] > 0.33 else None
            )
        
        with c2:
            st.metric(
                "Monte Carlo 主勝",
                f"{mc_probs['mc_home_win']:.1%}",
                delta=f"{mc_probs['mc_home_win'] - 0.33:.1%}" if mc_probs['mc_home_win'] > 0.33 else None
            )
        
        with c3:
            st.metric(
                "Glicko-2 勝率",
                f"{glicko.get('win_prob', 0):.1%}",
                delta_color="normal"
            )
        
        with c4:
            st.metric(
                "xG 預測",
                f"{h_exp_adj:.2f} - {a_exp_adj:.2f}",
                delta=f"{(h_exp_adj - a_exp_adj):.2f}"
            )
        
        # 詳細分析
        tab1, tab2, tab3, tab4 = st.tabs(["📊 對賽往績", "🏥 傷停數據", "👕 陣容分析", "📈 詳細數據"])
        
        with tab1:
            # Head-to-Head
            st.subheader("Head-to-Head 統計")
            
            if h2h_stats and h2h_stats.get('h2h_games', 0) > 0:
                col_h2h1, col_h2h2, col_h2h3 = st.columns(3)
                with col_h2h1:
                    st.metric(f"{home_team} 勝", h2h_stats.get('h2h_wins_home', 0))
                with col_h2h2:
                    st.metric("和局", h2h_stats.get('h2h_ways', 0))
                with col_h2h3:
                    st.metric(f"{away_team} 勝", h2h_stats.get('h2h_wins_away', 0))
                
                st.info(f"近 {h2h_stats.get('h2h_games', 0)} 場對賽平均進球: {h2h_stats.get('h2h_avg_goals', 0):.2f}")
                
                # 顯示最近對賽
                h2h_records = match_context.get('h2h', [])
                if h2h_records:
                    st.write("最近對賽:")
                    h2h_df = pd.DataFrame(h2h_records)
                    st.dataframe(h2h_df[['date', 'home_team', 'away_team', 'home_goals', 'away_goals']], hide_index=True)
            else:
                st.warning("沒有對賽往績數據")
            
            # 最近狀態
            st.subheader("最近狀態 (近 5 場)")
            col_f1, col_f2 = st.columns(2)
            
            with col_f1:
                st.write(f"**{home_team}**")
                st.metric("得分", f"{home_form.get('points', 0)} 分")
                st.write(f"🏆 {home_form.get('wins', 0)} 勝 | 🤝 {home_form.get('draws', 0)} 和 | ❌ {home_form.get('losses', 0)} 敗")
                st.write(f"⚽ 進球: {home_form.get('goals_for', 0)} | 失球: {home_form.get('goals_against', 0)}")
            
            with col_f2:
                st.write(f"**{away_team}**")
                st.metric("得分", f"{away_form.get('points', 0)} 分")
                st.write(f"🏆 {away_form.get('wins', 0)} 勝 | 🤝 {away_form.get('draws', 0)} 和 | ❌ {away_form.get('losses', 0)} 敗")
                st.write(f"⚽ 進球: {away_form.get('goals_for', 0)} | 失球: {away_form.get('goals_against', 0)}")
        
        with tab2:
            # 傷停數據
            st.subheader("傷停數據")
            
            home_inj = injury_report['home']
            away_inj = injury_report['away']
            
            col_inj1, col_inj2 = st.columns(2)
            
            with col_inj1:
                st.write(f"**{home_team}**")
                st.metric("傷病", f"{len(home_inj.get('injuries', []))} 人")
                st.metric("停賽", f"{len(home_inj.get('suspensions', []))} 人")
                st.metric("影響分數", f"{home_inj.get('total_impact', 0):.1f}")
                
                if home_inj.get('key_players'):
                    st.error(f"⚠️ 核心球員傷停: {', '.join(home_inj['key_players'])}")
            
            with col_inj2:
                st.write(f"**{away_team}**")
                st.metric("傷病", f"{len(away_inj.get('injuries', []))} 人")
                st.metric("停賽", f"{len(away_inj.get('suspensions', []))} 人")
                st.metric("影響分數", f"{away_inj.get('total_impact', 0):.1f}")
                
                if away_inj.get('key_players'):
                    st.error(f"⚠️ 核心球員傷停: {', '.join(away_inj['key_players'])}")
            
            if abs(injury_impact_diff) > 5:
                st.warning(f"⚠️ 傷停影響差異顯著: {injury_impact_diff:+.1f}")
        
        with tab3:
            # 陣容數據
            st.subheader("陣容分析")
            
            if lineup:
                st.success(f"數據來源: {lineup.get('source', 'unknown')}")
                
                home_lineup = lineup.get('home_team', {})
                away_lineup = lineup.get('away_team', {})
                
                col_lineup1, col_lineup2 = st.columns(2)
                
                with col_lineup1:
                    st.write(f"**{home_lineup.get('name', home_team)}**")
                    st.write(f"陣型: {home_lineup.get('formation', 'Unknown')}")
                    st.write(f"主教練: {home_lineup.get('coach', 'Unknown')}")
                    st.write(f"主力球員: {len(home_lineup.get('starters', []))} 人")
                    
                    starters = home_lineup.get('starters', [])[:5]
                    st.write("關鍵球員:")
                    for p in starters:
                        st.write(f"  • {p.get('name', 'Unknown')}")
                
                with col_lineup2:
                    st.write(f"**{away_lineup.get('name', away_team)}**")
                    st.write(f"陣型: {away_lineup.get('formation', 'Unknown')}")
                    st.write(f"主教練: {away_lineup.get('coach', 'Unknown')}")
                    st.write(f"主力球員: {len(away_lineup.get('starters', []))} 人")
                    
                    starters = away_lineup.get('starters', [])[:5]
                    st.write("關鍵球員:")
                    for p in starters:
                        st.write(f"  • {p.get('name', 'Unknown')}")
            else:
                st.warning("暫無陣容數據")
        
        with tab4:
            # 詳細數據
            st.subheader("xG 數據分析")
            
            col_xg1, col_xg2 = st.columns(2)
            
            with col_xg1:
                st.write(f"**{home_team}**")
                st.metric("xG 進球", f"{stats.get('home_xg_for', 0):.2f}")
                st.metric("xG 失球", f"{stats.get('home_xg_against', 0):.2f}")
                st.metric("xG 淨值", f"{stats.get('home_xg_for', 0) - stats.get('home_xg_against', 0):.2f}")
            
            with col_xg2:
                st.write(f"**{away_team}**")
                st.metric("xG 進球", f"{stats.get('away_xg_for', 0):.2f}")
                st.metric("xG 失球", f"{stats.get('away_xg_against', 0):.2f}")
                st.metric("xG 淨值", f"{stats.get('away_xg_for', 0) - stats.get('away_xg_against', 0):.2f}")
            
            # 詳細比分預測
            st.subheader("比分預測分布")
            
            score_probs = {}
            from scipy.stats import poisson
            for home_goals in range(0, 6):
                for away_goals in range(0, 6):
                    prob = poisson.pmf(home_goals, h_exp_adj) * poisson.pmf(away_goals, a_exp_adj)
                    if prob > 0.01:
                        score_probs[f"{home_goals}-{away_goals}"] = prob
            
            top_scores = sorted(score_probs.items(), key=lambda x: x[1], reverse=True)[:5]
            
            for score, prob in top_scores:
                st.write(f"{score}: {prob:.1%}")
        
        # 數學模型結果
        st.markdown("---")
        st.subheader("📊 數學模型結果")
        
        col_m1, col_m2, col_m3 = st.columns(3)
        
        with col_m1:
            st.write("**Dixon-Coles 模型**")
            st.write(f"主勝: {dc_probs['home_win']:.1%}")
            st.write(f"和局: {dc_probs['draw']:.1%}")
            st.write(f"客勝: {dc_probs['away_win']:.1%}")
        
        with col_m2:
            st.write("**Monte Carlo 模擬**")
            st.write(f"主勝: {mc_probs['mc_home_win']:.1%}")
            st.write(f"和局: {mc_probs['mc_draw']:.1%}")
            st.write(f"客勝: {mc_probs['mc_away_win']:.1%}")
            st.write(f"大 2.5: {mc_probs['mc_over_2.5']:.1%}")
        
        with col_m3:
            st.write("**Glicko-2 評分**")
            st.write(f"{home_team}: {glicko.get('home_rating', 'N/A')}")
            st.write(f"{away_team}: {glicko.get('away_rating', 'N/A')}")
            st.write(f"主隊勝率: {glicko.get('win_prob', 0):.1%}")
        
    else:
        st.error("輸入格式錯誤，請使用 '主隊 vs 客隊' 格式")

# 頁腳
st.markdown("---")
st.caption("⚽ AI 足球分析系統 v6.0 | 數據來源: 歷史數據 + API-Football + Understat")
