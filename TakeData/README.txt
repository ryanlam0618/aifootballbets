# 將整個 OddsHarvester 文件夾複製到此目錄
# 確保目錄結構如下：
#
# TakeData/
# ├── odds_batch_scraper.py   (主程序)
# ├── setup.bat               (首次運行設置)
# ├── OddsHarvester/          (從 fb_ai_bets/OddsHarvester 複製過來)
# │   ├── src/
# │   ├── .venv/
# │   └── ...
# └── data/                   (數據輸出目錄，運行後自動創建)
#     └── odds/
#
# 使用方法：
# 1. 首次運行：雙擊 setup.bat
# 2. 運行爬蟲：
#    python odds_batch_scraper.py --all
#    python odds_batch_scraper.py --league england-premier-league --season 2024-2025
#    python odds_batch_scraper.py --league japan-j1-league --season 2024-2025
#    python odds_batch_scraper.py --league south-korea-k-league-1 --season 2024-2025
#
# 支持的聯賽：
#   - england-premier-league  (英超)
#   - spain-laliga           (西甲)
#   - italy-serie-a          (意甲)
#   - germany-bundesliga     (德甲)
#   - france-ligue-1        (法甲)
#   - japan-j1-league       (J1聯賽)
#   - south-korea-k-league-1 (K聯賽1, 2018+)
#   - south-korea-k-league-classic (K聯賽經典, 2017及之前)
#   - australia-a-league    (澳洲A聯賽)
#
# 支持的市場：
#   - 1x2
#   - over_under_0.5 到 over_under_5.5
#   - asian_handicap_-2 到 asian_handicap_+2
