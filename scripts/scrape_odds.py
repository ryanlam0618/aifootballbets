#!/usr/bin/env python3
"""
PowerShell command.ps1 的 Python 版本
用於從 oddsportal.com 抓取比賽赔率數據

功能:
1. 定義要抓取的比賽链接列表
2. 使用 OddsHarvester scraper 作為子程序抓取數據
3. 將數據合併到最終的 CSV 文件
4. 處理錯誤和重試邏輯

使用方法:
    python scripts/scrape_odds.py
"""

import os
import sys
import time
import logging
import subprocess
from pathlib import Path
from typing import List, Optional

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OddsScraperRunner:
    """負責運行 OddsHarvester scraper 的類別"""
    
    def __init__(self):
        self.scraper_path = r"C:\Users\Ryan\python\.vscode\fb_ai_bets\OddsHarvester"
        self.venv_python = r"C:\Users\Ryan\python\.vscode\fb_ai_bets\OddsHarvester\.venv\Scripts\python.exe"
        self.scraper_src_main = r"C:\Users\Ryan\python\.vscode\fb_ai_bets\OddsHarvester\src\main.py"
        self.alternative_script = r"C:\Users\Ryan\python\.vscode\fb_ai_bets\scripts\TakeHistoryData.py"
    
    def run_scraper(self, link: str, temp_file: str) -> bool:
        """
        運行 OddsHarvester scraper 作為子程序
        
        Args:
            link: 要抓取的比賽链接
            temp_file: 臨時輸出文件路徑
            
        Returns:
            bool: 是否成功
        """
        # 檢查 scraper 是否存在
        if not os.path.exists(self.scraper_src_main):
            logger.warning(f"Scraper not found at: {self.scraper_src_main}")
            logger.info("Trying alternative scraper...")
            return self._run_alternative_scraper(temp_file)
        
        # 決定使用哪個 Python 解釋器
        python_exe = self.venv_python if os.path.exists(self.venv_python) else sys.executable
        
        # 構建命令參數
        cmd = [
            python_exe,
            "-m", "src.main",
            "scrape_upcoming",
            "--sport", "football",
            "--match_links", link,
            "--format", "csv",
            "--markets", "1x2",
            "--scrape_odds_history",
            "--file_path", temp_file,
            "--concurrency_tasks", "5",
            "--target_bookmaker", "1xBet",
            "--headless"
        ]
        
        # 設置環境變量
        env = os.environ.copy()
        env["PYTHONPATH"] = self.scraper_path
        env["PYTHONUNBUFFERED"] = "1"
        
        try:
            logger.info(f"Starting scraper for: {link}")
            logger.info(f"Command: {' '.join(cmd)}")
            
            # 運行 scraper 作為子程序
            result = subprocess.run(
                cmd,
                cwd=self.scraper_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=600  # 10 分鐘超時
            )
            
            if result.returncode == 0:
                logger.info(f"Data saved to: {temp_file}")
                # 打印輸出以便調試
                if result.stdout:
                    for line in result.stdout.strip().split('\n')[-10:]:  # 只打印最後10行
                        logger.debug(f"  {line}")
                return True
            else:
                logger.error(f"Scraper failed with exit code {result.returncode}")
                if result.stderr:
                    logger.error(f"Stderr: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Scraper timed out after 10 minutes")
            return False
        except Exception as e:
            logger.error(f"Error running scraper: {e}", exc_info=True)
            return False
    
    def _run_alternative_scraper(self, temp_file: str) -> bool:
        """
        運行替代的歷史數據抓取腳本
        
        Args:
            temp_file: 輸出文件路徑
            
        Returns:
            bool: 是否成功
        """
        try:
            logger.info(f"Running alternative scraper: {self.alternative_script}")
            result = subprocess.run(
                [sys.executable, self.alternative_script],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                logger.info("Alternative scraper completed successfully")
                return True
            else:
                logger.error(f"Alternative scraper failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error running alternative scraper: {e}")
            return False


class DataMerger:
    """負責合併 CSV 文件的類別"""
    
    @staticmethod
    def merge_csv_files(temp_file: str, final_file: str) -> bool:
        """
        合併臨時文件到最終文件
        
        Args:
            temp_file: 臨時文件路徑
            final_file: 最終文件路徑
            
        Returns:
            bool: 是否成功
        """
        try:
            # 檢查臨時文件是否存在
            if not os.path.exists(temp_file):
                logger.error(f"Temp file not found: {temp_file}")
                return False
            
            # 檢查臨時文件是否為空
            if os.path.getsize(temp_file) == 0:
                logger.warning("Temp file is empty, skipping merge")
                os.remove(temp_file)
                return False
            
            # 檢查最終文件是否存在
            if not os.path.exists(final_file):
                # 情況 1: 最終文件不存在，直接移動臨時文件
                os.rename(temp_file, final_file)
                logger.info(f"Created new file: {final_file}")
                return True
            else:
                # 情況 2: 最終文件存在，追加內容（跳過標題行）
                try:
                    import pandas as pd
                    
                    # 讀取臨時文件
                    temp_df = pd.read_csv(temp_file, encoding='utf-8')
                    
                    if temp_df.empty:
                        logger.warning("Temp file is empty (pandas), skipping merge")
                        os.remove(temp_file)
                        return False
                    
                    # 讀取最終文件
                    final_df = pd.read_csv(final_file, encoding='utf-8')
                    
                    # 追加數據
                    merged_df = pd.concat([final_df, temp_df], ignore_index=True)
                    
                    # 保存結果
                    merged_df.to_csv(final_file, index=False, encoding='utf-8')
                    
                    # 刪除臨時文件
                    os.remove(temp_file)
                    
                    logger.info(f"Data appended to: {final_file}")
                    logger.info(f"Total records: {len(merged_df)}")
                    return True
                    
                except ImportError:
                    # 如果沒有 pandas，使用純 Python 方式
                    logger.info("Pandas not available, using pure Python merge")
                    
                    # 讀取最終文件的所有行
                    with open(final_file, 'r', encoding='utf-8') as f:
                        final_lines = f.readlines()
                    
                    # 讀取臨時文件，跳過標題行
                    with open(temp_file, 'r', encoding='utf-8') as f:
                        temp_lines = f.readlines()
                    
                    if len(temp_lines) <= 1:
                        logger.warning("Temp file has no data rows, skipping merge")
                        os.remove(temp_file)
                        return False
                    
                    # 追加數據（跳過臨時文件的標題行）
                    with open(final_file, 'a', encoding='utf-8') as f:
                        for line in temp_lines[1:]:  # 跳過標題行
                            f.write(line)
                    
                    # 刪除臨時文件
                    os.remove(temp_file)
                    
                    total_records = len(final_lines) + len(temp_lines) - 1
                    logger.info(f"Data appended to: {final_file}")
                    logger.info(f"Total records (approx): {total_records}")
                    return True
                
        except Exception as e:
            logger.error(f"Error merging files: {e}", exc_info=True)
            return False


class OddsDataPipeline:
    """主數據處理管道"""
    
    def __init__(self, links: List[str], base_path: str):
        """
        初始化管道
        
        Args:
            links: 要抓取的比賽链接列表
            base_path: 數據保存的基本路徑
        """
        self.links = links
        self.base_path = Path(base_path)
        self.temp_file = self.base_path / "temp_odds.csv"
        self.final_file = self.base_path / "odds_latest.csv"
        self.scraper_runner = OddsScraperRunner()
        self.merger = DataMerger()
        
        # 確保目錄存在
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def run(self) -> bool:
        """
        運行完整的數據處理管道
        
        Returns:
            bool: 是否所有任務都成功
        """
        logger.info("=" * 60)
        logger.info("Starting Odds Data Pipeline")
        logger.info(f"Total tasks: {len(self.links)}")
        logger.info(f"Base path: {self.base_path}")
        logger.info("=" * 60)
        
        all_success = True
        
        for i, link in enumerate(self.links, 1):
            logger.info("-" * 60)
            logger.info(f"Processing Task ({i}/{len(self.links)})...")
            logger.info(f"Target: {link}")
            
            # 清理舊的臨時文件
            if self.temp_file.exists():
                try:
                    self.temp_file.unlink()
                    logger.info("Removed old temp file")
                except Exception as e:
                    logger.warning(f"Could not remove temp file: {e}")
            
            # 運行 scraper
            success = self.scraper_runner.run_scraper(link, str(self.temp_file))
            
            if success:
                # 合併數據
                merge_success = self.merger.merge_csv_files(
                    str(self.temp_file),
                    str(self.final_file)
                )
                
                if not merge_success:
                    all_success = False
            else:
                logger.error("Scraping failed")
                all_success = False
            
            # 顯示狀態
            if success and self.final_file.exists():
                try:
                    import pandas as pd
                    final_df = pd.read_csv(self.final_file)
                    logger.info(f"Total records in final file: {len(final_df)}")
                except ImportError:
                    with open(self.final_file, 'r') as f:
                        lines = f.readlines()
                    logger.info(f"Total lines in final file: {len(lines)}")
            
            # 等待一段時間再進行下一個任務
            if i < len(self.links):
                logger.info("Sleeping for 10 seconds...")
                time.sleep(10)
        
        logger.info("=" * 60)
        if all_success:
            logger.info("All tasks completed successfully!")
        else:
            logger.warning("Some tasks failed. Check logs for details.")
        
        logger.info(f"Final data saved to: {self.final_file}")
        logger.info("=" * 60)
        
        return all_success


def main():
    """主入口點"""
    
    # 1. 定義要抓取的链接
    links = [
        "https://www.oddsportal.com/football/england/premier-league/leeds-nottingham-raKBgwWA/",
    ]
    
    # 2. 定義文件路徑
    base_path = r"C:\Users\Ryan\python\.vscode\fb_ai_bets\data\archive"
    
    # 3. 創建並運行管道
    pipeline = OddsDataPipeline(links, base_path)
    success = pipeline.run()
    
    # 退出碼
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
