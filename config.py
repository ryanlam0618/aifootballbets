import os
from dotenv import load_dotenv

# 載入 .env
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Settings:
    # --- 路徑設定 ---
    GDRIVE_PATH = r"G:\我的雲端硬碟\AI" 
    
    # 歷史數據路徑
    HISTORY_CSV_PATH = os.path.join(BASE_DIR, "data", "history_data.csv")
    
    # 賠率數據路徑 (讀取本地 odds.csv)
    ODDS_DATA_PATH = os.path.join(BASE_DIR, "data", "odds.csv")

    # the_odds_api 金鑰
    ODDS_API_KEY = "b404547d496d1606bc0eda3c7f1fe5ea"  
    
    # Excel 報表名稱
    EXCEL_FILENAME = "Betting_Records.xlsx"
    
    if os.path.exists(GDRIVE_PATH):
        EXCEL_FILEPATH = os.path.join(GDRIVE_PATH, EXCEL_FILENAME)
    else:
        EXCEL_FILEPATH = os.path.join(BASE_DIR, EXCEL_FILENAME)

    # --- 資金管理設定 ---
    INITIAL_BANKROLL = 500
    KELLY_FRACTION = 0.75 # Kelly 投注比例
    MIN_EDGE = 0.09 # 最小期望值 (Edge) 門檻


    # --- API 設定 (OpenAI 兼容模式) ---
    # 根據你的服務商文件，這是 API 網址
    API_BASE_URL = os.getenv("API_BASE_URL", "https://api.whatai.cc/v1")  
    NETWORK_API_URL = os.getenv("NETWORK_API_URL", "https://api.whatai.cc/v1")

    # --- API Keys ---
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "sk-XnFA4k0EMp5IspVxLOSVAOAnb2OGWQ2MB2uaB9yfOXrneXV8")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-NBQeAvgttqd13O48F1OjjPXgh01sy0z8jucmwN8gNMwRmVMe")
    GROK_API_KEY = os.getenv("GROK_API_KEY", "sk-brT8h5Bd3KKVJyNyn5s963vUTGDe5Pz4RUrzPUsTcqvxVTsn")

    # API-Football Key (傷停數據)
    API_FOOTBALL_KEY = "147e3f1218fa63de077c346ddac4f5ad"

    # --- 模型名稱設定 ---
    # 必須使用標準名稱
    MODEL_GEMINI = "gemini-3-pro-preview"  
    MODEL_GROK = "grok-4"
    MODEL_GPT = "gpt-5.2"

settings = Settings()


