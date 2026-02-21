# OddsHarvester 批量爬蟲

## 目錄結構

```
TakeData/
├── odds_batch_scraper.py   (主程序)
├── odds_scraper.spec       (PyInstaller 配置)
├── setup.bat               (首次運行設置)
├── OddsHarvester/          (爬蟲核心代碼)
│   ├── src/
│   ├── pyproject.toml
│   └── .venv/              (運行 setup.bat 後創建)
└── data/                   (數據輸出目錄，運行後自動創建)
    └── odds/
```

## 首次運行設置

1. 雙擊 setup.bat - 這會自動：
   - 檢查 Python 3.12+ 是否安裝
   - 創建虛擬環境
   - 安裝依賴 (beautifulsoup4, playwright, etc.)
   - 安裝 Playwright 瀏覽器

## 使用方法

```powershell
# 爬取所有聯賽 + 杯賽 (所有市場)
python odds_batch_scraper.py --all

# 爬取單個聯賽
python odds_batch_scraper.py --league england-premier-league --season 2024-2025

# 使用完整市場 (所有 over/under 和 asian_handicap 盤口)
python odds_batch_scraper.py --all --full-markets

# 查看所有參數
python odds_batch_scraper.py --help
```

## 支持的聯賽

| 聯賽 | Key |
|------|-----|
| 英超 | england-premier-league |
| 西甲 | spain-laliga |
| 意甲 | italy-serie-a |
| 德甲 | germany-bundesliga |
| 法甲 | france-ligue-1 |
| J1聯賽 (日本) | japan-j1-league |
| J2聯賽 (日本) | japan-j2-league |
| K聯賽1 (韓國, 2018+) | south-korea-k-league-1 |
| K聯賽經典 (韓國, 2017及之前) | south-korea-k-league-classic |
| K聯賽2 (韓國) | south-korea-k-league-2 |
| A聯賽 (澳洲) | australia-a-league |

## 支持的杯賽

- UEFA Champions League (歐冠)
- UEFA Europa League (歐聯)
- UEFA Europa Conference League (歐會杯)
- FA Cup (英格蘭足總杯)
- EFL Cup / Capital One Cup (英格蘭聯賽杯)
- Copa del Rey (西班牙國王杯)
- Coppa Italia (意大利杯)
- DFB-Pokal (德國杯)
- Coupe de France (法國杯)
- AFC Champions League (亞冠)
- Emperor's Cup (日本天皇杯)
- J.League Cup (日本聯賽杯)
- Korean FA Cup (韓國足總杯)
- Australia Cup (澳洲杯)

## 支持的市場

### 默認市場
- 1x2 - 全場獨贏
- over_under_2_5 - 大小球 2.5
- asian_handicap_0 - 亞洲讓分盤 0

### 完整市場 (--full-markets)
- 1x2 - 全場獨贏
- over_under_0_5 到 over_under_5_5 - 大小球 (12個盤口)
- asian_handicap_-2 到 asian_handicap_+2 - 亞洲讓分盤 (10個盤口)

## 數據輸出

數據會保存在 data/odds/ 目錄下，文件名格式：
odds_{league}_{season}_{market}.csv

## 數據範圍

- 時間範圍: 2015-2016 賽季至今
- 聯賽: 五大聯賽 + J1 + J2 + K League + A-League
- 杯賽: 歐冠、歐聯、各國杯賽、亞冠等
