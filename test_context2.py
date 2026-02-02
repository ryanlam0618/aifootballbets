import sys
sys.stdout.reconfigure(encoding='utf-8')

from config import settings
from src.data_modules import HistoryRepo

repo = HistoryRepo(settings.HISTORY_CSV_PATH)

print("Testing get_match_context...")
import traceback

try:
    context = repo.get_match_context("Liverpool", "Arsenal", "Premier League")
    print("Success!")
    print(f"Keys: {context.keys()}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    traceback.print_exc()
