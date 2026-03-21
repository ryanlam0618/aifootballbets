"""Compatibility wrapper for OddsPortal extraction.

Why this exists:
- Some long-running jobs execute v2/tracking/*.py by file path, and cron may not run with repo root as CWD.
- In that case, importing `scripts.*` can fail (ModuleNotFoundError: scripts) because repo root isn't on sys.path.

This wrapper makes imports robust by anchoring sys.path to the repo root, then re-exporting the functions.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.oddsportal_one_match import extract_odds, normalize_market_type, parse_line_csv  # noqa: E402,F401
