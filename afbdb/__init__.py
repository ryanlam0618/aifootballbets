"""afbdb — aifootballbets MySQL data layer.

Layer-1 storage for the repo:
- afb_odds_snapshots : live/pre-match odds snapshots (as-of queryable)
- afb_predictions    : model predictions per run/match/market
- afb_bets           : bet ledger (mirrors paper bet_log; PK = bet_id)
- afb_state          : small key/value run state

Historical fixtures/results/xG are READ-ONLY from the existing
sofascore-backfill tables (matches / match_shotmap / teams / competitions /
seasons). This module never writes to those tables.
"""

from afbdb.connection import afb_mysql_available, afb_mysql_connect
from afbdb.schema import ensure_afb_schema

__all__ = [
    "afb_mysql_available",
    "afb_mysql_connect",
    "ensure_afb_schema",
]
