import pandas as pd
import numpy as np
import os
import random
import ast
import json
import pickle
import difflib  # 用於模糊比對
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from config import settings

# ⚠️ 注意：頂層不要匯入 math_models，避免與 app.py 產生循環引用

# --- 1. 歷史數據儲存庫 ---
class HistoryRepo:
    def __init__(self, csv_path: str):
        self.df = None
        self.ranking_system = None
        self.lineup_model_class = None
        
        # 延遲匯入 math_models_v2
        try:
            from math_models_v2 import Glicko2System, LineupModel
            self.ranking_system = Glicko2System() # 使用 Glicko-2
            self.lineup_model_class = LineupModel
        except ImportError:
            print("⚠️ Warning: math_models_v2 not found. Trying v1...")
            try:
                from math_models import EloSystem
                self.ranking_system = EloSystem() # 降級使用 Elo
            except:
                print("⚠️ Warning: No ranking system available.")

        # 嘗試載入 ML 模型
        self.ml_model = None
        try:
            model_path = os.path.join(os.path.dirname(__file__), "xgb_model.pkl")
            if os.path.exists(model_path):
                with open(model_path, "rb") as f:
                    self.ml_model = pickle.load(f)
        except: pass
        
        # 讀取 CSV
        try:
            if not os.path.exists(csv_path):
                print(f"⚠️ 找不到歷史數據檔案: {csv_path}，切換模擬模式。")
                self._create_mock_data()
                return

            try:
                self.df = pd.read_csv(csv_path, encoding='utf-8-sig', low_memory=False)
            except UnicodeDecodeError:
                self.df = pd.read_csv(csv_path, encoding='latin-1', low_memory=False)
            
            self.df.columns = self.df.columns.str.strip().str.lower().str.replace('\ufeff', '')
            
            column_mapping = {
                "date": ["date", "match_date", "time", "日期"],
                "league": ["league", "div", "division", "聯賽"],
                "home_team": ["home_team", "hometeam", "home", "主隊"],
                "away_team": ["away_team", "awayteam", "away", "客隊"],
                "home_goals": ["home_goals", "fthg", "h_score", "hg", "主隊進球"],
                "away_goals": ["away_goals", "ftag", "a_score", "ag", "客隊進球"],
            }
            
            rename_dict = {}
            for standard_col, possible_names in column_mapping.items():
                for col in self.df.columns:
                    if col in possible_names:
                        rename_dict[col] = standard_col
                        break
            
            self.df.rename(columns=rename_dict, inplace=True)
            self.df["date"] = pd.to_datetime(self.df["date"], dayfirst=True, errors='coerce')
            self.df = self.df.dropna(subset=["date"])
            self.df = self.df.sort_values("date")

            if self.ranking_system:
                self._calculate_rankings()

        except Exception as e:
            print(f"⚠️ 讀取 CSV 錯誤 ({e})，切換模擬模式。")
            self._create_mock_data()

    def _calculate_rankings(self):
        valid_rows = self.df.dropna(subset=['home_goals', 'away_goals', 'home_team', 'away_team'])
        for _, row in valid_rows.iterrows():
            try:
                self.ranking_system.update_ratings(
                    row['home_team'], row['away_team'], 
                    int(row['home_goals']), int(row['away_goals'])
                )
            except: continue

    def _create_mock_data(self):
        self.df = pd.DataFrame({
            "date": [datetime.now() - timedelta(days=x*2) for x in range(100)],
            "league": ["Premier League"] * 100,
            "home_team": ["Arsenal", "Chelsea", "Liverpool", "Man City", "Man Utd"] * 20,
            "away_team": ["Chelsea", "Arsenal", "Man City", "Liverpool", "Spurs"] * 20,
            "home_goals": np.random.randint(0, 4, 100),
            "away_goals": np.random.randint(0, 3, 100)
        })

    # ✅ 重點升級：支援模糊比對的首發名單搜尋
    def get_lineup_prediction(self, home_team, away_team):
        """
        嘗試讀取並分析首發名單 JSON (支援模糊搜尋檔名)
        """
        if not self.lineup_model_class: return None
        
        data_dir = os.path.dirname(settings.HISTORY_CSV_PATH)
        target_file = None
        
        if os.path.exists(data_dir):
            # 取得所有可能是首發名單的 json 檔案
            candidates = [f for f in os.listdir(data_dir) if f.endswith(".json") and "lineup" in f.lower()]
            
            best_score = 0.0
            best_candidate = None
            
            # 預處理輸入的隊名 (去除點號，轉小寫)
            h_input = home_team.lower().replace(".", "").strip()
            a_input = away_team.lower().replace(".", "").strip()
            
            for f in candidates:
                # 處理檔名: "lineup_Atletico_Madrid_vs_Real_Madrid.json"
                # 1. 清理檔名雜訊
                clean_name = f.lower().replace("lineup_", "").replace(".json", "")
                # 2. 將底線轉為空格 "atletico madrid vs real madrid"
                clean_name = clean_name.replace("_", " ")
                
                # 嘗試根據 "vs" 分割
                if " vs " in clean_name:
                    parts = clean_name.split(" vs ")
                    f_home, f_away = parts[0], parts[1]
                    
                    # 分別比對主客隊
                    score_h = difflib.SequenceMatcher(None, h_input, f_home).ratio()
                    score_a = difflib.SequenceMatcher(None, a_input, f_away).ratio()
                    avg_score = (score_h + score_a) / 2
                    
                    # 防呆：嘗試反向比對 (防止主客寫反)
                    score_h_rev = difflib.SequenceMatcher(None, h_input, f_away).ratio()
                    score_a_rev = difflib.SequenceMatcher(None, a_input, f_home).ratio()
                    avg_score_rev = (score_h_rev + score_a_rev) / 2
                    
                    current_score = max(avg_score, avg_score_rev)
                else:
                    # 如果檔名格式怪異，直接比對整串
                    full_query = f"{h_input} {a_input}"
                    current_score = difflib.SequenceMatcher(None, full_query, clean_name).ratio()

                # 更新最佳匹配
                if current_score > best_score:
                    best_score = current_score
                    best_candidate = f
            
            # 設定門檻值 (0.5)，避免匹配到完全無關的檔案
            if best_candidate and best_score > 0.5:
                target_file = os.path.join(data_dir, best_candidate)
                # Debug 用：可以看到匹配了哪個檔案
                # print(f"   (Lineup Fuzzy Match: {best_candidate}, Score: {best_score:.2f})")
        
        if target_file:
            try:
                print(f"   📄 找到首發名單: {os.path.basename(target_file)}")
                with open(target_file, 'r', encoding='utf-8') as f:
                    lineup_data = json.load(f)
                
                model = self.lineup_model_class(lineup_data)
                return model.predict_win_prob()
            except Exception as e:
                print(f"   ⚠️ 解析首發 JSON 失敗: {e}")
                return None
        return None

    # 模糊搜尋隊名 (用於 CSV 數據)
    def _fuzzy_match_team(self, input_name: str, all_teams: List[str]) -> str:
        matches = difflib.get_close_matches(input_name, all_teams, n=1, cutoff=0.6)
        if matches:
            return matches[0]
        return input_name

    def get_match_context(self, home: str, away: str, league: str) -> Dict:
        if self.df is None or self.df.empty: self._create_mock_data()
        
        all_home_teams = self.df['home_team'].unique().astype(str).tolist()
        all_away_teams = self.df['away_team'].unique().astype(str).tolist()
        all_teams = list(set(all_home_teams + all_away_teams))

        real_home = self._fuzzy_match_team(home, all_teams)
        real_away = self._fuzzy_match_team(away, all_teams)
        
        if real_home != home or real_away != away:
            print(f"   🔄 隊名校正: {home} -> {real_home}, {away} -> {real_away}")

        home_s = real_home.lower().strip()
        away_s = real_away.lower().strip()
        
        ranking_info = {}
        if self.ranking_system:
            try:
                r_h_data = self.ranking_system.get_rating(real_home)
                r_a_data = self.ranking_system.get_rating(real_away)
                
                if isinstance(r_h_data, dict):
                    val_h = r_h_data['rating']
                    val_a = r_a_data['rating']
                else:
                    val_h = r_h_data
                    val_a = r_a_data
                
                prob = self.ranking_system.expected_win_prob(real_home, real_away)
                
                ranking_info = {
                    "home_rating": round(val_h, 0),
                    "away_rating": round(val_a, 0),
                    "win_prob": round(prob, 2)
                }
            except Exception as e:
                print(f"Ranking calc error: {e}")

        tmp = self.df.copy()
        tmp["hl"] = tmp["home_team"].astype(str).str.lower().str.strip()
        tmp["al"] = tmp["away_team"].astype(str).str.lower().str.strip()

        h_games = tmp[(tmp["hl"] == home_s) | (tmp["al"] == home_s)].sort_values("date").tail(10)
        a_games = tmp[(tmp["hl"] == away_s) | (tmp["al"] == away_s)].sort_values("date").tail(10)
        h2h = tmp[((tmp["hl"] == home_s) & (tmp["al"] == away_s)) | 
                  ((tmp["hl"] == away_s) & (tmp["al"] == home_s))].tail(5)
        
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
        
        return {
            "home_last_5": h_games[avail_cols].tail(5).to_dict(orient="records"),
            "away_last_5": a_games[avail_cols].tail(5).to_dict(orient="records"),
            "h2h": h2h[avail_cols].to_dict(orient="records"),
            "stats": {"home_weighted_xg": home_w_avg, "away_weighted_xg": away_w_avg, "league": league},
            "glicko": ranking_info,
            "elo": ranking_info
        }

