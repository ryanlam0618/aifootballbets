import pandas as pd
import numpy as np
import os
import random
import ast
import json
import pickle
import difflib
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from config import settings

# --- 聯賽選單配置 (The Odds API Keys) ---
LEAGUE_OPTIONS = {
    # 五大聯賽
    "1": {"name": "Premier League (England)", "key": "soccer_epl"},
    "2": {"name": "La Liga (Spain)", "key": "soccer_spain_la_liga"},
    "3": {"name": "Bundesliga (Germany)", "key": "soccer_germany_bundesliga"},
    "4": {"name": "Serie A (Italy)", "key": "soccer_italy_serie_a"},
    "5": {"name": "Ligue 1 (France)", "key": "soccer_france_ligue_one"},
    
    # 歐洲杯賽
    "6": {"name": "UEFA Champions League", "key": "soccer_uefa_champs_league"},
    "7": {"name": "UEFA Europa League", "key": "soccer_uefa_europa_league"},
    "8": {"name": "UEFA Europa Conference League", "key": "soccer_uefa_europa_conference_league"},
    "9": {"name": "UEFA Champions League Qualification", "key": "soccer_uefa_champs_league_qualification"},
    "10": {"name": "UEFA Nations League", "key": "soccer_uefa_nations_league"},
    "11": {"name": "UEFA Euro Championship", "key": "soccer_uefa_european_championship"},
    "12": {"name": "UEFA Euro Qualification", "key": "soccer_uefa_euro_qualification"},
    "13": {"name": "UEFA Women's Champions League", "key": "soccer_uefa_champs_league_women"},
    
    # 英格蘭聯賽
    "14": {"name": "Championship (England)", "key": "soccer_efl_champ"},
    "15": {"name": "League 1 (England)", "key": "soccer_england_league1"},
    "16": {"name": "League 2 (England)", "key": "soccer_england_league2"},
    "17": {"name": "EFL Cup (England)", "key": "soccer_england_efl_cup"},
    "18": {"name": "FA Cup (England)", "key": "soccer_fa_cup"},
    
    # 西班牙聯賽
    "19": {"name": "La Liga 2 (Spain)", "key": "soccer_spain_segunda_division"},
    
    # 德國聯賽
    "20": {"name": "Bundesliga 2 (Germany)", "key": "soccer_germany_bundesliga2"},
    "21": {"name": "3. Liga (Germany)", "key": "soccer_germany_liga3"},
    
    # 義大利聯賽
    "22": {"name": "Serie B (Italy)", "key": "soccer_italy_serie_b"},
    
    # 法國聯賽
    "23": {"name": "Ligue 2 (France)", "key": "soccer_france_ligue_two"},
    
    # 其他歐洲主要聯賽
    "24": {"name": "Eredivisie (Netherlands)", "key": "soccer_netherlands_eredivisie"},
    "25": {"name": "Primeira Liga (Portugal)", "key": "soccer_portugal_primeira_liga"},
    "26": {"name": "Premiership (Scotland)", "key": "soccer_spl"},
    "27": {"name": "Belgium First Division", "key": "soccer_belgium_first_div"},
    "28": {"name": "Allsvenskan (Sweden)", "key": "soccer_sweden_allsvenskan"},
    "29": {"name": "Superettan (Sweden)", "key": "soccer_sweden_superettan"},
    "30": {"name": "Super Lig (Turkey)", "key": "soccer_turkey_super_league"},
    "31": {"name": "Austrian Bundesliga", "key": "soccer_austria_bundesliga"},
    "32": {"name": "Swiss Superleague", "key": "soccer_switzerland_superleague"},
    "33": {"name": "Denmark Superliga", "key": "soccer_denmark_superliga"},
    "34": {"name": "Super League (Greece)", "key": "soccer_greece_super_league"},
    "35": {"name": "Premier League (Russia)", "key": "soccer_russia_premier_league"},
    "36": {"name": "Ekstraklasa (Poland)", "key": "soccer_poland_ekstraklasa"},
    "37": {"name": "Eliteserien (Norway)", "key": "soccer_norway_eliteserien"},
    "38": {"name": "Veikkausliiga (Finland)", "key": "soccer_finland_veikkausliiga"},
    "39": {"name": "League of Ireland", "key": "soccer_league_of_ireland"},
    
    # 美洲聯賽
    "40": {"name": "MLS (USA)", "key": "soccer_usa_mls"},
    "41": {"name": "Liga MX (Mexico)", "key": "soccer_mexico_ligamx"},
    "42": {"name": "Série A (Brazil)", "key": "soccer_brazil_campeonato"},
    "43": {"name": "Série B (Brazil)", "key": "soccer_brazil_serie_b"},
    "44": {"name": "Primera División (Argentina)", "key": "soccer_argentina_primera_division"},
    "45": {"name": "Primera División (Chile)", "key": "soccer_chile_campeonato"},
    "46": {"name": "Copa América", "key": "soccer_conmebol_copa_america"},
    "47": {"name": "Copa Libertadores", "key": "soccer_conmebol_copa_libertadores"},
    "48": {"name": "Copa Sudamericana", "key": "soccer_conmebol_copa_sudamericana"},
    "49": {"name": "CONCACAF Gold Cup", "key": "soccer_concacaf_gold_cup"},
    "50": {"name": "CONCACAF Leagues Cup", "key": "soccer_concacaf_leagues_cup"},
    
    # 亞洲聯賽
    "51": {"name": "Super League (China)", "key": "soccer_china_superleague"},
    "52": {"name": "J League (Japan)", "key": "soccer_japan_j_league"},
    "53": {"name": "K League 1 (South Korea)", "key": "soccer_korea_kleague1"},
    
    # 大洋洲聯賽
    "54": {"name": "A-League (Australia)", "key": "soccer_australia_aleague"},
    
    # 非洲聯賽
    "55": {"name": "Africa Cup of Nations", "key": "soccer_africa_cup_of_nations"},
    
    # 國際賽事
    "56": {"name": "FIFA World Cup", "key": "soccer_fifa_world_cup"},
    "57": {"name": "FIFA World Cup Winner", "key": "soccer_fifa_world_cup_winner"},
    "58": {"name": "FIFA World Cup Qualifiers - Europe", "key": "soccer_fifa_world_cup_qualifiers_europe"},
    "59": {"name": "FIFA World Cup Qualifiers - South America", "key": "soccer_fifa_world_cup_qualifiers_south_america"},
    "60": {"name": "FIFA Women's World Cup", "key": "soccer_fifa_world_cup_womens"},
    "61": {"name": "FIFA Club World Cup", "key": "soccer_fifa_club_world_cup"}
}

# --- 球隊名稱映射表 (The Odds API <-> API-Football) ---
# 使用更完整的 team_name_matcher.py 映射
from .team_name_matcher import TEAM_MAPPING_DB, match_teams, get_team_info

def get_api_football_id(team_name: str) -> Optional[int]:
    """獲取 API-Football ID"""
    info = get_team_info(team_name)
    return info.get("api_football_id")


