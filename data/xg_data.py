import requests
import json
import pandas as pd
import re
import time
import os
import codecs
from bs4 import BeautifulSoup

# 設定五大聯賽與年份
# Understat 的年份是起始年，例如 2023 代表 2023-24 賽季
LEAGUES = ['EPL', 'La_liga', 'Bundesliga', 'Serie_A', 'Ligue_1']
YEARS = [2019, 2020, 2021, 2022, 2023]

BASE_URL = "https://understat.com"

# 偽裝成瀏覽器，減少被封鎖機率
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def decode_json(json_str):
    """解析 Understat 網頁中的壓縮 JSON 字串"""
    try:
        # Understat 的 JSON 通常用 unicode_escape 編碼
        decoded = codecs.decode(json_str, 'unicode_escape')
        return json.loads(decoded)
    except Exception as e:
        print(f"JSON 解析失敗: {e}")
        return None

def get_match_ids(league, year):
    """取得特定聯賽與賽季的所有比賽 ID"""
    url = f"{BASE_URL}/league/{league}/{year}"
    print(f"正在獲取賽程: {url}")
    
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            print(f"無法存取頁面 (Code {response.status_code})")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        scripts = soup.find_all('script')
        
        # 尋找包含 datesData 的 script
        for script in scripts:
            if script.string and 'datesData' in script.string:
                match = re.search(r"JSON\.parse\('([^']+)'\)", script.string)
                if match:
                    data = decode_json(match.group(1))
                    # 篩選出已結束的比賽 (isResult = True)
                    ids = [m['id'] for m in data if m['isResult']]
                    return ids
        return []
    except Exception as e:
        print(f"獲取賽程錯誤: {e}")
        return []

def get_shots_data(match_id):
    """進入單場比賽頁面，抓取詳細射門數據 (含 X,Y)"""
    url = f"{BASE_URL}/match/{match_id}"
    
    try:
        response = requests.get(url, headers=HEADERS)
        soup = BeautifulSoup(response.content, 'html.parser')
        scripts = soup.find_all('script')
        
        for script in scripts:
            if script.string and 'shotsData' in script.string:
                match = re.search(r"JSON\.parse\('([^']+)'\)", script.string)
                if match:
                    data = decode_json(match.group(1))
                    # data 包含 'h' (主隊) 和 'a' (客隊) 的射門
                    shots_list = []
                    for side in ['h', 'a']:
                        for shot in data[side]:
                            shot['match_id'] = match_id
                            shot['side'] = 'home' if side == 'h' else 'away'
                            shots_list.append(shot)
                    return shots_list
        return []
    except Exception as e:
        print(f"   - Match {match_id} 抓取失敗: {e}")
        return []

def main():
    all_shots = []
    
    print("🚀 開始直接抓取 Understat (不使用 soccerdata 庫)")
    
    for league in LEAGUES:
        for year in YEARS:
            print(f"\nProcessing {league} {year}-{year+1}...")
            
            # 1. 取得該賽季所有比賽 ID
            match_ids = get_match_ids(league, year)
            print(f"   -> 找到 {len(match_ids)} 場比賽")
            
            # 測試模式：每個賽季只抓前 5 場 (若要抓全部，請註解掉下面這行)
            # match_ids = match_ids[:5] 
            
            # 2. 逐場抓取射門數據
            for idx, mid in enumerate(match_ids):
                # 顯示進度
                if idx % 10 == 0:
                    print(f"   Scraping match {idx+1}/{len(match_ids)} (ID: {mid})...")
                
                shots = get_shots_data(mid)
                
                # 補上聯賽與賽季資訊
                for s in shots:
                    s['league'] = league
                    s['season'] = f"{year}-{year+1}"
                
                all_shots.extend(shots)
                
                # 重要：暫停一下，避免被封鎖
                time.sleep(0.5) 

    # 3. 轉存 JSON
    print(f"\n✅ 抓取完成！共收集 {len(all_shots)} 筆射門數據。")
    df = pd.DataFrame(all_shots)
    
    # 確保數據包含 X, Y, xG
    if not df.empty:
        output_file = "data/understat_direct_shots.json"
        os.makedirs("data", exist_ok=True)
        df.to_json(output_file, orient='records', force_ascii=False, indent=4)
        print(f"檔案已儲存至: {output_file}")
        print("數據包含欄位:", df.columns.tolist())
    else:
        print("⚠️ 未抓取到任何數據，請檢查網路連線。")

if __name__ == "__main__":
    main()