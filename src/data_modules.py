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

class OddsAnalyzer:
    def analyze_movement(self, h): return {}