# --- 1. 歷史數據儲存庫 ---
class HistoryRepo:
    def __init__(self, csv_path: str):
        self.df = None
        self.ranking_system = None
        self.lineup_model_class = None
        
        # 從整合版 math_models 導入 (v7.0)
        try:
            from src.math_models import Glicko2System, LineupModel
            self.ranking_system = Glicko2System() 
            self.lineup_model_class = LineupModel
        except ImportError:
            try:
                from src.math_models import EloSystem
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
            self.df["date"] = pd.to_datetime(self.df["date"], errors='coerce')
            self.df = self.df.dropna(subset=["date"]).sort_values("date")

            if self.ranking_system: self._calculate_rankings()

        except Exception as e:
            print(f"⚠️ 讀取 CSV 錯誤 ({e})")
            self._create_mock_data()

    def _calculate_rankings(self):
        valid_rows = self.df.dropna(subset=['home_goals', 'away_goals', 'home_team', 'away_team'])
        for _, row in valid_rows.iterrows():
            try:
                # 優先使用 xG 數據計算評分
                xg_home = row.get('xG') if 'xG' in row.index else None
                xg_away = row.get('xGA') if 'xGA' in row.index else None
                
                self.ranking_system.update_ratings(
                    row['home_team'], row['away_team'], int(row['home_goals']), int(row['away_goals']),
                    xg_home, xg_away
                )
            except: continue

    def _create_mock_data(self):
        self.df = pd.DataFrame()

    def _find_lineup_file(self, home_team, away_team):
        data_dir = os.path.dirname(settings.HISTORY_CSV_PATH)
        lineup_dir = os.path.join(data_dir, "lineup")
        
        # 搜索多個目錄
        search_dirs = []
        if os.path.exists(lineup_dir):
            search_dirs.append(lineup_dir)
        if os.path.exists(data_dir):
            search_dirs.append(data_dir)
        
        if not search_dirs:
            return None
        
        candidates = []
        for search_dir in search_dirs:
            if os.path.exists(search_dir):
                for f in os.listdir(search_dir):
                    if f.endswith(".json") and "lineup" in f.lower():
                        candidates.append(os.path.join(search_dir, f))
        
        best_score = 0.0
        best_candidate = None
        
        # 標準化輸入球隊名稱
        h_input = home_team.lower().replace(".", "").replace(" ", "").strip()
        a_input = away_team.lower().replace(" ", "").strip()
        
        for filepath in candidates:
            filename = os.path.basename(filepath)
            clean_name = filename.lower().replace("lineup_", "").replace(".json", "").replace("_", " ")
            
            if " vs " not in clean_name:
                continue
                
            parts = clean_name.split(" vs ")
            file_h = parts[0].replace(" ", "").strip()
            file_a = parts[1].replace(" ", "").strip()
            
            # 計算兩個方向的匹配分數
            s1 = difflib.SequenceMatcher(None, h_input, file_h).ratio()
            s2 = difflib.SequenceMatcher(None, a_input, file_a).ratio()
            score_normal = (s1 + s2) / 2
            
            s1_rev = difflib.SequenceMatcher(None, h_input, file_a).ratio()
            s2_rev = difflib.SequenceMatcher(None, a_input, file_h).ratio()
            score_rev = (s1_rev + s2_rev) / 2
            
            # 選擇最佳方向
            if score_normal >= score_rev:
                final_score = score_normal
                min_team_match = min(s1, s2)
            else:
                final_score = score_rev
                min_team_match = min(s1_rev, s2_rev)
            
            # 完全匹配檢查 (兩個隊都 > 95% 匹配)
            if score_normal > 0.95 and s1 > 0.95 and s2 > 0.95:
                return filepath
            
            # 只接受兩個隊都有較高匹配度的結果
            if final_score > best_score and min_team_match > 0.8:
                best_score = final_score
                best_candidate = filepath
        
        return best_candidate if best_candidate else None

    def get_lineup_data(self, home_team, away_team):
        target_file = self._find_lineup_file(home_team, away_team)
        if target_file:
            try:
                with open(target_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {}

    def get_lineup_prediction(self, home_team, away_team):
        if not self.lineup_model_class: return None
        data = self.get_lineup_data(home_team, away_team)
        if data:
            print(f"   📄 成功載入陣容數據: {home_team} vs {away_team}")
            return self.lineup_model_class(data).predict_win_prob()
        return None

    def _get_h2h_stats(self, h2h_df, home_s, away_s):
        """計算 Head-to-Head 統計"""
        if h2h_df.empty:
            return {
                'h2h_wins_home': 0,
                'h2h_ways': 0,
                'h2h_wins_away': 0,
                'h2h_avg_goals': 0,
                'h2h_games': 0
            }
        
        wins_home = 0
        ways = 0
        wins_away = 0
        total_goals = 0
        
        for _, row in h2h_df.iterrows():
            hg = row['home_goals'] if pd.notna(row['home_goals']) else 0
            ag = row['away_goals'] if pd.notna(row['away_goals']) else 0
            total_goals += hg + ag
            
            # 判斷實際主客隊的結果
            # 如果輸入的 home_s 是當時的主隊
            if row['hl'] == home_s:
                if hg > ag: wins_home += 1
                elif hg == ag: ways += 1
                else: wins_away += 1
            else:  # home_s 是當時的客隊
                if ag > hg: wins_home += 1
                elif hg == ag: ways += 1
                else: wins_away += 1
        
        return {
            'h2h_wins_home': wins_home,
            'h2h_ways': ways,
            'h2h_wins_away': wins_away,
            'h2h_avg_goals': round(total_goals / len(h2h_df), 2) if len(h2h_df) > 0 else 0,
            'h2h_games': len(h2h_df)
        }
    
    def _get_recent_form(self, games_df, team_s):
        """計算最近 5 場狀態 (3分/勝, 1分/和, 0分/敗)"""
        if games_df.empty:
            return {'points': 0, 'wins': 0, 'draws': 0, 'losses': 0, 'goals_for': 0, 'goals_against': 0}
        
        points, wins, draws, losses = 0, 0, 0, 0
        goals_for, goals_against = 0, 0
        
        # 只看最近 5 場
        recent = games_df.tail(5)
        
        for _, row in recent.iterrows():
            hg = row['home_goals'] if pd.notna(row['home_goals']) else 0
            ag = row['away_goals'] if pd.notna(row['away_goals']) else 0
            
            if row['hl'] == team_s:
                goals_for += hg
                goals_against += ag
                if hg > ag:
                    wins += 1
                    points += 3
                elif hg == ag:
                    draws += 1
                    points += 1
                else:
                    losses += 1
            else:
                goals_for += ag
                goals_against += hg
                if ag > hg:
                    wins += 1
                    points += 3
                elif hg == ag:
                    draws += 1
                    points += 1
                else:
                    losses += 1
        
        return {
            'points': points,
            'wins': wins,
            'draws': draws,
            'losses': losses,
            'goals_for': goals_for,
            'goals_against': goals_against
        }

    def _fuzzy_match_team(self, input_name: str, all_teams: List[str]) -> str:
        matches = difflib.get_close_matches(input_name, all_teams, n=1, cutoff=0.6)
        return matches[0] if matches else input_name

    def get_match_context(self, home: str, away: str, league: str = None) -> Dict:
        if self.df is None or self.df.empty: self._create_mock_data()
        
        # 確保列是字符串類型
        self.df['home_team'] = self.df['home_team'].astype(str)
        self.df['away_team'] = self.df['away_team'].astype(str)
        
        all_teams = list(set(
            self.df['home_team'].unique().tolist() + 
            self.df['away_team'].unique().tolist()
        ))
        real_home = self._fuzzy_match_team(home, all_teams)
        real_away = self._fuzzy_match_team(away, all_teams)
        
        if real_home != home or real_away != away:
            print(f"   🔄 歷史數據隊名校正: {home} -> {real_home}, {away} -> {real_away}")

        home_s, away_s = real_home.lower().strip(), real_away.lower().strip()
        
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

        tmp = self.df.copy()
        tmp["hl"] = tmp["home_team"].astype(str).str.lower().str.strip()
        tmp["al"] = tmp["away_team"].astype(str).str.lower().str.strip()
        
        h_games = tmp[(tmp["hl"] == home_s) | (tmp["al"] == home_s)].sort_values("date").tail(10)
        a_games = tmp[(tmp["hl"] == away_s) | (tmp["al"] == away_s)].sort_values("date").tail(10)
        h2h = tmp[((tmp["hl"] == home_s) & (tmp["al"] == away_s)) | ((tmp["hl"] == away_s) & (tmp["al"] == home_s))].tail(10)

        # ========== Head-to-Head 統計 ==========
        h2h_stats = self._get_h2h_stats(h2h, home_s, away_s)
        
        # ========== 最近狀態 ==========
        home_form = self._get_recent_form(h_games, home_s)
        away_form = self._get_recent_form(a_games, away_s)
        
        # 計算聯賽平均值 (用於缺少數據時的回退值)
        def get_league_xg_avg():
            """計算聯賽平均 xG"""
            if self.df is None or self.df.empty:
                return 1.35  # 一般聯賽平均 xG
            try:
                # 支援大小寫 column names
                if 'xg' in self.df.columns and 'xga' in self.df.columns:
                    valid = self.df.dropna(subset=['xg', 'xga'])
                    if not valid.empty:
                        return float(valid['xg'].mean())
                elif 'xG' in self.df.columns and 'xGA' in self.df.columns:
                    valid = self.df.dropna(subset=['xG', 'xGA'])
                    if not valid.empty:
                        return float(valid['xG'].mean())
            except: pass
            return 1.35
        
        league_xg_avg = get_league_xg_avg()
        
        def get_avg(games, team_l, use_xg=True):
            if games.empty: return league_xg_avg
            goals = []
            weights = []
            
            for i, (_, row) in enumerate(games.iterrows()):
                # 優先使用 xG, 否則使用實際進球 (支援大小寫)
                xg_col = 'xg' if 'xg' in games.columns else ('xG' if 'xG' in games.columns else None)
                xga_col = 'xga' if 'xga' in games.columns else ('xGA' if 'xGA' in games.columns else None)
                
                if use_xg and xg_col and xga_col and pd.notna(row.get(xg_col)) and pd.notna(row.get(xga_col)):
                    g = row[xg_col] if row['hl'] == team_l else row[xga_col]
                else:
                    g = row["home_goals"] if row["hl"] == team_l else row["away_goals"]
                goals.append(g)
                weights.append(i + 1)
            
            return np.average(goals, weights=weights) if weights else league_xg_avg

        def get_avg_xg(games, team_l):
            """計算球隊的平均 xG (支援新舊格式和大小寫)"""
            if games.empty:
                return {'xg_for': league_xg_avg, 'xg_against': league_xg_avg}
            
            # 支援大小寫 column names
            xg_col = 'xg' if 'xg' in games.columns else ('xG' if 'xG' in games.columns else None)
            xga_col = 'xga' if 'xga' in games.columns else ('xGA' if 'xGA' in games.columns else None)
            
            xg_for = []
            xg_against = []
            
            for _, row in games.iterrows():
                # 嘗試從新格式獲取 xG
                has_xg = xg_col and pd.notna(row.get(xg_col))
                has_xga = xga_col and pd.notna(row.get(xga_col))
                
                if row["hl"] == team_l:
                    if has_xg:
                        xg_for.append(row[xg_col])
                    else:
                        xg_for.append(row["home_goals"])
                    
                    if has_xga:
                        xg_against.append(row[xga_col])
                    else:
                        xg_against.append(row["away_goals"])
                else:
                    if has_xga:
                        xg_for.append(row[xga_col])
                    else:
                        xg_for.append(row["away_goals"])
                    
                    if has_xg:
                        xg_against.append(row[xg_col])
                    else:
                        xg_against.append(row["home_goals"])
            
            return {
                'xg_for': np.mean(xg_for) if xg_for else league_xg_avg,
                'xg_against': np.mean(xg_against) if xg_against else league_xg_avg
            }

        home_w_avg = get_avg(h_games, home_s)
        away_w_avg = get_avg(a_games, away_s)

        # 計算 xG 數據 (新功能)
        home_xg = get_avg_xg(h_games, home_s)
        away_xg = get_avg_xg(a_games, away_s)
        
        cols = ["date", "league", "home_team", "away_team", "home_goals", "away_goals"]
        avail_cols = [c for c in cols if c in h_games.columns]
        lineup_json = self.get_lineup_data(home, away)

        return {
            "home_last_5": h_games[avail_cols].tail(5).to_dict(orient="records"),
            "away_last_5": a_games[avail_cols].tail(5).to_dict(orient="records"),
            "h2h": h2h[avail_cols].to_dict(orient="records"),
            "h2h_stats": h2h_stats,
            "home_form": home_form,
            "away_form": away_form,
            "stats": {
                "home_weighted_xg": home_w_avg,
                "away_weighted_xg": away_w_avg,
                "league": league,
                # 新增 xG 數據
                "home_xg_for": home_xg['xg_for'],
                "home_xg_against": home_xg['xg_against'],
                "away_xg_for": away_xg['xg_for'],
                "away_xg_against": away_xg['xg_against'],
            },
            "glicko": ranking_info,
            "elo": ranking_info,
            "lineup": lineup_json
        }

# ==========================================
# 2. 真實賠率獲取器 (整合 The Odds API)
# ==========================================
@dataclass
class OddsPoint:
    time_offset: str; decimal_odds: float; bookmaker: str = "Aggregated"

OddsDataStructure = Dict[str, Dict[str, Dict[str, List[OddsPoint]]]]

class RealOddsFetcher:
    def __init__(self):
        self.api_key = getattr(settings, 'ODDS_API_KEY', '') 
        self.base_url = "https://api.the-odds-api.com/v4/sports"

    def get_real_odds(self, league_key: str, home: str, away: str) -> OddsDataStructure:
        """
        league_key: 必須是 API 支援的 key (如 'soccer_epl')
        """
        print(f"🌍 連線 The Odds API 獲取即時賠率...")
        
        if not self.api_key:
            print("⚠️ 錯誤: 未設定 ODDS_API_KEY。請在 config.py 設定。")
            return {}

        # 如果傳入的不是 key，嘗試轉換 (容錯)
        if not league_key.startswith('soccer_'):
            league_key = self._get_sport_key(league_key)
            
        print(f"   目標聯賽 Key: {league_key}")

        try:
            url = f"{self.base_url}/{league_key}/odds"
            params = {
                'apiKey': self.api_key,
                'regions': 'eu,uk',
                'markets': 'h2h,spreads,totals', 
                'oddsFormat': 'decimal'
            }
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                print(f"❌ API 錯誤 ({response.status_code}): {response.text}")
                return {}
            
            data = response.json()
            
            # 尋找比賽
            target_match = None
            h_in = home.lower()
            a_in = away.lower()
            
            for match in data:
                m_h = match.get('home_team', '').lower()
                m_a = match.get('away_team', '').lower()
                if (h_in in m_h or m_h in h_in) and (a_in in m_a or m_a in a_in):
                    target_match = match
                    break
            
            if target_match:
                print(f"✅ 找到比賽 (API): {target_match['home_team']} vs {target_match['away_team']}")
                return self._process_api_response(target_match)
            else:
                print(f"⚠️ API 回傳中找不到 '{home} vs {away}' 的比賽。")
                return {}

        except Exception as e:
            print(f"❌ 連線例外: {e}")
            return {}

    def _get_sport_key(self, league_name: str) -> str:
        # 簡單的 fallback，防止 app.py 傳錯
        for key, val in LEAGUE_OPTIONS.items():
            if val["name"] == league_name:
                return val["key"]
        return 'soccer_epl' 

    def _process_api_response(self, match_data) -> OddsDataStructure:
        all_markets = {}
        bookmakers = match_data.get('bookmakers', [])
        temp_data = {}

        for bk in bookmakers:
            for market in bk.get('markets', []):
                key = market['key']
                for outcome in market['outcomes']:
                    name = outcome['name']
                    price = outcome['price']
                    point = outcome.get('point')

                    market_name, selection_name = "", ""

                    if key == 'h2h':
                        market_name = "1x2"
                        if name == match_data['home_team']: selection_name = "Home"
                        elif name == match_data['away_team']: selection_name = "Away"
                        else: selection_name = "Draw"
                    elif key == 'spreads':
                        p_str = f"{point}" if point < 0 else f"+{point}"
                        market_name = f"Asian Handicap {p_str}" 
                        selection_name = "Home" if name == match_data['home_team'] else "Away"
                    elif key == 'totals':
                        market_name = f"Over/Under {point}"
                        selection_name = name 

                    if market_name and selection_name:
                        if market_name not in temp_data: temp_data[market_name] = {}
                        if selection_name not in temp_data[market_name]: temp_data[market_name][selection_name] = []
                        temp_data[market_name][selection_name].append(price)

        for m_name, selections in temp_data.items():
            market_stats = {}
            for s_name, prices in selections.items():
                if prices:
                    market_stats[s_name] = {
                        'max': [OddsPoint("Current", max(prices), "Max")],
                        'min': [OddsPoint("Current", min(prices), "Min")],
                        'avg': [OddsPoint("Current", round(sum(prices)/len(prices), 2), "Avg")]
                    }
            if market_stats:
                all_markets[m_name] = market_stats

        return all_markets


class OddsHarvesterFetcher:
    """
    使用 OddsHarvester 從 oddsportal.com 獲取平均賠率
    """
    
    def __init__(self):
        self.oh_base_path = "OddsHarvester"
    
    def get_real_odds(self, league_key: str, home: str, away: str) -> OddsDataStructure:
        """
        從 oddsportal.com 獲取平均賠率
        
        league_key: The Odds API key (如 'soccer_epl')
        home: 主隊名稱
        away: 客隊名稱
        """
        import asyncio
        import sys
        import os
        
        # 確保 OddsHarvester 路徑在 sys.path 中
        oh_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', self.oh_base_path)
        oh_base = os.path.normpath(oh_base)
        oh_src_path = os.path.join(oh_base, 'src')
        
        # === DEBUG LOGGING ===
        import json
        log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "id": "log_path_setup",
                "timestamp": 1733456789005,
                "location": "data_modules.py:get_real_odds",
                "message": "OddsHarvester 路徑設置",
                "data": {"oh_base": oh_base, "oh_src_path": oh_src_path, "old_sys_path": sys.path[:3]},
                "runId": "debug-path",
                "hypothesisId": "A"
            }) + "\n")
        # === END DEBUG ===
        
        # 修復: 完全移除 src 目錄的影響
        # 移除 '' 和當前工作目錄
        cwd = os.getcwd()
        new_sys_path = []
        for p in sys.path:
            # 排除當前目錄和任何 src 目錄
            if p and p != cwd and not p.endswith('\\src') and not p.endswith('/src'):
                new_sys_path.append(p)
        sys.path[:] = new_sys_path
        # 添加 OddsHarvester 到開頭
        sys.path.insert(0, oh_base)
        
        # === DEBUG LOGGING ===
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "id": "log_syspath_after",
                "timestamp": 1733456789100,
                "location": "data_modules.py:get_real_odds",
                "message": "sys.path after fix",
                "data": {"new_sys_path": sys.path[:5]},
                "runId": "debug-path",
                "hypothesisId": "B"
            }) + "\n")
        # === END DEBUG ===
        
        print(f"🌐 連線 OddsPortal 獲取平均賠率...")
        
        # 使用 subprocess 在獨立 Python 進程中運行 OddsHarvester
        # 這樣可以繞過模組導入的問題
        print("   ⚠️ 使用 OddsHarvester subprocess...")
        
        try:
            import subprocess
            import datetime
            
            oh_base = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\OddsHarvester"
            oh_script = os.path.join(oh_base, "src", "main.py")
            
            # 獲取今天的日期
            today = datetime.datetime.now().strftime('%Y%m%d')
            
            # 轉換 league_key 為 OddsHarvester 格式
            league_slug = self._get_oh_league(league_key)
            
            # ===== 使用默認熱門盤口 =====
            # 默認使用常見盤口：AH=0 (平手), OU=2.5 (2.5球)
            ah_line = "0"
            ou_line = "2.5"
            print(f"   📊 使用默認盤口: AH={ah_line}, OU={ou_line}")
            
            # 爬取所有可用的市場
            print(f"   📊 爬取所有可用市場")
            
            # 獲取 OddsHarvester 的 venv Python 路徑
            venv_python = os.path.join(oh_base, ".venv", "Scripts", "python.exe")
            print(f"   🐍 使用 venv Python: {venv_python}")
            
            # ===== 使用 OddsURL.py 獲取正確的比賽 URL =====
            print(f"   🔍 正在搜尋正確的比賽 URL...")
            
            odds_url_script = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\TakeData\OddsURL.py"
            
            # 構建 league URL
            league_url_map = {
                'england-premier-league': 'https://www.oddsportal.com/football/england/premier-league/',
                'spain-primera-division': 'https://www.oddsportal.com/football/spain/laliga/',
                'germany-bundesliga': 'https://www.oddsportal.com/football/germany/bundesliga/',
                'italy-serie-a': 'https://www.oddsportal.com/football/italy/serie-a/',
                'france-ligue-1': 'https://www.oddsportal.com/football/france/ligue-1/',
            }
            league_url = league_url_map.get(league_slug, f'https://www.oddsportal.com/football/{league_slug}/')
            
            print(f"   🌐 搜尋聯賽: {league_url}")
            
            # 運行 OddsURL.py 獲取所有比賽 URL
            # 使用預設 Python（系統默認 Python，有安裝所需依賴）
            
            # 獲取系統默認 Python
            default_python = sys.executable
            
            print(f"   🔄 正在執行 OddsURL.py...")
            
            # 從 league_url 提取國家和聯賽
            # 例如: https://www.oddsportal.com/football/spain/laliga/ -> country=spain, league=laliga
            from urllib.parse import urlparse
            parsed = urlparse(league_url)
            path_parts = [p for p in parsed.path.strip('/').split('/') if p]
            # path_parts[0] 是 "football"（運動類型），需要跳過
            country = path_parts[1] if len(path_parts) > 1 else "england"
            league = path_parts[2] if len(path_parts) > 2 else "premier-league"
            
            print(f"   🔍 爬取聯賽: {country}/{league}")
            
            env = os.environ.copy()
            env['PYTHONPATH'] = oh_base
            
            # 使用列表形式調用，避免 shell=True 的問題
            process_url = subprocess.Popen(
                [default_python, odds_url_script, country, league],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=os.path.dirname(odds_url_script)
            )
            
            all_urls = []
            stdout, stderr = process_url.communicate(timeout=300)  # 增加超時到 5 分鐘
            
            print(f"   📝 OddsURL.py 輸出長度: {len(stdout)}")
            if stdout:
                print(f"   📝 OddsURL.py 原始輸出（前200字）: {stdout[:200]}")
            
            # 解析輸出中的 URL - 使用更嚴格的過濾
            import re
            # 匹配完整的 oddsportal URL 格式
            url_pattern = re.compile(r'https://www\.oddsportal\.com/football/[^/]+/[^/]+/[^/]+/')
            
            for line in stdout.split('\n'):
                line_clean = line.strip()
                # 使用正則表達式匹配完整 URL
                match = url_pattern.search(line_clean)
                if match:
                    url = match.group(0)
                    if url and url not in all_urls:
                        all_urls.append(url)
            
            if stderr:
                print(f"   ⚠️ 錯誤: {stderr[:500]}")
            
            print(f"   ✅ 共獲取 {len(all_urls)} 個比賽 URL")
            if all_urls:
                print(f"   📋 前3個URL: {all_urls[:3]}")
            
            # 找尋匹配的比賽 URL
            match_url = None
            home_lower = home.lower()
            away_lower = away.lower()
            
            for url in all_urls:
                url_lower = url.lower()
                # 檢查 URL 中是否包含雙方球隊名（只匹配球隊名，不含ID）
                if home_lower.replace(' ', '') in url_lower.replace('-', '').replace(' ', '') and \
                   away_lower.replace(' ', '') in url_lower.replace('-', '').replace(' ', ''):
                    match_url = url
                    print(f"   ✅ 找到匹配 URL: {url}")
                    break
            
            if not match_url and all_urls:
                # 使用第一個 URL
                match_url = all_urls[0]
                print(f"   ⚠️ 使用第一個可用 URL: {match_url}")
            
            if not match_url:
                print("   ❌ 無法獲取比賽 URL")
                return {}
            
            # 使用 subprocess 運行（不使用 shell=True 以避免路徑問題）
            # 指定輸出文件路徑 - 使用正斜杠
            output_file = os.path.join(oh_base, "scraped_data.json").replace("\\", "/")
            
            # 使用列表形式，避免 shell=True 的路徑問題
            # 添加 --preview_submarkets_only 來爬取所有可用市場（包含可見的 submarkets 和平均賠率）
            cmd_list = [
                venv_python,
                oh_script,
                "scrape_upcoming",
                "--sport", "football",
                "--match_links", match_url,
                "--headless",
                "--preview_submarkets_only",
                "--file_path", output_file
            ]
            
            # === DEBUG LOGGING - Hypothesis: Missing --markets parameter ===
            import json
            log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": "log_cmd_before",
                    "timestamp": 1733456789000,
                    "location": "data_modules.py:843",
                    "message": "Command list BEFORE adding markets",
                    "data": {"cmd_list": cmd_list, "has_markets_param": "--markets" in cmd_list},
                    "runId": "debug-run",
                    "hypothesisId": "A"
                }) + "\n")
            # === END DEBUG ===
            
            # 添加市場參數 - 爬取所有主要市場 (使用正確的市場名稱)
            # 參考 OddsHarvester 支援的市場: over_under_X, asian_handicap_X
            markets_to_scrape = [
                "1x2", "btts", "double_chance", "dnb",
                "over_under_2_5", "over_under_3", "over_under_3_5",
                "asian_handicap_0", "asian_handicap_-0_5", "asian_handicap_-1",
                "asian_handicap_+0_5", "asian_handicap_+1"
            ]
            cmd_list.extend(["--markets", ",".join(markets_to_scrape)])
            
            # === DEBUG LOGGING ===
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": "log_cmd_after",
                    "timestamp": 1733456789000,
                    "location": "data_modules.py:843",
                    "message": "Command list AFTER adding markets",
                    "data": {"cmd_list": cmd_list, "markets_added": markets_to_scrape},
                    "runId": "debug-run",
                    "hypothesisId": "A"
                }) + "\n")
            # === END DEBUG ===
            
            cmd_str = " ".join(cmd_list)  # 用於調試輸出
            
            print(f"   🧪 執行命令: {cmd_str}")
            print(f"   🎯 目標比賽: {home} vs {away}")
            print(f"   🔗 比賽URL: {match_url}")
            print(f"   ⏳ 正在爬取數據...")
            
            # 設置環境變量
            import os
            env = os.environ.copy()
            env['PYTHONPATH'] = oh_base
            
            # 使用列表形式調用 subprocess
            import subprocess
            process = subprocess.Popen(
                cmd_list,
                cwd=oh_base,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合併 stderr 到 stdout
                text=True,
                env=env
            )
            
            # 即時讀取輸出（減少輸出以提高性能）
            output_lines = []
            line_count = 0
            try:
                for line in iter(process.stdout.readline, ''):
                    if line:
                        # 只顯示前20行和重要的行
                        if line_count < 5 or 'INFO - Successfully' in line or 'ERROR' in line or 'Scraping match:' in line:
                            print(f"   📝 {line.rstrip()}")
                        output_lines.append(line)
                        line_count += 1
                process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                print("   ❌ 執行超時，正在終止進程...")
                process.kill()
                process.wait()
                return {}
            
            result_stdout = ''.join(output_lines)
            result = type('obj', (object,), {
                'returncode': process.returncode,
                'stdout': result_stdout,
                'stderr': ''
            })()
            
            end_time = datetime.datetime.now().isoformat()
            debug_log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({
                    "timestamp": end_time,
                    "event": "subprocess_end",
                    "returncode": result.returncode,
                    "stdout_len": len(result.stdout) if result.stdout else 0,
                    "stderr_len": len(result.stderr) if result.stderr else 0,
                    "hypothesis": "testing_subprocess_timing"
                }) + "\n")
            
            print(f"   📊 返回碼: {result.returncode}")
            
            # 讀取並解析輸出文件
            if os.path.exists(output_file):
                try:
                    import json
                    with open(output_file, 'r', encoding='utf-8') as f:
                        scraped_data = json.load(f)
                    print(f"   ✅ 成功讀取 {len(scraped_data)} 條比賽數據")
                    
                    # 查找匹配的對戰組合
                    matched_match = None
                    
                    # 確保數據是列表格式
                    if isinstance(scraped_data, dict):
                        scraped_data = scraped_data.get('matches', scraped_data.get('data', [scraped_data]))
                    
                    for match in scraped_data:
                        # 使用 home_team 和 away_team 匹配
                        match_home = match.get('home_team', '').lower()
                        match_away = match.get('away_team', '').lower()
                        home_lower = home.lower()
                        away_lower = away.lower()
                        
                        # 嘗試多種匹配方式（精確匹配或包含匹配）
                        if (home_lower in match_home or match_home in home_lower) and \
                           (away_lower in match_away or match_away in away_lower):
                            # 選擇包含最多市場數據的比賽（通常是最新的一個）
                            if matched_match is None:
                                matched_match = match
                            else:
                                # 比較兩個比賽的市場數據數量
                                current_market_keys = [k for k in match.keys() if k.endswith('_market')]
                                matched_market_keys = [k for k in matched_match.keys() if k.endswith('_market')]
                                if len(current_market_keys) > len(matched_market_keys):
                                    matched_match = match
                    
                    if matched_match:
                        print(f"   ✅ 找到匹配: {matched_match.get('home_team')} vs {matched_match.get('away_team')}")
                        # 解析真實赔率數據
                        odds_data = self._parse_oh_odds(matched_match, ou_line, ah_line)
                        return odds_data
                    else:
                        print(f"   ⚠️ 未找到匹配: {home} vs {away}")
                        # 打印第一個匹配看看格式
                        if scraped_data:
                            print(f"   📝 第一條數據: {scraped_data[0]}")
                        return {}
                except Exception as e:
                    print(f"   ❌ 解析數據失敗: {e}")
            else:
                print(f"   ⚠️ 輸出文件不存在: {output_file}")
            
            return {}
            
        except subprocess.TimeoutExpired:
            # 超时时添加调试日志
            timeout_time = datetime.datetime.now().isoformat()
            debug_log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({
                    "timestamp": timeout_time,
                    "event": "subprocess_timeout",
                    "timeout_seconds": 300,
                    "hypothesis": "testing_subprocess_timing"
                }) + "\n")
            print("   ❌ OdtsHarvester 執行超時")
            return {}
        except Exception as e:
            # 異常時添加調試日誌
            error_time = datetime.datetime.now().isoformat()
            debug_log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
            with open(debug_log_path, "a") as f:
                f.write(json.dumps({
                    "timestamp": error_time,
                    "event": "subprocess_exception",
                    "error": str(e),
                    "hypothesis": "testing_subprocess_timing"
                }) + "\n")
            print(f"   ❌ OdtsHarvester 執行失敗: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def get_real_odds_3(self, league_key: str, home: str, away: str, odds_source: int) -> dict:
        """使用 3rd party API 獲取即時赔率"""
        pass
    
    def _get_oh_league(self, league_key: str) -> str:
        """
        將 The Odds API league key 轉換為 OddsHarvester league slug
        """
        league_mapping = {
            'soccer_epl': 'england-premier-league',
            'soccer_spain_la_liga': 'spain-primera-division',
            'soccer_germany_bundesliga': 'germany-bundesliga',
            'soccer_italy_serie_a': 'italy-serie-a',
            'soccer_france_ligue_one': 'france-ligue-1',
            'soccer_uefa_champs_league': 'europe-champions-league',
            'soccer_uefa_europa_league': 'europe-europa-league',
            'soccer_efl_champ': 'england-championship',
            'soccer_england_league1': 'england-league-one',
            'soccer_england_league2': 'england-league-two',
            'soccer_england_efl_cup': 'england-league-cup',
            'soccer_fa_cup': 'england-fa-cup',
            'soccer_spain_segunda_division': 'spain-segunda-division',
            'soccer_germany_bundesliga2': 'germany-bundesliga-2',
            'soccer_italy_serie_b': 'italy-serie-b',
            'soccer_france_ligue_two': 'france-ligue-2',
            'soccer_netherlands_eredivisie': 'netherlands-eredivisie',
            'soccer_portugal_primeira_liga': 'portugal-primeira-liga',
            'soccer_spl': 'scotland-premier-league',
            'soccer_usa_mls': 'usa-mls',
            'soccer_brazil_campeonato': 'brazil-serie-a',
            'soccer_argentina_primera_division': 'argentina-primera-division',
        }
        return league_mapping.get(league_key, 'england-premier-league')
    
    def _parse_oh_odds(self, match_data: dict, ou_line: str = "2.5", ah_line: str = "0") -> dict:
        """
        解析 OddsHarvester 返回的比賽數據，提取所有可用的市場赔率
        
        動態解析所有市場：
        - 1x2_market -> 1x2
        - over_under_X_market -> Over/Under X
        - asian_handicap_X_market -> Asian Handicap X
        """
        try:
            all_markets = {}
            
            # === DEBUG LOGGING - Log received match_data keys ===
            import json
            log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
            all_keys = list(match_data.keys())
            market_keys = [k for k in all_keys if k.endswith('_market')]
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": "log_parse_start",
                    "timestamp": 1733456789000,
                    "location": "data_modules.py:_parse_oh_odds",
                    "message": "Parsing received data - keys analysis",
                    "data": {
                        "total_keys": len(all_keys),
                        "all_keys": all_keys[:20],  # First 20 keys
                        "market_keys_found": market_keys,
                        "has_market_data": len(market_keys) > 0
                    },
                    "runId": "debug-run",
                    "hypothesisId": "A"
                }) + "\n")
            # === END DEBUG ===
            
            # 遍歷所有市場 key
            for key in match_data.keys():
                if not key.endswith('_market'):
                    continue
                
                market_name = key.replace('_market', '')
                market_data = match_data[key]
                
                if not market_data or not isinstance(market_data, list):
                    continue
                
                # 解析 1x2 市場
                if market_name == '1x2':
                    home_prices = []
                    draw_prices = []
                    away_prices = []
                    
                    for bm in market_data:
                        try:
                            h = float(bm.get('1', 0) or bm.get('home', 0) or 0)
                            d = float(bm.get('X', 0) or bm.get('x', 0) or bm.get('draw', 0) or 0)
                            a = float(bm.get('2', 0) or bm.get('away', 0) or 0)
                            if h > 0: home_prices.append(h)
                            if d > 0: draw_prices.append(d)
                            if a > 0: away_prices.append(a)
                        except (ValueError, TypeError):
                            pass
                    
                    if home_prices or draw_prices or away_prices:
                        all_markets['1x2'] = {}
                        if home_prices:
                            all_markets['1x2']['Home'] = {
                                'max': [OddsPoint("Current", max(home_prices), "Max")],
                                'min': [OddsPoint("Current", min(home_prices), "Min")],
                                'avg': [OddsPoint("Current", round(sum(home_prices)/len(home_prices), 2), "Avg")]
                            }
                        if draw_prices:
                            all_markets['1x2']['Draw'] = {
                                'max': [OddsPoint("Current", max(draw_prices), "Max")],
                                'min': [OddsPoint("Current", min(draw_prices), "Min")],
                                'avg': [OddsPoint("Current", round(sum(draw_prices)/len(draw_prices), 2), "Avg")]
                            }
                        if away_prices:
                            all_markets['1x2']['Away'] = {
                                'max': [OddsPoint("Current", max(away_prices), "Max")],
                                'min': [OddsPoint("Current", min(away_prices), "Min")],
                                'avg': [OddsPoint("Current", round(sum(away_prices)/len(away_prices), 2), "Avg")]
                            }
                    print(f"   📊 解析 1x2: Home={len(home_prices)}, Draw={len(draw_prices)}, Away={len(away_prices)} 莊家")
                
                # 解析 Over/Under 市場
                elif market_name.startswith('over_under_'):
                    # 提取 base line (如 2.5, 3, 3.5 from market name)
                    base_line_str = market_name.replace('over_under_', '').replace('_', '.')
                    try:
                        base_line_val = float(base_line_str)
                    except:
                        base_line_val = 2.5  # default
                    
                    # 解析每個 submarket - 直接從名稱提取總分值
                    over_prices = []
                    under_prices = []
                    
                    for submarket in market_data:
                        submarket_name = submarket.get('submarket_name', '')
                        
                        # 直接從 submarket_name 提取總分值 (如 "Over/Under +2.5" -> 2.5)
                        import re
                        # Match the full number with sign at the start
                        match = re.search(r'Over/Under\s+([+-]?\d+\.?\d*)', submarket_name)
                        if not match:
                            continue
                        
                        total_str = match.group(1)
                        try:
                            total_val = float(total_str)
                        except:
                            continue
                        
                        # 收集與目標總分匹配的赔率
                        try:
                            o = float(submarket.get('odds_over', 0) or submarket.get('over', 0) or 0)
                            u = float(submarket.get('odds_under', 0) or submarket.get('under', 0) or 0)
                            
                            # 只收集總分等於基準線的赔率
                            if abs(total_val - base_line_val) < 0.01:
                                if o > 0:
                                    over_prices.append(o)
                                if u > 0:
                                    under_prices.append(u)
                        except (ValueError, TypeError):
                            pass
                    
                    if over_prices or under_prices:
                        market_name_display = f"Over/Under {base_line_val}"
                        all_markets[market_name_display] = {}
                        if over_prices:
                            all_markets[market_name_display]['Over'] = {
                                'max': [OddsPoint("Current", max(over_prices), "Max")],
                                'min': [OddsPoint("Current", min(over_prices), "Min")],
                                'avg': [OddsPoint("Current", round(sum(over_prices)/len(over_prices), 2), "Avg")]
                            }
                        if under_prices:
                            all_markets[market_name_display]['Under'] = {
                                'max': [OddsPoint("Current", max(under_prices), "Max")],
                                'min': [OddsPoint("Current", min(under_prices), "Min")],
                                'avg': [OddsPoint("Current", round(sum(under_prices)/len(under_prices), 2), "Avg")]
                            }
                    print(f"   📊 解析 Over/Under {base_line_val}: Over={len(over_prices)}, Under={len(under_prices)} 莊家")
                
                # 解析 Asian Handicap 市場
                elif market_name.startswith('asian_handicap_'):
                    # 提取 base line (如 0, -0.5, -1, +0.5, +1)
                    base_line_str = market_name.replace('asian_handicap_', '').replace('_', '.')
                    
                    # 解析每個 submarket - 直接從名稱提取讓分值
                    home_prices = []
                    away_prices = []
                    
                    for submarket in market_data:
                        submarket_name = submarket.get('submarket_name', '')
                        
                        # 直接從 submarket_name 提取讓分值 (如 "Asian Handicap -0.5" -> -0.5)
                        import re
                        # Match the full number with sign at the start
                        match = re.search(r'Asian Handicap\s+([+-]?\d+\.?\d*)', submarket_name)
                        if not match:
                            continue
                        
                        handicap_str = match.group(1)
                        try:
                            handicap_val = float(handicap_str)
                        except:
                            continue
                        
                        # team1_handicap 和 team2_handicap 是赔率
                        try:
                            h = float(submarket.get('team1_handicap', 0) or 0)
                            a = float(submarket.get('team2_handicap', 0) or 0)
                            
                            # 解析 base_line_str，去掉 + 符號
                            base_val = float(base_line_str.replace('+', ''))
                            
                            # 只收集讓分值等於基準線的赔率
                            if abs(handicap_val - base_val) < 0.01:
                                if h > 0:
                                    home_prices.append(h)
                                if a > 0:
                                    away_prices.append(a)
                        except (ValueError, TypeError):
                            pass
                    
                    if home_prices or away_prices:
                        market_name_display = f"Asian Handicap {base_line_str}"
                        all_markets[market_name_display] = {}
                        if home_prices:
                            all_markets[market_name_display]['Home'] = {
                                'max': [OddsPoint("Current", max(home_prices), "Max")],
                                'min': [OddsPoint("Current", min(home_prices), "Min")],
                                'avg': [OddsPoint("Current", round(sum(home_prices)/len(home_prices), 2), "Avg")]
                            }
                        if away_prices:
                            all_markets[market_name_display]['Away'] = {
                                'max': [OddsPoint("Current", max(away_prices), "Max")],
                                'min': [OddsPoint("Current", min(away_prices), "Min")],
                                'avg': [OddsPoint("Current", round(sum(away_prices)/len(away_prices), 2), "Avg")]
                            }
                    print(f"   📊 解析 Asian Handicap {base_line_str}: Home={len(home_prices)}, Away={len(away_prices)} 莊家")
            
            print(f"   ✅ 解析完成: 共 {len(all_markets)} 個市場")
            return all_markets
            
        except Exception as e:
            print(f"   ⚠️ 解析赔率失敗: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def _find_popular_ah_line_grok(self, league_key: str, home: str, away: str) -> str | None:
        """
        使用 Grok API 搜尋找出熱門的亞洲讓球盤口
        
        返回格式如: "0", "-0.5", "-1", "-1.5", "-2" 等
        如果失敗返回 None
        """
        # === DEBUG LOGGING ===
        import json
        log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "id": "log_ah_start",
                "timestamp": 1733456789000,
                "location": "data_modules.py:_find_popular_ah_line_grok",
                "message": "Grok AH 分析開始",
                "data": {"league_key": league_key, "home": home, "away": away},
                "runId": "test-grok",
                "hypothesisId": "A"
            }) + "\n")
        # === END DEBUG ===
        
        try:
            # 嘗試導入 Grok 相關模組
            from src.llm_clients import llm
            
            # 構建搜尋問題
            search_query = f"{home} vs {away} Asian Handicap line odds"
            
            # 使用 Grok 的 web search 功能 (如果有的話)
            # 先嘗試直接問 LLM
            prompt = f"""你是足球博彩專家。請根據以下比賽，預測莊家最可能開出的亞洲讓球盤口(Asian Handicap)。

比賽: {home} vs {away}
聯賽: {league_key}

常見盤口:
- 0 (平手)
- -0.5 (半球)  
- -0.75 (讓半一)
- -1 (一球)
- -1.5 (球半)
- -2 (兩球)

請根據兩隊實力差距，猜測莊家最可能開出的主隊讓球盤口。
只回答盤口數字，例如: -1 或 0 或 -0.5
不要回答其他文字。"""
            
            print(f"   🔍 使用 Grok 分析熱門盤口...")
            
            # 嘗試使用 LLM
            try:
                response = llm.chat.completions.create(
                    model="grok-2-1212",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=10,
                )
                answer = response.choices[0].message.content.strip()
                
                # 解析答案
                import re
                match = re.search(r'-?\d+\.?\d*', answer)
                if match:
                    line = match.group()
                    # 標準化格式
                    if line == '0':
                        # === DEBUG LOGGING ===
                        import json
                        log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({
                                "id": "log_ah_success",
                                "timestamp": 1733456789001,
                                "location": "data_modules.py:_find_popular_ah_line_grok",
                                "message": "Grok AH 分析成功",
                                "data": {"result": "0"},
                                "runId": "test-grok",
                                "hypothesisId": "A"
                            }) + "\n")
                        # === END DEBUG ===
                        return '0'
                    elif line == '-0':
                        # === DEBUG LOGGING ===
                        import json
                        log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({
                                "id": "log_ah_success",
                                "timestamp": 1733456789001,
                                "location": "data_modules.py:_find_popular_ah_line_grok",
                                "message": "Grok AH 分析成功",
                                "data": {"result": "0"},
                                "runId": "test-grok",
                                "hypothesisId": "A"
                            }) + "\n")
                        # === END DEBUG ===
                        return '0'
                    else:
                        # === DEBUG LOGGING ===
                        import json
                        log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({
                                "id": "log_ah_success",
                                "timestamp": 1733456789001,
                                "location": "data_modules.py:_find_popular_ah_line_grok",
                                "message": "Grok AH 分析成功",
                                "data": {"result": line},
                                "runId": "test-grok",
                                "hypothesisId": "A"
                            }) + "\n")
                        # === END DEBUG ===
                        return line
                        
            except Exception as grok_err:
                print(f"   ⚠️ Grok API 失敗: {str(grok_err)[:30]}")
                raise grok_err
                
        except ImportError:
            print("   ⚠️ 無法導入 LLM 模組")
        except Exception as e:
            print(f"   ⚠️ Grok 搜尋失敗: {str(e)[:30]}")
        
        # 如果失敗，返回 None，使用預設盤口
        # === DEBUG LOGGING ===
        import json
        log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "id": "log_ah_fail",
                "timestamp": 1733456789002,
                "location": "data_modules.py:_find_popular_ah_line_grok",
                "message": "Grok AH 分析失敗，返回 None",
                "data": {},
                "runId": "test-grok",
                "hypothesisId": "A"
            }) + "\n")
        # === END DEBUG ===
        return None
    
    def _find_popular_ou_line_grok(self, league_key: str, home: str, away: str) -> str | None:
        """
        使用 Grok API 搜尋找出熱門的大小球盤口 (Over/Under)
        
        返回格式如: "2.5", "3.5", "2", "3" 等
        如果失敗返回 None
        """
        # === DEBUG LOGGING ===
        import json
        log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "id": "log_ou_start",
                "timestamp": 1733456789010,
                "location": "data_modules.py:_find_popular_ou_line_grok",
                "message": "Grok OU 分析開始",
                "data": {"league_key": league_key, "home": home, "away": away},
                "runId": "test-grok",
                "hypothesisId": "B"
            }) + "\n")
        # === END DEBUG ===
        
        try:
            from src.llm_clients import llm
            
            prompt = f"""你是足球博彩專家。請根據以下比賽，預測莊家最可能開出的大小球盤口(Over/Under)。

比賽: {home} vs {away}
聯賽: {league_key}

常見盤口:
- 2.5 (最常見)
- 3.5 
- 2.0
- 3.0

請根據兩隊的進攻/防守能力，猜測莊家最可能開出的大小球盤口。
只回答盤口數字，例如: 2.5 或 3.5
不要回答其他文字。"""
            
            try:
                response = llm.chat.completions.create(
                    model="grok-2-1212",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=10,
                )
                answer = response.choices[0].message.content.strip()
                
                # 解析答案
                import re
                match = re.search(r'\d+\.?\d*', answer)
                if match:
                    result = match.group()
                    # === DEBUG LOGGING ===
                    import json
                    log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "id": "log_ou_success",
                            "timestamp": 1733456789011,
                            "location": "data_modules.py:_find_popular_ou_line_grok",
                            "message": "Grok OU 分析成功",
                            "data": {"result": result},
                            "runId": "test-grok",
                            "hypothesisId": "B"
                        }) + "\n")
                    # === END DEBUG ===
                    return result
                        
            except Exception as grok_err:
                print(f"   ⚠️ Grok API 失敗: {str(grok_err)[:30]}")
                raise grok_err
                
        except ImportError:
            print("   ⚠️ 無法導入 LLM 模組")
        except Exception as e:
            print(f"   ⚠️ Grok 搜尋失敗: {str(e)[:30]}")
        
        # 如果失敗，返回 None，使用預設盤口
        # === DEBUG LOGGING ===
        import json
        log_path = r"c:\Users\Ryan\python\.vscode\fb_ai_bets\.cursor\debug.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "id": "log_ou_fail",
                "timestamp": 1733456789012,
                "location": "data_modules.py:_find_popular_ou_line_grok",
                "message": "Grok OU 分析失敗，返回 None",
                "data": {},
                "runId": "test-grok",
                "hypothesisId": "B"
            }) + "\n")
        # === END DEBUG ===
        return None
    
    def _process_oh_response(self, match_data: dict) -> OddsDataStructure:
        """
        將 OddsHarvester 輸出轉換為標準格式
        """
        all_markets = {}
        
        # 遍歷所有市場數據
        # OddsHarvester 返回的格式可能是多層嵌套的
        # 需要從 match_data 中提取市場赔率
        
        # 先嘗試直接提取市場數據
        markets_data = match_data.get('markets', {})
        
        if not markets_data:
            # 嘗試其他可能的鍵
            for key in match_data.keys():
                if isinstance(match_data[key], dict):
                    markets_data = match_data[key]
                    break
        
        home_team = match_data.get('home_team', '')
        away_team = match_data.get('away_team', '')
        
        temp_data = {}
        
        # 處理市場數據
        for market_key, market_value in markets_data.items():
            if not isinstance(market_value, dict):
                continue
            
            # 處理 1x2 市場
            if '1x2' in market_key.lower() or market_key == '1x2':
                # 嘗試提取主客和赔率
                odds_values = market_value.get('odds', [])
                if isinstance(odds_values, list) and len(odds_values) >= 3:
                    # 假設順序是 主, 和, 客
                    home_odds = self._extract_odds_value(odds_values[0])
                    draw_odds = self._extract_odds_value(odds_values[1]) if len(odds_values) > 1 else None
                    away_odds = self._extract_odds_value(odds_values[2]) if len(odds_values) > 2 else None
                    
                    if home_odds:
                        temp_data.setdefault('1x2', {})['Home'] = [home_odds]
                    if draw_odds:
                        temp_data.setdefault('1x2', {})['Draw'] = [draw_odds]
                    if away_odds:
                        temp_data.setdefault('1x2', {})['Away'] = [away_odds]
                else:
                    # 嘗試從 avg_odds 提取
                    avg_odds = market_value.get('avg_odds') or market_value.get('average')
                    if avg_odds:
                        if isinstance(avg_odds, list) and len(avg_odds) >= 3:
                            temp_data.setdefault('1x2', {})['Home'] = [self._extract_odds_value(avg_odds[0])]
                            temp_data.setdefault('1x2', {})['Draw'] = [self._extract_odds_value(avg_odds[1])]
                            temp_data.setdefault('1x2', {})['Away'] = [self._extract_odds_value(avg_odds[2])]
            
            # 處理 Over/Under 市場
            elif 'over' in market_key.lower() or 'under' in market_key.lower() or 'total' in market_key.lower():
                # 提取盤口
                line = self._extract_line(market_key)
                odds_over = market_value.get('odds_over') or market_value.get('over')
                odds_under = market_value.get('odds_under') or market_value.get('under')
                
                if odds_over or odds_under:
                    market_name = f"Over/Under {line}"
                    if odds_over:
                        temp_data.setdefault(market_name, {})['Over'] = [self._extract_odds_value(odds_over)]
                    if odds_under:
                        temp_data.setdefault(market_name, {})['Under'] = [self._extract_odds_value(odds_under)]
            
            # 處理 Asian Handicap 市場
            elif 'asian' in market_key.lower() or 'handicap' in market_key.lower():
                line = self._extract_line(market_key)
                odds_home = market_value.get('odds_home') or market_value.get('home')
                odds_away = market_value.get('odds_away') or market_value.get('away')
                
                if odds_home or odds_away:
                    market_name = f"Asian Handicap {line}"
                    if odds_home:
                        temp_data.setdefault(market_name, {})['Home'] = [self._extract_odds_value(odds_home)]
                    if odds_away:
                        temp_data.setdefault(market_name, {})['Away'] = [self._extract_odds_value(odds_away)]
        
        # 如果沒有找到市場數據，嘗試直接遍歷
        if not temp_data:
            # 遍歷所有鍵值對
            for key, value in match_data.items():
                if isinstance(value, (int, float)) and key != 'home_score' and key != 'away_score':
                    # 可能是直接的赔率值
                    pass
        
        # 轉換為標準格式
        for m_name, selections in temp_data.items():
            market_stats = {}
            for s_name, prices in selections.items():
                if prices and prices[0]:
                    price_val = prices[0]
                    market_stats[s_name] = {
                        'max': [OddsPoint("Current", price_val, "Max")],
                        'min': [OddsPoint("Current", price_val, "Min")],
                        'avg': [OddsPoint("Current", price_val, "Avg")]
                    }
            if market_stats:
                all_markets[m_name] = market_stats
        
        return all_markets
    
    def _extract_odds_value(self, odds) -> float:
        """從各種格式中提取赔率值"""
        if odds is None:
            return 0.0
        if isinstance(odds, (int, float)):
            return float(odds)
        if isinstance(odds, str):
            try:
                return float(odds)
            except:
                return 0.0
        if isinstance(odds, dict):
            # 嘗試從 dict 中提取
            return odds.get('odds') or odds.get('avg') or odds.get('price') or 0.0
        return 0.0
    
    def _extract_line(self, market_key: str) -> str:
        """從市場名稱中提取盤口"""
        import re
        # 嘗試匹配數字
        match = re.search(r'[\d.]+', market_key)
        if match:
            return match.group()
        return "2.5"


class OddsAnalyzer:
    def analyze_movement(self, h): return {}