import requests
import json
import time
import os
from datetime import datetime
import difflib

class FotMobLineupHarvester:
    def __init__(self, match_id=None):
        self.match_id = match_id
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.fotmob.com/"
        }
        if match_id:
            self.api_url = f"https://www.fotmob.com/api/matchDetails?matchId={match_id}"
        else:
            self.api_url = None

    @staticmethod
    def search_match_id(home_team, away_team, league_key=None):
        """
        搜索比賽 ID
        Args:
            home_team: 主隊名稱
            away_team: 客隊名稱
            league_key: 聯賽代碼 (可選)
        Returns:
            match_id (str) 或 None
        """
        try:
            search_url = "https://www.fotmob.com/api/searchAll"
            search_query = f"{home_team} {away_team}"
            
            params = {
                "query": search_query,
                "type": "match"
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.fotmob.com/"
            }
            
            print(f"🔍 正在搜索比賽: {home_team} vs {away_team}...")
            response = requests.get(search_url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                matches = data.get('matches', [])
                
                if matches:
                    # 尋找最相符的比賽
                    best_match = None
                    best_score = 0
                    
                    for match in matches:
                        home = match.get('home', {}).get('name', '').lower()
                        away = match.get('away', {}).get('name', '').lower()
                        
                        home_input = home_team.lower()
                        away_input = away_team.lower()
                        
                        # 計算相似度
                        home_score = difflib.SequenceMatcher(None, home_input, home).ratio()
                        away_score = difflib.SequenceMatcher(None, away_input, away).ratio()
                        total_score = (home_score + away_score) / 2
                        
                        if total_score > best_score:
                            best_score = total_score
                            best_match = match
                    
                    if best_match and best_score > 0.6:
                        match_id = best_match.get('id')
                        print(f"✅ 找到比賽: {best_match.get('home', {}).get('name')} vs {best_match.get('away', {}).get('name')} (ID: {match_id})")
                        return str(match_id)
                    else:
                        print(f"⚠️ 未找到相符的比賽")
                        return None
                else:
                    print(f"⚠️ 搜索無結果")
                    return None
            else:
                print(f"❌ 搜索 API 失敗: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"⚠️ 搜索錯誤: {e}")
            return None

    def fetch_data(self):
        try:
            print(f"📡 正在請求比賽數據 (ID: {self.match_id})...")
            response = requests.get(self.api_url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ API 請求失敗: {response.status_code}")
                return None
        except Exception as e:
            print(f"⚠️ 連線錯誤: {e}")
            return None

    def parse_lineup(self, raw_data):
        try:
            content = raw_data.get('content', {})
            lineup_root = content.get('lineup', {})

            if not lineup_root or 'homeTeam' not in lineup_root:
                return None

            def extract_players(team_data):
                players = []
                starters = team_data.get('starters', [])
                for p in starters:
                    players.append({
                        "id": p.get('id'),
                        "name": p.get('name'),
                        "number": p.get('shirtNumber'),
                        "position_id": p.get('positionId'),
                        "rating": p.get('performance', {}).get('rating', None)
                    })
                return players

            parsed_result = {
                "match_id": self.match_id,
                "match_time": raw_data.get('general', {}).get('matchTimeUTC'),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "home_team": {
                    "name": lineup_root['homeTeam']['name'],
                    "id": lineup_root['homeTeam']['id'],
                    "formation": lineup_root['homeTeam'].get('formation'),
                    "starters": extract_players(lineup_root['homeTeam']),
                    "coach": lineup_root['homeTeam'].get('coach', {}).get('name')
                },
                "away_team": {
                    "name": lineup_root['awayTeam']['name'],
                    "id": lineup_root['awayTeam']['id'],
                    "formation": lineup_root['awayTeam'].get('formation'),
                    "starters": extract_players(lineup_root['awayTeam']),
                    "coach": lineup_root['awayTeam'].get('coach', {}).get('name')
                }
            }

            if not parsed_result['home_team']['starters']:
                return None

            return parsed_result

        except Exception as e:
            print(f"❌ 解析數據時發生錯誤: {e}")
            return None

    def fetch_lineup(self, save_to_file=True):
        """
        直接爬取陣容數據
        Args:
            save_to_file: 是否保存到文件
        Returns:
            parsed_lineup (dict) 或 None
        """
        raw_data = self.fetch_data()
        
        if not raw_data:
            return None
        
        if 'general' not in raw_data:
            print("⚠️ API 回傳無效或 Match ID 錯誤")
            return None
        
        clean_lineup = self.parse_lineup(raw_data)
        
        if clean_lineup and save_to_file:
            save_folder = r"C:\Users\Ryan\python\.vscode\fb_ai_bets\data\lineup"
            
            if not os.path.exists(save_folder):
                try:
                    os.makedirs(save_folder)
                    print(f"📁 已建立資料夾: {save_folder}")
                except OSError as e:
                    print(f"❌ 無法建立資料夾: {e}")
                    return clean_lineup
            
            home_name = clean_lineup['home_team']['name']
            away_name = clean_lineup['away_team']['name']
            
            safe_home = home_name.replace(" ", "_")
            safe_away = away_name.replace(" ", "_")
            filename = f"lineup_{safe_home}_vs_{safe_away}.json"
            full_path = os.path.join(save_folder, filename)
            
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(clean_lineup, f, ensure_ascii=False, indent=4)
            
            print(f"💾 檔案已保存至: {full_path}")
        
        return clean_lineup

    def run(self, interval=60):
        print(f"🚀 啟動監控 (Match ID: {self.match_id})，每 {interval} 秒檢查一次...")
        
        # --- 設定存檔資料夾 ---
        # 直接指定絕對路徑，最穩當
        save_folder = r"C:\Users\Ryan\python\.vscode\fb_ai_bets\data"
        
        # 如果資料夾不存在，自動建立 (避免報錯)
        if not os.path.exists(save_folder):
            try:
                os.makedirs(save_folder)
                print(f"📁 已建立資料夾: {save_folder}")
            except OSError as e:
                print(f"❌ 無法建立資料夾: {e}")
                return

        while True:
            raw_data = self.fetch_data()
            
            if raw_data:
                if 'general' not in raw_data:
                    print("⚠️ API 回傳無效或 Match ID 錯誤")
                    break

                clean_lineup = self.parse_lineup(raw_data)

                if clean_lineup:
                    home_name = clean_lineup['home_team']['name']
                    away_name = clean_lineup['away_team']['name']
                    
                    print(f"\n✅ 陣容已公布！ {home_name} vs {away_name}")
                    
                    # --- 修正後的路徑組合 ---
                    # 1. 處理檔名中的空白 (建議轉為底線，雖然 Windows 支援空白但底線較好處理)
                    safe_home = home_name.replace(" ", "_")
                    safe_away = away_name.replace(" ", "_")
                    filename = f"lineup_{safe_home}_vs_{safe_away}.json"
                    
                    # 2. 組合 資料夾 + 檔名
                    full_path = os.path.join(save_folder, filename)

                    with open(full_path, 'w', encoding='utf-8') as f:
                        json.dump(clean_lineup, f, ensure_ascii=False, indent=4)
                    
                    print(f"💾 檔案已保存至: {full_path}")
                    print("🎉 任務完成，程式結束。")
                    break 
                else:
                    current_time = datetime.now().strftime('%H:%M:%S')
                    print(f"⏳ [{current_time}] 陣容尚未公布，等待中...")
            
            time.sleep(interval)

if __name__ == "__main__":
    
    MATCH_ID = "4813595"  # 替換為您想監控的比賽 ID
    
    bot = FotMobLineupHarvester(MATCH_ID)
    bot.run(interval=60)