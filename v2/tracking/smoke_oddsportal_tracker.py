#!/usr/bin/env python3
from __future__ import annotations

# Allow running by file path from any CWD by anchoring repo root on sys.path.
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v2.tracking.oddsportal_one_match import extract_odds


DEFAULT_BASE_URL = "https://www.oddsportal.com/football/england/premier-league/brentford-wolves-0jR7cwU6/"


async def run(args: argparse.Namespace) -> int:
    targets = [
        ("1X2", f"{args.base_url}#1X2;2", []),
        ("OU", f"{args.base_url}#over-under;2", [2.5, 2.75]),
        ("AH", f"{args.base_url}#ah;2", [-0.25, 0.0]),
    ]

    for market, url, prefer in targets:
        payload = await extract_odds(
            match_url=url,
            market=market,
            storage_state_path=Path(args.storage_state),
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            settle_ms=args.settle_ms,
            top_lines=args.top_lines,
            prefer_lines=prefer,
            debug=False,
        )

        quotes = payload.get("odds") or []
        print(f"\n=== {market} ===")
        print(f"url={url}")
        print(f"detected_market_tab={payload.get('detected_market_tab')}")
        print(f"row_count_seen={payload.get('row_count_seen')} quotes={len(quotes)}")
        print(f"available_lines={payload.get('available_lines', [])[:20]}")
        print(f"selected_lines={payload.get('selected_lines', [])}")
        print(f"line_frequency_top10={list((payload.get('line_frequency') or {}).items())[:10]}")
        print("sample_quotes=")
        print(json.dumps(quotes[: args.sample], ensure_ascii=False, indent=2))

    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smoke test for OddsPortal tracker markets (1X2/OU/AH)")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Match base URL ending with '/'")
    p.add_argument("--storage-state", default="/tmp/oddsportal_storage.json", help="Playwright storage state path")
    p.add_argument("--headless", action="store_true", help="Run headless")
    p.add_argument("--timeout-ms", type=int, default=120000)
    p.add_argument("--settle-ms", type=int, default=2500)
    p.add_argument("--top-lines", type=int, default=2)
    p.add_argument("--sample", type=int, default=3, help="Sample quotes to print per market")
    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
