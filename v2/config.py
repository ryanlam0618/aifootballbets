from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env", override=True)
load_dotenv(override=True)


@dataclass
class V2Settings:
    odds_api_key: str = os.getenv("ODDS_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    grok_api_key: str = os.getenv("GROK_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    api_football_key: str = os.getenv("API_FOOTBALL_KEY", "")

    api_base_url: str = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
    network_api_url: str = os.getenv("NETWORK_API_URL", os.getenv("API_BASE_URL", "https://api.openai.com/v1"))

    model_gemini: str = os.getenv("MODEL_GEMINI", "gemini-3-flash-preview-thinking-*")
    model_grok: str = os.getenv("MODEL_GROK", "grok-4")
    model_gpt: str = os.getenv("MODEL_GPT", "gpt-5.2")

    gdrive_path: str = os.getenv("GDRIVE_PATH", "")
    gdrive_folder_id: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    service_account_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

    initial_bankroll: float = float(os.getenv("INITIAL_BANKROLL", "2000"))
    kelly_fraction: float = float(os.getenv("KELLY_FRACTION", "0.5"))
    min_edge: float = float(os.getenv("MIN_EDGE", "0.05"))

    timezone: str = os.getenv("DEFAULT_TIMEZONE", "Asia/Hong_Kong")

    # history source used by v2 features
    history_csv_path: str = os.getenv("HISTORY_CSV_PATH", str(BASE_DIR / "data" / "history_data.csv"))

    # OddsPortal / OddsHarvester integration
    oddsharvester_data_dir: str = os.getenv("ODDSHARVESTER_DATA_DIR", str(BASE_DIR / "OddsHarvester"))
    oddsharvester_cmd: str = os.getenv("ODDSHARVESTER_CMD", "")

    # token saving: limit leagues fetched from The Odds API per run
    odds_api_max_leagues_per_run: int = int(os.getenv("ODDS_API_MAX_LEAGUES_PER_RUN", "4"))

    # Optional tracking export hook (off by default)
    tracking_export_enabled: bool = os.getenv("TRACKING_EXPORT_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
    tracking_sqlite_path: str = os.getenv("TRACKING_SQLITE_PATH", str(BASE_DIR / "data" / "v2" / "tracking" / "bets.sqlite"))
    tracking_source_book: str = os.getenv("TRACKING_SOURCE_BOOK", "sport pp88")

    def missing_keys(self) -> list[str]:
        missing = []
        if not self.odds_api_key:
            missing.append("ODDS_API_KEY")
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.grok_api_key:
            missing.append("GROK_API_KEY")
        if not self.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        return missing


settings_v2 = V2Settings()
