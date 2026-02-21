#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OddsHarvester Batch Scraper
==========================
用於批量爬取多個聯賽、賽季和市場的投注賠率數據

支持的聯賽:
- 五大聯賽: Premier League, LaLiga, Serie A, Bundesliga, Ligue 1
- J1 League (日本)
- K League 1 (韓國)
- A-League Men (澳洲)

支持的市場:
- 1x2 (全場獨贏)
- btts (雙方都進球)
- double_chance (雙重機會)
- dnb (draw_no_bet, 和局退款)
- over/under (大小球, 常用盤口)
- asian_handicap (亞洲讓分盤)

時間範圍: 2015-2016 賽季至今
"""

import os
import sys
import time
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ============== 配置 ==============

# 獲取腳本所在目錄（支持 exe 和 py 運行）
def get_script_dir():
    """獲取腳本所在目錄"""
    if getattr(sys, 'frozen', False):
        # 運行為 exe 時，使用 exe 所在目錄
        return os.path.dirname(sys.executable)
    else:
        # 運行為 py 時，使用腳本所在目錄
        return os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = get_script_dir()

# OddsHarvester 路徑配置
# pyinstaller 打包時: SCRIPT_DIR = dist/
# 開發時: SCRIPT_DIR = TakeData/
ODDS_HARVESTER_PATH = os.path.join(SCRIPT_DIR, "OddsHarvester")
ODDS_HARVESTER_VENV = os.path.join(ODDS_HARVESTER_PATH, ".venv", "Scripts", "python.exe")

# 檢查是否存在虛擬環境，如果不存在則使用系統 Python
if not os.path.exists(ODDS_HARVESTER_VENV):
    # 嘗試使用 OddsHarvester 目錄下的 python
    ODDS_HARVESTER_VENV = os.path.join(ODDS_HARVESTER_PATH, ".venv", "Scripts", "python.exe")
    # 如果還是不存在，嘗試系統 python
    if not os.path.exists(ODDS_HARVESTER_VENV):
        ODDS_HARVESTER_VENV = "python"

# 數據輸出目錄
OUTPUT_BASE_PATH = os.path.join(SCRIPT_DIR, "data", "odds")

# 起始賽季 (2015-2016賽季)
START_SEASON = "2015-2016"

# ============== 聯賽配置 ==============

# 五大聯賽 + A-League + J1 League + K League
LEAGUES = {
    # 五大聯賽
    "england-premier-league": {
        "name": "Premier League",
        "country": "England",
        "url_key": "england-premier-league",
    },
    "spain-laliga": {
        "name": "LaLiga",
        "country": "Spain", 
        "url_key": "spain-laliga",
    },
    "italy-serie-a": {
        "name": "Serie A",
        "country": "Italy",
        "url_key": "italy-serie-a",
    },
    "germany-bundesliga": {
        "name": "Bundesliga",
        "country": "Germany",
        "url_key": "germany-bundesliga",
    },
    "france-ligue-1": {
        "name": "Ligue 1",
        "country": "France",
        "url_key": "france-ligue-1",
    },
    # A-League Men (澳洲)
    "australia-a-league": {
        "name": "A-League Men",
        "country": "Australia",
        "url_key": "australia-a-league",
    },
    # J1 League (日本)
    "japan-j1-league": {
        "name": "J1 League",
        "country": "Japan",
        "url_key": "japan-j1-league",
    },
    # J2 League (日本)
    "japan-j2-league": {
        "name": "J2 League",
        "country": "Japan",
        "url_key": "japan-j2-league",
    },
    # K League Classic (2017及之前)
    "south-korea-k-league-classic": {
        "name": "K League Classic (2013-2017)",
        "country": "South Korea",
        "url_key": "south-korea-k-league-classic",
        "note": "2017及之前使用"
    },
    # K League 1 (2018起)
    "south-korea-k-league-1": {
        "name": "K League 1 (2018+)",
        "country": "South Korea",
        "url_key": "south-korea-k-league-1",
        "note": "2018年起使用"
    },
    # K League 2
    "south-korea-k-league-2": {
        "name": "K League 2",
        "country": "South Korea",
        "url_key": "south-korea-k-league-2",
    },
}

# 杯賽配置
# url_template 用於動態生成URL (包含賽季)
# latest_url 用於最新賽季
CUPS = {
    # 歐洲盃賽
    "champions-league": {
        "name": "UEFA Champions League",
        "url_key": "champions-league",
        "url_template": "https://www.oddsportal.com/football/europe/champions-league-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/europe/champions-league/results/",
    },
    "europa-league": {
        "name": "UEFA Europa League",
        "url_key": "europa-league",
        "url_template": "https://www.oddsportal.com/football/europe/europa-league-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/europe/europa-league/results/",
    },
    "europa-conference-league": {
        "name": "UEFA Europa Conference League",
        "url_key": "europa-conference-league",
        "url_template": "https://www.oddsportal.com/football/europe/europa-conference-league-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/europe/europa-conference-league/results/",
    },
    # 英格蘭杯賽
    "england-fa-cup": {
        "name": "FA Cup",
        "url_key": "england-fa-cup",
        "url_template": "https://www.oddsportal.com/football/england/fa-cup-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/england/fa-cup/results/",
    },
    "england-league-cup": {
        "name": "EFL Cup (Capital One Cup)",
        "url_key": "england-league-cup",
        "url_template": "https://www.oddsportal.com/football/england/capital-one-cup-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/england/efl-cup/results/",
    },
    # 西班牙杯賽
    "spain-copa-del-rey": {
        "name": "Copa del Rey",
        "url_key": "spain-copa-del-rey",
        "url_template": "https://www.oddsportal.com/football/spain/copa-del-rey-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/spain/copa-del-rey/results/",
    },
    # 意大利杯賽
    "italy-coppa-italia": {
        "name": "Coppa Italia",
        "url_key": "italy-coppa-italia",
        "url_template": "https://www.oddsportal.com/football/italy/coppa-italia-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/italy/coppa-italia/results/",
    },
    # 德國杯賽
    "germany-dfb-pokal": {
        "name": "DFB-Pokal",
        "url_key": "germany-dfb-pokal",
        "url_template": "https://www.oddsportal.com/football/germany/dfb-pokal-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/germany/dfb-pokal/results/",
    },
    # 法國杯賽
    "france-coupe-de-france": {
        "name": "Coupe de France",
        "url_key": "france-coupe-de-france",
        "url_template": "https://www.oddsportal.com/football/france/coupe-de-france-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/france/coupe-de-france/results/",
    },
    "france-coupe-de-la-ligue": {
        "name": "Coupe de la Ligue",
        "url_key": "france-coupe-de-la-ligue",
        "url_template": "https://www.oddsportal.com/football/france/coupe-de-la-ligue-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/france/coupe-de-la-ligue/results/",
    },
    # 亞洲杯賽
    "afc-champions-league": {
        "name": "AFC Champions League",
        "url_key": "afc-champions-league",
        "url_template": "https://www.oddsportal.com/football/asia/afc-champions-league-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/asia/afc-champions-league/results/",
    },
    "japan-emperors-cup": {
        "name": "Emperor's Cup",
        "url_key": "japan-emperors-cup",
        "url_template": "https://www.oddsportal.com/football/japan/emperors-cup-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/japan/emperors-cup/results/",
    },
    "japan-league-cup": {
        "name": "J.League Cup",
        "url_key": "japan-league-cup",
        "url_template": "https://www.oddsportal.com/football/japan/j-league-cup-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/japan/j-league-cup/results/",
    },
    "south-korea-fa-cup": {
        "name": "Korean FA Cup",
        "url_key": "south-korea-fa-cup",
        "url_template": "https://www.oddsportal.com/football/south-korea/fa-cup-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/south-korea/fa-cup/results/",
    },
    # 澳洲杯賽
    "australia-fa-cup": {
        "name": "Australia Cup",
        "url_key": "australia-fa-cup",
        "url_template": "https://www.oddsportal.com/football/australia/fa-cup-{season}/results/",
        "latest_url": "https://www.oddsportal.com/football/australia/fa-cup/results/",
    },
}

# ============== 市場類型配置 ==============

# 足球市場類型
MARKETS = [
    # 主要市場
    "1x2",           # 全場獨贏
    
    # Over/Under (大小球) - 常用盤口
    "over_under_0_5",
    "over_under_1",
    "over_under_1_5",
    "over_under_2",
    "over_under_2_5",  # 最常用
    "over_under_3",
    "over_under_3_5",
    "over_under_4",
    "over_under_4_5",
    "over_under_5",
    "over_under_5_5",
    
    # Asian Handicap (亞洲讓分盤) - 常用盤口
    "asian_handicap_-2",
    "asian_handicap_-1_5",
    "asian_handicap_-1",
    "asian_handicap_-0_75",
    "asian_handicap_-0_5",
    "asian_handicap_0",
    "asian_handicap_+0_5",
    "asian_handicap_+1",
    "asian_handicap_+1_5",
    "asian_handicap_+2",
]

# 精簡市場 (用於調試或快速測試)
MARKETS_SHORT = [
    "1x2",
    "over_under_2_5",
    "asian_handicap_0",
]

# ============== 輔助函數 ==============

def setup_logging(log_dir: str) -> logging.Logger:
    """設置日誌"""
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, f"odds_harvester_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def generate_seasons(start_season: str) -> List[str]:
    """
    生成從起始賽季到當前賽季的所有賽季列表
    
    Args:
        start_season: 起始賽季格式 "YYYY-YYYY"
    
    Returns:
        賽季列表
    """
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # 確定當前賽季 (8月-次年5月為一個賽季)
    if current_month >= 8:
        current_season_start = current_year
    else:
        current_season_start = current_year - 1
    
    # 解析起始賽季
    start_year = int(start_season.split("-")[0])
    
    seasons = []
    for year in range(start_year, current_season_start + 1):
        seasons.append(f"{year}-{year + 1}")
    
    return seasons


def get_league_url(league_key: str) -> str:
    """獲取聯賽的URL"""
    league = LEAGUES.get(league_key)
    if not league:
        return None
    
    # 如果有自定義URL，使用自定義URL
    if "custom_url" in league:
        return league["custom_url"]
    
    # 否則使用預設的URL格式
    return f"https://www.oddsportal.com/football/{league['country'].lower()}/{league['url_key']}"


def get_cup_url(cup_key: str) -> str:
    """獲取杯賽的URL"""
    cup = CUPS.get(cup_key)
    if not cup:
        return None
    return cup.get("custom_url")


def build_output_filename(league_key: str, season: str, market: str) -> str:
    """構建輸出文件名"""
    safe_league = league_key.replace("-", "_")
    safe_market = market.replace("-", "_").replace(".", "_")
    return f"odds_{safe_league}_{season}_{safe_market}.csv"


def run_odds_harvester(
    league_key: str,
    season: str,
    markets: List[str],
    output_dir: str,
    headless: bool = True,
    concurrency: int = 5,
    scrape_history: bool = True,
    use_preview_mode: bool = False,
    log_logger: Optional[logging.Logger] = None
) -> Tuple[bool, str]:
    """
    運行 OddsHarvester 爬取數據
    
    Args:
        league_key: 聯賽 key
        season: 賽季 (如 "2015-2016")
        markets: 市場列表
        output_dir: 輸出目錄
        headless: 是否使用無頭模式
        concurrency: 並發任務數
        scrape_history: 是否爬取歷史賠率
        use_preview_mode: 是否使用預覽模式 (更快)
        log_logger: 日誌記錄器
    
    Returns:
        (是否成功, 輸出文件路徑)
    """
    logger = log_logger or logging.getLogger(__name__)
    
    # 獲取聯賽URL
    league_url = get_league_url(league_key)
    if not league_url:
        logger.error(f"無法獲取聯賽 URL: {league_key}")
        return False, ""
    
    # 構建市場參數
    markets_str = ",".join(markets)
    
    # 構建輸出文件路徑 (不使用tmp，避免擴展名問題)
    output_file = os.path.join(output_dir, build_output_filename(league_key, season, markets[0]))
    
    # 構建命令 - 注意: file_path 必須是 .csv 結尾
    cmd = [
        ODDS_HARVESTER_VENV,
        "-m", "src.main",
        "scrape_historic",
        "--sport", "football",
        "--leagues", league_key,
        "--season", season,
        "--markets", markets_str,
        "--format", "csv",
        "--file_path", output_file,  # 直接使用最終路徑
        "--concurrency_tasks", str(concurrency),
    ]
    
    if headless:
        cmd.append("--headless")
    
    if scrape_history:
        cmd.append("--scrape_odds_history")
    
    # 不使用 --preview_submarkets_only，獲取完整歷史數據
    
    # 設置環境變量
    env = os.environ.copy()
    env["PYTHONPATH"] = ODDS_HARVESTER_PATH
    env["PYTHONUNBUFFERED"] = "1"
    # 設置編碼避免Windows中文編碼問題
    env["PYTHONIOENCODING"] = "utf-8"
    
    logger.info(f"開始爬取: {league_key} - {season}, 市場: {markets_str}")
    logger.info(f"命令: {' '.join(cmd)}")
    
    try:
        # 執行命令 - 使用 utf-8 編碼
        result = subprocess.run(
            cmd,
            env=env,
            cwd=ODDS_HARVESTER_PATH,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',  # 忽略無法解碼的字元
            timeout=10800  # 3小時超時
        )
        
        if result.returncode == 0:
            # 檢查輸出文件是否存在
            if os.path.exists(output_file):
                # 讀取文件檢查是否有有效數據
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if content and len(content) > 100:  # 有實際數據
                            logger.info(f"✅ 成功: {league_key} - {season}")
                            return True, output_file
                except Exception as e:
                    logger.warning(f"⚠️ 讀取文件失敗: {e}")
            
            # 如果文件不存在或沒有數據
            logger.warning(f"⚠️ 命令執行成功但未生成輸出文件: {league_key}")
            return True, output_file
        else:
            logger.error(f"❌ 失敗: {league_key} - {season}")
            logger.error(f"錯誤輸出: {result.stderr[:500]}")
            return False, ""
            
    except subprocess.TimeoutExpired:
        logger.error(f"❌ 超時: {league_key} - {season}")
        return False, ""
    except Exception as e:
        logger.error(f"❌ 異常: {league_key} - {season}, 錯誤: {str(e)}")
        return False, ""


def run_odds_harvester_by_url(
    url: str,
    season: str,
    markets: List[str],
    output_dir: str,
    league_name: str = "custom",
    headless: bool = True,
    concurrency: int = 5,
    scrape_history: bool = True,
    use_preview_mode: bool = False,
    log_logger: Optional[logging.Logger] = None
) -> Tuple[bool, str]:
    """
    通過自定義URL運行 OddsHarvester 爬取數據
    
    Args:
        url: 比賽頁面URL
        season: 賽季
        markets: 市場列表
        output_dir: 輸出目錄
        league_name: 聯賽名稱
        headless: 是否使用無頭模式
        concurrency: 並發任務數
        scrape_history: 是否爬取歷史賠率
        use_preview_mode: 是否使用預覽模式
        log_logger: 日誌記錄器
    
    Returns:
        (是否成功, 輸出文件路徑)
    """
    logger = log_logger or logging.getLogger(__name__)
    
    # 構建市場參數
    markets_str = ",".join(markets)
    
    # 構建輸出文件路徑
    safe_name = league_name.replace(" ", "_").replace("-", "_")
    safe_market = markets[0].replace("-", "_").replace(".", "_")
    output_file = os.path.join(output_dir, f"odds_{safe_name}_{season}_{safe_market}.csv")
    temp_file = output_file + ".tmp"
    
    # 構建命令 - 使用 match_links (需要 --sport 參數)
    cmd = [
        ODDS_HARVESTER_VENV,
        "-m", "src.main",
        "scrape_upcoming",  # 使用 scrape_upcoming 配合 match_links
        "--sport", "football",
        "--match_links", url,
        "--markets", markets_str,
        "--format", "csv",
        "--file_path", temp_file,
        "--concurrency_tasks", str(concurrency),
    ]
    
    if headless:
        cmd.append("--headless")
    
    if scrape_history:
        cmd.append("--scrape_odds_history")
    
    # 不使用 --preview_submarkets_only，獲取完整歷史數據
    
    # 設置環境變量
    env = os.environ.copy()
    env["PYTHONPATH"] = ODDS_HARVESTER_PATH
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    
    logger.info(f"開始爬取: {league_name} - {season}, URL: {url}")
    
    try:
        result = subprocess.run(
            cmd,
            env=env,
            cwd=ODDS_HARVESTER_PATH,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=3600
        )
        
        if result.returncode == 0 and os.path.exists(output_file):
            # 檢查文件是否有有效數據
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content and len(content) > 100:
                        logger.info(f"✅ 成功: {league_name} - {season}")
                        return True, output_file
            except Exception as e:
                logger.warning(f"⚠️ 讀取文件失敗: {e}")
            
            logger.info(f"✅ 成功: {league_name} - {season}")
            return True, output_file
        else:
            logger.warning(f"⚠️ 結果未知: {league_name} - {season}")
            return False, ""
            
    except Exception as e:
        logger.error(f"❌ 異常: {league_name} - {season}, 錯誤: {str(e)}")
        return False, ""


# ============== 主爬取邏輯 ==============

def scrape_leagues(
    leagues: Dict[str, Dict],
    seasons: List[str],
    markets: List[str],
    output_dir: str,
    headless: bool = True,
    concurrency: int = 5,
    scrape_history: bool = True,
    use_preview_mode: bool = False,
    delay_between_requests: int = 5,
    log_logger: Optional[logging.Logger] = None
) -> Dict[str, int]:
    """
    爬取所有聯賽數據
    
    Args:
        leagues: 聯賽配置
        seasons: 賽季列表
        markets: 市場列表
        output_dir: 輸出目錄
        headless: 是否使用無頭模式
        concurrency: 並發任務數
        scrape_history: 是否爬取歷史賠率
        use_preview_mode: 是否使用預覽模式
        delay_between_requests: 請求間隔(秒)
        log_logger: 日誌記錄器
    
    Returns:
        統計信息 {"success": x, "failed": y}
    """
    logger = log_logger or logging.getLogger(__name__)
    
    stats = {"success": 0, "failed": 0}
    total_tasks = len(leagues) * len(seasons) * len(markets)
    current_task = 0
    
    for league_key, league_info in leagues.items():
        for season in seasons:
            for market in markets:  # 遍歷所有市場
                current_task += 1
                logger.info(f"\n[{current_task}/{total_tasks}] 處理: {league_info['name']} - {season}")
                
                # 檢查是否使用自定義URL
                if "custom_url" in league_info:
                    success, _ = run_odds_harvester_by_url(
                        url=league_info["custom_url"],
                        season=season,
                        markets=[market],
                        output_dir=output_dir,
                        league_name=league_key,
                        headless=headless,
                        concurrency=concurrency,
                        scrape_history=scrape_history,
                        use_preview_mode=use_preview_mode,
                        log_logger=logger
                    )
                else:
                    success, _ = run_odds_harvester(
                        league_key=league_key,
                        season=season,
                        markets=[market],
                        output_dir=output_dir,
                        headless=headless,
                        concurrency=concurrency,
                        scrape_history=scrape_history,
                        use_preview_mode=use_preview_mode,
                        log_logger=logger
                    )
                
                if success:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
                
                # 延遲，避免請求過快
                time.sleep(delay_between_requests)
    
    return stats


def scrape_cups(
    cups: Dict[str, Dict],
    seasons: List[str],
    markets: List[str],
    output_dir: str,
    headless: bool = True,
    concurrency: int = 5,
    scrape_history: bool = True,
    use_preview_mode: bool = False,
    delay_between_requests: int = 5,
    log_logger: Optional[logging.Logger] = None
) -> Dict[str, int]:
    """
    爬取所有杯賽數據
    
    Args:
        cups: 杯賽配置
        seasons: 賽季列表
        markets: 市場列表
        output_dir: 輸出目錄
        headless: 是否使用無頭模式
        concurrency: 並發任務數
        scrape_history: 是否爬取歷史賠率
        use_preview_mode: 是否使用預覽模式
        delay_between_requests: 請求間隔(秒)
        log_logger: 日誌記錄器
    
    Returns:
        統計信息
    """
    logger = log_logger or logging.getLogger(__name__)
    
    stats = {"success": 0, "failed": 0}
    total_tasks = len(cups) * len(seasons) * len(markets)
    current_task = 0
    
    for cup_key, cup_info in cups.items():
        for season in seasons:
            for market in markets:  # 遍歷所有市場
                current_task += 1
                logger.info(f"\n[{current_task}/{total_tasks}] 處理: {cup_info['name']} - {season}")
                
                # 使用動態URL模板，替換賽季
                if "url_template" in cup_info:
                    # 轉換賽季格式 (2015-2016 -> 2015-2016)
                    season_url = season.replace("-", "-")
                    cup_url = cup_info["url_template"].replace("{season}", season_url)
                    success, _ = run_odds_harvester_by_url(
                        url=cup_url,
                        season=season,
                        markets=[market],
                        output_dir=output_dir,
                        league_name=cup_key,
                        headless=headless,
                        concurrency=concurrency,
                        scrape_history=scrape_history,
                        use_preview_mode=use_preview_mode,
                        log_logger=logger
                    )
                elif "custom_url" in cup_info:
                    success, _ = run_odds_harvester_by_url(
                        url=cup_info["custom_url"],
                        season=season,
                        markets=[market],
                        output_dir=output_dir,
                        league_name=cup_key,
                        headless=headless,
                        concurrency=concurrency,
                        scrape_history=scrape_history,
                        use_preview_mode=use_preview_mode,
                        log_logger=logger
                    )
                else:
                    success, _ = run_odds_harvester(
                        league_key=cup_key,
                        season=season,
                        markets=[market],
                        output_dir=output_dir,
                        headless=headless,
                        concurrency=concurrency,
                        scrape_history=scrape_history,
                        use_preview_mode=use_preview_mode,
                        log_logger=logger
                    )
                
                if success:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
                
                time.sleep(delay_between_requests)
    
    return stats


# ============== 便捷函數 ==============

def scrape_all_leagues_and_cups(
    start_season: str = START_SEASON,
    markets: List[str] = MARKETS_SHORT,
    headless: bool = True,
    concurrency: int = 5,
    scrape_history: bool = True,
    use_preview_mode: bool = False,
    delay_between_requests: int = 5,
    include_cups: bool = True,
    output_base: str = OUTPUT_BASE_PATH
) -> Dict[str, int]:
    """
    便捷函數：爬取所有聯賽和杯賽數據
    
    Args:
        start_season: 起始賽季
        markets: 市場列表
        headless: 是否使用無頭模式
        concurrency: 並發任務數
        scrape_history: 是否爬取歷史賠率
        use_preview_mode: 是否使用預覽模式 (更快)
        delay_between_requests: 請求間隔
        include_cups: 是否包含杯賽
        output_base: 輸出基礎路徑
    
    Returns:
        統計信息
    """
    # 創建輸出目錄
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = os.path.join(output_base, f"scrape_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)
    
    # 設置日誌
    logger = setup_logging(output_dir)
    
    logger.info("=" * 60)
    logger.info("OddsHarvester 批量爬取任務開始")
    logger.info(f"起始賽季: {start_season}")
    logger.info(f"市場: {markets}")
    logger.info(f"包含杯賽: {include_cups}")
    logger.info("=" * 60)
    
    # 生成賽季列表
    seasons = generate_seasons(start_season)
    logger.info(f"賽季列表: {seasons}")
    
    total_stats = {"success": 0, "failed": 0}
    
    # 爬取聯賽
    logger.info("\n" + "=" * 40)
    logger.info("開始爬取聯賽數據")
    logger.info("=" * 40)
    
    league_stats = scrape_leagues(
        leagues=LEAGUES,
        seasons=seasons,
        markets=markets,
        output_dir=output_dir,
        headless=headless,
        concurrency=concurrency,
        scrape_history=scrape_history,
        use_preview_mode=use_preview_mode,
        delay_between_requests=delay_between_requests,
        log_logger=logger
    )
    
    total_stats["success"] += league_stats["success"]
    total_stats["failed"] += league_stats["failed"]
    
    # 爬取杯賽
    if include_cups:
        logger.info("\n" + "=" * 40)
        logger.info("開始爬取杯賽數據")
        logger.info("=" * 40)
        
        cup_stats = scrape_cups(
            cups=CUPS,
            seasons=seasons,
            markets=markets,
            output_dir=output_dir,
            headless=headless,
            concurrency=concurrency,
            scrape_history=scrape_history,
            use_preview_mode=use_preview_mode,
            delay_between_requests=delay_between_requests,
            log_logger=logger
        )
        
        total_stats["success"] += cup_stats["success"]
        total_stats["failed"] += cup_stats["failed"]
    
    logger.info("\n" + "=" * 60)
    logger.info("爬取任務完成!")
    logger.info(f"成功: {total_stats['success']}")
    logger.info(f"失敗: {total_stats['failed']}")
    logger.info(f"輸出目錄: {output_dir}")
    logger.info("=" * 60)
    
    return total_stats


def scrape_single_league(
    league_key: str,
    season: str,
    markets: List[str] = MARKETS_SHORT,
    headless: bool = True,
    concurrency: int = 5,
    scrape_history: bool = True,
    use_preview_mode: bool = False,
    output_dir: Optional[str] = None
) -> Tuple[bool, str]:
    """
    便捷函數：爬取單個聯賽
    
    Args:
        league_key: 聯賽 key
        season: 賽季
        markets: 市場列表
        headless: 是否使用無頭模式
        concurrency: 並發任務數
        scrape_history: 是否爬取歷史賠率
        use_preview_mode: 是否使用預覽模式
        output_dir: 輸出目錄
    
    Returns:
        (是否成功, 輸出文件路徑)
    """
    if output_dir is None:
        output_dir = os.path.join(OUTPUT_BASE_PATH, "single_scrape")
        os.makedirs(output_dir, exist_ok=True)
    
    logger = setup_logging(output_dir)
    
    league_info = LEAGUES.get(league_key)
    if not league_info:
        logger.error(f"未知的聯賽: {league_key}")
        return False, ""
    
    if "custom_url" in league_info:
        return run_odds_harvester_by_url(
            url=league_info["custom_url"],
            season=season,
            markets=markets,
            output_dir=output_dir,
            league_name=league_key,
            headless=headless,
            concurrency=concurrency,
            scrape_history=scrape_history,
            use_preview_mode=use_preview_mode,
            log_logger=logger
        )
    else:
        return run_odds_harvester(
            league_key=league_key,
            season=season,
            markets=markets,
            output_dir=output_dir,
            headless=headless,
            concurrency=concurrency,
            scrape_history=scrape_history,
            use_preview_mode=use_preview_mode,
            log_logger=logger
        )


def scrape_single_cup(
    cup_key: str,
    season: str,
    markets: List[str] = MARKETS_SHORT,
    headless: bool = True,
    concurrency: int = 5,
    scrape_history: bool = True,
    use_preview_mode: bool = False,
    output_dir: Optional[str] = None
) -> Tuple[bool, str]:
    """
    便捷函數：爬取單個杯賽
    
    Args:
        cup_key: 杯賽 key
        season: 賽季
        markets: 市場列表
        headless: 是否使用無頭模式
        concurrency: 並發任務數
        scrape_history: 是否爬取歷史賠率
        use_preview_mode: 是否使用預覽模式
        output_dir: 輸出目錄
    
    Returns:
        (是否成功, 輸出文件路徑)
    """
    if output_dir is None:
        output_dir = os.path.join(OUTPUT_BASE_PATH, "single_scrape")
        os.makedirs(output_dir, exist_ok=True)
    
    logger = setup_logging(output_dir)
    
    cup_info = CUPS.get(cup_key)
    if not cup_info:
        logger.error(f"未知的杯賽: {cup_key}")
        return False, ""
    
    if "custom_url" in cup_info:
        return run_odds_harvester_by_url(
            url=cup_info["custom_url"],
            season=season,
            markets=markets,
            output_dir=output_dir,
            league_name=cup_key,
            headless=headless,
            concurrency=concurrency,
            scrape_history=scrape_history,
            use_preview_mode=use_preview_mode,
            log_logger=logger
        )
    else:
        return run_odds_harvester(
            league_key=cup_key,
            season=season,
            markets=markets,
            output_dir=output_dir,
            headless=headless,
            concurrency=concurrency,
            scrape_history=scrape_history,
            use_preview_mode=use_preview_mode,
            log_logger=logger
        )


# ============== 主程序入口 ==============

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="OddsHarvester 批量爬取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:

# 1. 爬取所有聯賽和杯賽 (使用精簡市場)
python odds_batch_scraper.py --all

# 2. 爬取所有聯賽和杯賽 (使用完整市場)
python odds_batch_scraper.py --all --full-markets

# 3. 爬取單個聯賽
python odds_batch_scraper.py --league england-premier-league --season 2023-2024

# 4. 爬取單個杯賽
python odds_batch_scraper.py --cup champions-league --season 2023-2024

# 5. 爬取多個賽季
python odds_batch_scraper.py --league england-premier-league --seasons 2020-2021 2021-2022 2022-2023

# 6. 僅爬取聯賽，不包含杯賽
python odds_batch_scraper.py --all --no-cups
        """
    )
    
    parser.add_argument("--all", action="store_true", help="爬取所有聯賽和杯賽")
    parser.add_argument("--league", type=str, help="爬取指定聯賽")
    parser.add_argument("--cup", type=str, help="爬取指定杯賽")
    parser.add_argument("--season", type=str, help="指定單個賽季")
    parser.add_argument("--seasons", nargs="+", help="指定多個賽季")
    parser.add_argument("--start-season", type=str, default=START_SEASON, help=f"起始賽季 (默認: {START_SEASON})")
    parser.add_argument("--markets", nargs="+", help="指定市場列表")
    parser.add_argument("--full-markets", action="store_true", help="使用完整市場列表")
    parser.add_argument("--no-headless", action="store_true", help="不使用無頭模式")
    parser.add_argument("--concurrency", type=int, default=5, help="並發任務數 (默認: 5)")
    parser.add_argument("--scrape-history", action="store_true", default=True, help="爬取歷史賠率 (默認開啟)")
    parser.add_argument("--no-preview", action="store_true", help="不使用預覽模式 (更慢但更詳細)")
    parser.add_argument("--no-cups", action="store_true", help="不包含杯賽")
    parser.add_argument("--delay", type=int, default=5, help="請求間隔秒數 (默認: 5)")
    
    args = parser.parse_args()
    
    # 確定市場
    if args.full_markets:
        markets = MARKETS
    elif args.markets:
        markets = args.markets
    else:
        markets = MARKETS_SHORT
    
    # 確定賽季
    if args.seasons:
        seasons = args.seasons
    elif args.season:
        seasons = [args.season]
    else:
        seasons = generate_seasons(args.start_season)
    
    # 執行爬取
    if args.all:
        stats = scrape_all_leagues_and_cups(
            start_season=args.start_season,
            markets=markets,
            headless=not args.no_headless,
            concurrency=args.concurrency,
            scrape_history=args.scrape_history,
            use_preview_mode=not args.no_preview,
            delay_between_requests=args.delay,
            include_cups=not args.no_cups
        )
        print(f"\n完成! 成功: {stats['success']}, 失敗: {stats['failed']}")
        
    elif args.league:
        success, output = scrape_single_league(
            league_key=args.league,
            season=seasons[0],
            markets=markets,
            headless=not args.no_headless,
            concurrency=args.concurrency,
            scrape_history=args.scrape_history,
            use_preview_mode=not args.no_preview
        )
        print(f"\n完成! 成功: {success}, 輸出: {output}")
        
    elif args.cup:
        success, output = scrape_single_cup(
            cup_key=args.cup,
            season=seasons[0],
            markets=markets,
            headless=not args.no_headless,
            concurrency=args.concurrency,
            scrape_history=args.scrape_history,
            use_preview_mode=not args.no_preview
        )
        print(f"\n完成! 成功: {success}, 輸出: {output}")
        
    else:
        parser.print_help()
