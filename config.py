# ============================================================
# API Keys 配置 (從環境變量讀取)
# ============================================================
# 請將以下設置複製到 .env 文件並填入您的 API Keys
# 
# 範例 .env 文件內容:
# ============================================================
# # API Keys (替換為您的實際 Keys)
# ODDS_API_KEY=your_odds_api_key_here
# GEMINI_API_KEY=your_gemini_api_key_here
# OPENAI_API_KEY=your_openai_api_key_here
# GROK_API_KEY=your_grok_api_key_here
# API_FOOTBALL_KEY=your_api_football_key_here
#
# # 可選: 自定義 API 端點
# API_BASE_URL=https://api.your-endpoint.com/v1
# NETWORK_API_URL=https://api.your-endpoint.com/v1
# ============================================================

import os
from dotenv import load_dotenv
from typing import List, Dict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 優先載入專案根目錄 .env，並覆蓋既有環境變數（避免舊 token 殘留）
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"), override=True)
load_dotenv(override=True)


class Settings:
    # --- 路徑設定 ---
    # 用環境變數覆蓋，避免硬編碼到單一 Windows 路徑
    GDRIVE_PATH = os.getenv("GDRIVE_PATH", "")
    
    # 歷史數據路徑
    HISTORY_CSV_PATH = os.path.join(BASE_DIR, "data", "history_data.csv")
    
    # 賠率數據路徑
    ODDS_DATA_PATH = os.path.join(BASE_DIR, "data", "odds.csv")

    # --- API Keys (從環境變量讀取) ---
    # 如果環境變量不存在，則返回空字符串
    ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    GROK_API_KEY = os.getenv("GROK_API_KEY", "")
    API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")

    # --- API 端點 ---
    API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
    NETWORK_API_URL = os.getenv("NETWORK_API_URL", API_BASE_URL)

    # --- Excel 報表名稱 ---
    EXCEL_FILENAME = os.getenv("EXCEL_FILENAME", "Betting_Records.xlsx")

    if GDRIVE_PATH and os.path.exists(GDRIVE_PATH):
        EXCEL_FILEPATH = os.path.join(GDRIVE_PATH, EXCEL_FILENAME)
    else:
        EXCEL_FILEPATH = os.path.join(BASE_DIR, EXCEL_FILENAME)

    # --- 資金管理設定 ---
    INITIAL_BANKROLL = float(os.getenv("INITIAL_BANKROLL", "2000"))
    KELLY_FRACTION = float(os.getenv("KELLY_FRACTION", "0.75"))
    MIN_EDGE = float(os.getenv("MIN_EDGE", "0.05"))

    # --- 模型名稱設定 ---
    MODEL_GEMINI = os.getenv("MODEL_GEMINI", "gemini-3-flash-preview-thinking-*")
    MODEL_GROK = os.getenv("MODEL_GROK", "grok-4")
    MODEL_GPT = os.getenv("MODEL_GPT", "gpt-5.2")

    # --- 驗證 API Keys 是否存在 ---
    def validate_api_keys(self) -> Dict[str, bool]:
        """檢查必要的 API Keys 是否已設置"""
        return {
            "ODDS_API_KEY": bool(self.ODDS_API_KEY),
            "OPENAI_API_KEY": bool(self.OPENAI_API_KEY),
            "GROK_API_KEY": bool(self.GROK_API_KEY),
        }

    def check_missing_keys(self) -> List[str]:
        """返回缺失的 API Keys 列表"""
        missing = []
        if not self.ODDS_API_KEY:
            missing.append("ODDS_API_KEY")
        if not self.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if not self.GROK_API_KEY:
            missing.append("GROK_API_KEY")
        return missing


settings = Settings()