# --- 2. 全盤口解析器 ---
@dataclass
class OddsPoint:
    time_offset: str
    decimal_odds: float
    bookmaker: str = "Aggregated"

OddsDataStructure = Dict[str, Dict[str, Dict[str, List[OddsPoint]]]]

class RealOddsFetcher:
    def __init__(self):
        self.data_path = settings.ODDS_DATA_PATH

    def get_real_odds(self, league: str, home: str, away: str) -> OddsDataStructure:
        print(f"📈 嘗試從 {os.path.basename(self.data_path)} 讀取數據...")
        
        if not os.path.exists(self.data_path):
            print(f"⚠️ 找不到檔案 {self.data_path}，使用模擬數據。")
            return self._generate_simulation_aggregated()

        try:
            if self.data_path.endswith('.json'):
                return self._read_from_json(home, away)
            else:
                return self._read_from_csv(home, away)
        except Exception as e:
            print(f"⚠️ 檔案解析錯誤: {e}")
            return self._generate_simulation_aggregated()

    def _read_from_json(self, home_query, away_query) -> OddsDataStructure:
        with open(self.data_path, 'r', encoding='utf-8') as f:
            matches = json.load(f)
        target_match = None
        for match in matches:
            m_home = match.get('home_team', '').lower()
            if home_query.lower() in m_home:
                target_match = match
                break
        if target_match:
            print(f"✅ 找到比賽: {target_match.get('home_team')} vs {target_match.get('away_team')}")
            return self._parse_all_markets(target_match)
        print(f"⚠️ JSON 中找不到 '{home_query}' 的比賽。")
        return self._generate_simulation_aggregated()

    def _read_from_csv(self, home_query, away_query) -> OddsDataStructure:
        try:
            df = pd.read_csv(self.data_path, low_memory=False)
            
            # CSV 端的模糊搜尋
            csv_home_teams = df['home_team'].unique().astype(str).tolist()
            matches = difflib.get_close_matches(home_query, csv_home_teams, n=1, cutoff=0.6)
            
            target_home = home_query
            if matches: target_home = matches[0]
            
            match_row = df[df['home_team'] == target_home]
            
            if not match_row.empty:
                row = match_row.iloc[0]
                print(f"✅ 找到比賽: {row['home_team']} vs {row['away_team']}")
                return self._parse_all_markets(row.to_dict())
            print(f"⚠️ CSV 中找不到 '{home_query}' 的比賽。")
            return self._generate_simulation_aggregated()
        except Exception as e:
            print(f"❌ CSV 讀取失敗: {e}")
            return self._generate_simulation_aggregated()

    def _parse_all_markets(self, match_data: Dict) -> OddsDataStructure:
        all_markets = {}
        for key, value in match_data.items():
            if not isinstance(key, str) or not key.endswith('_market'): continue
            
            bookmakers = value
            if isinstance(value, str):
                try: bookmakers = ast.literal_eval(value)
                except: continue
            
            if not isinstance(bookmakers, list) or not bookmakers: continue
            
            market_name = key.replace('_market', '').replace('_', ' ').title()
            selections = []
            
            if '1x2' in key:
                market_name = "1x2"
                selections = ["Home", "Draw", "Away"]
            elif 'asian_handicap' in key:
                line = key.replace('asian_handicap_', '').replace('_market', '').replace('_', '.')
                if 'plus' in line: line = line.replace('plus', '+')
                market_name = f"Asian Handicap {line}"
                selections = ["Home", "Away"]
            elif 'over_under' in key:
                line = key.replace('over_under_', '').replace('_market', '').replace('_', '.')
                market_name = f"Over/Under {line}"
                selections = ["Over", "Under"]
            else: continue

            market_stats = self._aggregate_bookmakers(bookmakers, selections)
            if any(market_stats[s]['avg'] for s in selections):
                all_markets[market_name] = market_stats

        return all_markets

    def _aggregate_bookmakers(self, bookmakers: List[Dict], selections: List[str]) -> Dict[str, Dict[str, List[OddsPoint]]]:
        raw_odds = {sel: [] for sel in selections}
        for bk in bookmakers:
            hist_data = bk.get('odds_history_data', [])
            if not isinstance(hist_data, list): continue
            for i, sel in enumerate(selections):
                if i < len(hist_data):
                    outcome_data = hist_data[i]
                    current = None
                    if isinstance(outcome_data, dict):
                        if 'odds_history' in outcome_data and outcome_data['odds_history']:
                            try: current = outcome_data['odds_history'][-1].get('odds')
                            except: pass
                        elif 'odds' in outcome_data: current = outcome_data.get('odds')
                    if current:
                        try: raw_odds[sel].append(float(current))
                        except: pass

        result = {}
        for sel in selections:
            vals = raw_odds[sel]
            if not vals:
                result[sel] = {'max': [], 'min': [], 'avg': []}
                continue
            avg_val = sum(vals) / len(vals)
            max_val = max(vals)
            min_val = min(vals)
            result[sel] = {
                'max': [OddsPoint("Current", max_val, "Max")],
                'min': [OddsPoint("Current", min(vals), "Min")],
                'avg': [OddsPoint("Current", round(avg_val, 2), "Avg")]
            }
        return result

    def _generate_simulation_aggregated(self):
        return {}

class OddsAnalyzer:
    def analyze_movement(self, odds_history: List[OddsPoint]) -> Dict:
        return {"trend_text": "Grok Analyzing"}