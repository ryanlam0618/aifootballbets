import pandas as pd
import numpy as np
import os
import random
import ast
import json
import pickle
import difflib
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from config import settings

# ⚠️ 注意：頂層不要匯入 math_models

# --- 1. 歷史數據儲存庫 ---
class HistoryRepo:
    def __init__(self, csv_path: str):
        self.df = None
        self.ranking_system = None
        self.lineup_model_class = None
        
        # 延遲匯入 math_models_v2
        try:
            from math_models_v2 import Glicko2System, LineupModel
            self.ranking_system = Glicko2System() 
            self.lineup_model_class = LineupModel
        except ImportError:
            print("⚠️ Warning: math_models_v2 not found. Trying v1...")
            try:
                from math_models import EloSystem
                self.ranking_system = EloSystem()
            except: pass

        self.ml_model = None
        try:
            model_path = os.path.join(os.path.dirname(__file__), "xgb_model.pkl")
            if os.path.exists(model_path):
                with open(model_path, "rb") as f: self.ml_model = pickle.load(f)
        except: pass
        
        try:
            if not os.path.exists(csv_path):
                self._create_mock_data()
                return
            try:
                self.df = pd.read_csv(csv_path, encoding='utf-8-sig', low_memory=False)
            except UnicodeDecodeError:
                self.df = pd.read_csv(csv_path, encoding='latin-1', low_memory=False)
            
            self.df.columns = self.df.columns.str.strip().str.lower().str.replace('\ufeff', '')
            
            rename_dict = {} # (省略詳細 mapping 以節省空間，保持原樣)
            column_mapping = {
                "date": ["date", "match_date", "time", "日期"],
                "league": ["league", "div", "division", "聯賽"],
                "home_team": ["home_team", "hometeam", "home", "主隊"],
                "away_team": ["away_team", "awayteam", "away", "客隊"],
                "home_goals": ["home_goals", "fthg", "h_score", "hg", "主隊進球"],
                "away_goals": ["away_goals", "ftag", "a_score", "ag", "客隊進球"],
            }
            for standard_col, possible_names in column_mapping.items():
                for col in self.df.columns:
                    if col in possible_names:
                        rename_dict[col] = standard_col
                        break
            self.df.rename(columns=rename_dict, inplace=True)
            self.df["date"] = pd.to_datetime(self.df["date"], dayfirst=True, errors='coerce')
            self.df = self.df.dropna(subset=["date"]).sort_values("date")

            if self.ranking_system: self._calculate_rankings()

        except Exception as e:
            print(f"⚠️ 讀取 CSV 錯誤 ({e})")
            self._create_mock_data()

    def _calculate_rankings(self):
        valid_rows = self.df.dropna(subset=['home_goals', 'away_goals', 'home_team', 'away_team'])
        for _, row in valid_rows.iterrows():
            try:
                self.ranking_system.update_ratings(
                    row['home_team'], row['away_team'], int(row['home_goals']), int(row['away_goals'])
                )
            except: continue

    def _create_mock_data(self):
        self.df = pd.DataFrame()

    def _find_lineup_file(self, home_team, away_team):
        data_dir = os.path.dirname(settings.HISTORY_CSV_PATH)
        if not os.path.exists(data_dir): return None
        
        candidates = [f for f in os.listdir(data_dir) if f.endswith(".json") and "lineup" in f.lower()]
        best_score = 0.0
        best_candidate = None
        
        h_input = home_team.lower().replace(".", "").strip()
        a_input = away_team.lower().replace(".", "").strip()
        
        for f in candidates:
            clean_name = f.lower().replace("lineup_", "").replace(".json", "").replace("_", " ")
            if " vs " in clean_name:
                parts = clean_name.split(" vs ")
                score = (difflib.SequenceMatcher(None, h_input, parts[0]).ratio() + 
                         difflib.SequenceMatcher(None, a_input, parts[1]).ratio()) / 2
            else:
                score = difflib.SequenceMatcher(None, f"{h_input} {a_input}", clean_name).ratio()
            
            if score > best_score:
                best_score = score
                best_candidate = f
        
        return os.path.join(data_dir, best_candidate) if best_candidate and best_score > 0.5 else None

    # ✅ 新增：獲取純數據 (給 GPT 用)
    def get_lineup_data(self, home_team, away_team):
        target_file = self._find_lineup_file(home_team, away_team)
        if target_file:
            try:
                with open(target_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {}

    # 獲取預測值 (給 app.py 顯示用)
    def get_lineup_prediction(self, home_team, away_team):
        if not self.lineup_model_class: return None
        data = self.get_lineup_data(home_team, away_team)
        if data:
            print(f"   📄 成功載入陣容數據 (用於 AI 分析)")
            return self.lineup_model_class(data).predict_win_prob()
        return None

    def _fuzzy_match_team(self, input_name: str, all_teams: List[str]) -> str:
        matches = difflib.get_close_matches(input_name, all_teams, n=1, cutoff=0.6)
        return matches[0] if matches else input_name

    def get_match_context(self, home: str, away: str, league: str) -> Dict:
        if self.df is None or self.df.empty: self._create_mock_data()
        
        all_teams = list(set(self.df['home_team'].unique().astype(str).tolist() + self.df['away_team'].unique().astype(str).tolist()))
        real_home = self._fuzzy_match_team(home, all_teams)
        real_away = self._fuzzy_match_team(away, all_teams)
        
        if real_home != home or real_away != away:
            print(f"   🔄 隊名校正: {home} -> {real_home}, {away} -> {real_away}")

        home_s, away_s = real_home.lower().strip(), real_away.lower().strip()
        
        # Ranking Info
        ranking_info = {}
        if self.ranking_system:
            try:
                rh = self.ranking_system.get_rating(real_home)
                ra = self.ranking_system.get_rating(real_away)
                val_h = rh['rating'] if isinstance(rh, dict) else rh
                val_a = ra['rating'] if isinstance(ra, dict) else ra
                prob = self.ranking_system.expected_win_prob(real_home, real_away)
                ranking_info = {"home_rating": round(val_h, 0), "away_rating": round(val_a, 0), "win_prob": round(prob, 2)}
            except: pass

        # Recent Stats
        tmp = self.df.copy()
        tmp["hl"] = tmp["home_team"].astype(str).str.lower().str.strip()
        tmp["al"] = tmp["away_team"].astype(str).str.lower().str.strip()
        
        h_games = tmp[(tmp["hl"] == home_s) | (tmp["al"] == home_s)].sort_values("date").tail(10)
        a_games = tmp[(tmp["hl"] == away_s) | (tmp["al"] == away_s)].sort_values("date").tail(10)
        h2h = tmp[((tmp["hl"] == home_s) & (tmp["al"] == away_s)) | ((tmp["hl"] == away_s) & (tmp["al"] == home_s))].tail(5)
        
        def get_avg(games, team_l):
            if games.empty: return 1.2
            goals = []
            weights = []
            for i, (_, row) in enumerate(games.iterrows()):
                g = row["home_goals"] if row["hl"] == team_l else row["away_goals"]
                goals.append(g)
                weights.append(i + 1)
            return np.average(goals, weights=weights) if weights else 1.2

        home_w_avg = get_avg(h_games, home_s)
        away_w_avg = get_avg(a_games, away_s)
        
        cols = ["date", "league", "home_team", "away_team", "home_goals", "away_goals"]
        avail_cols = [c for c in cols if c in h_games.columns]

        # ✅ 關鍵：在這裡調用 get_lineup_data，將陣容數據塞入 context
        lineup_json = self.get_lineup_data(home, away)

        return {
            "home_last_5": h_games[avail_cols].tail(5).to_dict(orient="records"),
            "away_last_5": a_games[avail_cols].tail(5).to_dict(orient="records"),
            "h2h": h2h[avail_cols].to_dict(orient="records"),
            "stats": {"home_weighted_xg": home_w_avg, "away_weighted_xg": away_w_avg, "league": league},
            "glicko": ranking_info,
            "elo": ranking_info,
            "lineup": lineup_json # 新增欄位
        }

# --- RealOddsFetcher (維持不變) ---
@dataclass
class OddsPoint:
    time_offset: str; decimal_odds: float; bookmaker: str = "Aggregated"

OddsDataStructure = Dict[str, Dict[str, Dict[str, List[OddsPoint]]]]

class RealOddsFetcher:
    def __init__(self): self.data_path = settings.ODDS_DATA_PATH
    def get_real_odds(self, league, home, away):
        print(f"📈 嘗試從 {os.path.basename(self.data_path)} 讀取數據...")
        if not os.path.exists(self.data_path): return {}
        try:
            if self.data_path.endswith('.json'): return self._read_from_json(home, away)
            else: return self._read_from_csv(home, away)
        except: return {}

    def _read_from_json(self, h, a):
        with open(self.data_path, 'r', encoding='utf-8') as f: matches = json.load(f)
        for m in matches:
            if h.lower() in m.get('home_team', '').lower():
                print(f"✅ 找到比賽: {m.get('home_team')} vs {m.get('away_team')}")
                return self._parse_all_markets(m)
        return {}

    def _read_from_csv(self, h, a):
        try:
            df = pd.read_csv(self.data_path, low_memory=False)
            csv_homes = df['home_team'].unique().astype(str).tolist()
            matches = difflib.get_close_matches(h, csv_homes, n=1, cutoff=0.6)
            target = matches[0] if matches else h
            match_row = df[df['home_team'] == target]
            if not match_row.empty:
                print(f"✅ 找到比賽: {match_row.iloc[0]['home_team']} vs {match_row.iloc[0]['away_team']}")
                return self._parse_all_markets(match_row.iloc[0].to_dict())
        except: pass
        return {}

    def _parse_all_markets(self, d):
        res = {}
        for k, v in d.items():
            if not str(k).endswith('_market'): continue
            try:
                bks = ast.literal_eval(str(v)) if isinstance(v, str) else v
                if not isinstance(bks, list): continue
                m_name = k.replace('_market', '').replace('_', ' ').title()
                sels = []
                if '1x2' in k: m_name, sels = "1x2", ["Home", "Draw", "Away"]
                elif 'asian' in k:
                    line = k.replace('asian_handicap_', '').replace('_market', '').replace('_', '.').replace('plus', '+')
                    m_name, sels = f"Asian Handicap {line}", ["Home", "Away"]
                elif 'over_under' in k:
                    line = k.replace('over_under_', '').replace('_market', '').replace('_', '.')
                    m_name, sels = f"Over/Under {line}", ["Over", "Under"]
                else: continue
                
                stats = self._agg_bks(bks, sels)
                if any(stats[s]['avg'] for s in sels): res[m_name] = stats
            except: continue
        return res

    def _agg_bks(self, bks, sels):
        raw = {s: [] for s in sels}
        for bk in bks:
            hist = bk.get('odds_history_data', [])
            if not isinstance(hist, list): continue
            for i, s in enumerate(sels):
                if i < len(hist):
                    d = hist[i]
                    cur = None
                    if isinstance(d, dict):
                        if 'odds_history' in d and d['odds_history']:
                            try: cur = d['odds_history'][-1].get('odds')
                            except: pass
                        elif 'odds' in d: cur = d.get('odds')
                    if cur: 
                        try: raw[s].append(float(cur))
                        except: pass
        res = {}
        for s in sels:
            vals = raw[s]
            if not vals: 
                res[s] = {'max':[], 'min':[], 'avg':[]}
                continue
            res[s] = {
                'max': [OddsPoint("Cur", max(vals), "Max")],
                'min': [OddsPoint("Cur", min(vals), "Min")],
                'avg': [OddsPoint("Cur", round(sum(vals)/len(vals), 2), "Avg")]
            }
        return res

class OddsAnalyzer:
    def analyze_movement(self, h): return {}


