import sys
sys.path.insert(0, r'C:\Users\Ryan\python\.vscode\fb_ai_bets\OddsHarvester')

try:
    from src.cli.cli_argument_handler import CLIArgumentHandler
    from src.core.scraper_app import run_scraper
    from src.storage.storage_manager import store_data
    print('[OK] All modules imported successfully')
except ImportError as e:
    print(f'[ERROR] Import failed: {e}')
