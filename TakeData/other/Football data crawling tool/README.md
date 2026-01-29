# A-League Data Crawler

澳職(A-League)足球比賽數據爬蟲 - 從2022年11月8日至24-25賽季

## 功能特點

1. **球隊數據** - CSV格式，按比賽時間排序
2. **球員數據** - JSON格式，一個球員一個檔案
3. **球員數據包含四大類別**:
   - 常规 (Regular)
   - 進攻 (Attacking)
   - 防守 (Defensive)
   - 傳球 (Passing)

## 安裝依賴

```bash
cd c:\Users\Ryan\Documents\data\football
pip install -r requirements.txt
```

## 使用方法

```bash
python aleague_crawler.py
```

## 輸出結構

```
aleague_data_output/
├── teams/
│   └── aleague_matches.csv    # 球隊比賽數據
└── players/
    ├── John_Smith_Macarthur_20231108.json
    ├── Tom_Jones_Wellington_20231108.json
    └── ...
```

---

## 📊 CSV 輸出格式 (球隊數據)

參考 `data/big_five_history.csv` 格式，**無賠率**，英文欄位名稱：

| 欄位 | 說明 | 範例 |
|------|------|------|
| Div | 聯賽名稱 | A-League |
| Date | 比賽日期 | 2023-11-08 |
| Time | 比賽時間 | 16:45 |
| HomeTeam | 主隊名稱 | Melbourne City |
| AwayTeam | 客隊名稱 | Western Sydney |
| FTHG | 主隊全場進球 | 2 |
| FTAG | 客隊全場進球 | 1 |
| FTR | 全場結果 | H (主勝) / D (和) / A (客勝) |
| HTHG | 主隊半場進球 | 1 |
| HTAG | 客隊半場進球 | 0 |
| HTR | 半場結果 | H / D / A |
| Referee | 裁判名稱 | |
| HS | 主隊射門次數 | 15 |
| AS | 客隊射門次數 | 8 |
| HST | 主隊射正次數 | 6 |
| AST | 客隊射正次數 | 3 |
| HF | 主隊犯規次數 | 12 |
| AF | 客隊犯規次數 | 14 |
| HC | 主隊角球次數 | 5 |
| AC | 客隊角球次數 | 3 |
| HY | 主隊黃牌 | 2 |
| AY | 客隊黃牌 | 3 |
| HR | 主隊紅牌 | 0 |
| AR | 客隊紅牌 | 0 |
| Season | 賽季 | 2023-2024 |

---

## 📋 JSON 輸出格式 (球員數據)

基於墨爾本城數據格式，每個球員一個 JSON 檔案：

### 範例：墨爾本城 前鋒 Jamie Maclaren

```json
{
  "match_info": {
    "date": "2023-11-08",
    "home_team": "Melbourne City",
    "away_team": "Western Sydney",
    "score": "2-1",
    "season": "2023-2024"
  },
  "player_info": {
    "name": "Jamie Maclaren",
    "team": "Melbourne City",
    "number": "9",
    "position": "Forward",
    "rating": "8.2",
    "is_home": true
  },
  "regular": {
    "number": "9",
    "position": "Forward",
    "rating": "8.2",
    "key_events": "⚽ 45' 🔵 67' 🟨 78' ⬇️ 82'",
    "minutes_played": "82",
    "is_motm": "1",
    "substituted_in": "0",
    "substituted_out": "1"
  },
  "attacking": {
    "goals": "1",
    "assists": "1",
    "shots": "4",
    "shots_on_target": "3",
    "key_passes": "2",
    "big_chances_missed": "0",
    "shots_from_set_pieces": "1",
    "goals_from_open_play": "1",
    "penalties_scored": "0",
    "hit_woodwork": "0"
  },
  "defensive": {
    "tackles": "1",
    "interceptions": "0",
    "clearances": "2",
    "headed_clearances": "1",
    "blocks": "0",
    "aerial_duels_won": "3",
    "aerial_duels_lost": "2",
    "duels_won": "8",
    "duels_lost": "4",
    "fouls_committed": "2",
    "fouls_drawn": "3",
    "yellow_cards": "1",
    "red_cards": "0",
    "own_goals": "0",
    "errors_leading_to_goal": "0"
  },
  "passing": {
    "passes": "28",
    "passes_completed": "24",
    "pass_accuracy": "86",
    "key_passes": "2",
    "crosses": "1",
    "crosses_completed": "0",
    "through_balls": "0",
    "through_balls_completed": "0",
    "long_passes": "3",
    "long_passes_completed": "2",
    "short_passes": "25",
    "short_passes_completed": "22",
    "backward_passes": "5",
    "assists": "1",
    "second_assists": "0",
    "chances_created": "2"
  }
}
```

### Key Events 標記說明

| 標記 | 說明 | 範例 |
|------|------|------|
| ⚽ | 進球 | ⚽ 45' (45分鐘進球) |
| 🔵 | 助攻 | 🔵 67' (67分鐘助攻) |
| 🟨 | 黃牌 | 🟨 78' (78分鐘黃牌) |
| 🟥 | 紅牌 | 🟥 85' (85分鐘紅牌) |
| ⬆️ | 換上 | ⬆️ 60' (60分鐘替補上場) |
| ⬇️ | 換下 | ⬇️ 75' (75分鐘被換下) |
| ⭐ | 全場最佳 | ⭐ (MOTM) |

---

## 🏆 澳職球隊列表

| 中文名稱 | 英文名稱 |
|----------|----------|
| 墨爾本城 | Melbourne City |
| 悉尼FC | Sydney FC |
| 墨爾本勝利 | Melbourne Victory |
| 阿德萊德聯 | Adelaide United |
| 珀斯光榮 | Perth Glory |
| 布里斯班獅吼 | Brisbane Roar |
| 西悉尼流浪者 | Western Sydney Wanderers |
| 中央海岸水手 | Central Coast Mariners |
| 惠靈頓鳳凰 | Wellington Phoenix |
| 紐卡斯爾噴氣機 | Newcastle Jets |
| 麥克阿瑟 | Macarthur FC |

---

## ⚠️ 注意事項

1. 需要安裝 **Google Chrome** 瀏覽器
2. 爬取過程中會有隨機延時，模擬人類行為
3. 完整爬取可能需要數小時，請耐心等待
4. 可以隨時按 `Ctrl+C` 中斷，已爬取的數據會保存

---

## 🔧 自定義設置

修改 `main()` 函數中的日期範圍：

```python
def main():
    start_date = datetime(2022, 11, 8)  # 開始日期
    end_date = datetime(2025, 1, 24)    # 結束日期 (24-25賽季)
    
    crawler = ALeagueCrawler(output_dir="aleague_data_output")
    crawler.crawl(start_date, end_date)
```

---

## 📁 文件命名規則

### 球員 JSON 文件
```
球員名稱_球隊名稱_日期.json
例如: Jamie_Maclaren_Melbourne_City_20231108.json
```

### 球隊 CSV 文件
```
aleague_matches.csv
```

所有數據按 **比賽時間** 排序，方便後續分析！
