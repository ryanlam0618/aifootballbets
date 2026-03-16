#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

DEFAULT_MATCH_URL = "https://www.oddsportal.com/football/england/premier-league/brentford-wolves-0jR7cwU6/#1X2;2"
DEFAULT_MARKET = "1X2"
DEFAULT_STORAGE_STATE_PATH = Path("/tmp/oddsportal_storage.json")
DEFAULT_OUTPUT_PATH = Path("/tmp/oddsportal_match.json")


def to_float(value: str | None):
    if value is None:
        return None
    value = value.strip().replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


async def accept_consent_if_present(page) -> bool:
    consent_selectors = [
        "#onetrust-accept-btn-handler",
        "button:has-text('Accept')",
        "button:has-text('I Accept')",
        "button:has-text('Accept all')",
    ]
    for sel in consent_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=2500)
                await page.wait_for_timeout(1200)
                return True
        except Exception:
            pass
    return False


async def ensure_storage_state(browser, url: str, storage_state_path: Path):
    if storage_state_path.exists() and storage_state_path.stat().st_size > 0:
        return

    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(3500)
    await accept_consent_if_present(page)
    await context.storage_state(path=str(storage_state_path))
    await context.close()


async def extract_odds(
    match_url: str,
    market: str = DEFAULT_MARKET,
    storage_state_path: Path = DEFAULT_STORAGE_STATE_PATH,
    headless: bool = False,
    timeout_ms: int = 120000,
    settle_ms: int = 2500,
) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            await ensure_storage_state(browser, match_url, storage_state_path)

            context = await browser.new_context(storage_state=str(storage_state_path))
            page = await context.new_page()
            await page.goto(match_url, wait_until="domcontentloaded", timeout=timeout_ms)
            await accept_consent_if_present(page)

            # Wait until bookmaker rows + odds cells are visible/rendered.
            row_selector = "div[data-testid='over-under-expanded-row'], div.border-black-borders.flex.h-9"
            await page.wait_for_selector(row_selector, state="visible", timeout=60000)

            # Extra settle time for dynamic odds hydration.
            await page.wait_for_timeout(settle_ms)

            rows = page.locator(row_selector)
            row_count = await rows.count()

            result = {
                "match_url": match_url,
                "market": market,
                "snapshot_ts_utc": datetime.now(timezone.utc).isoformat(),
                "row_count_seen": row_count,
                "odds": [],
                "errors": [],
            }

            for i in range(row_count):
                row = rows.nth(i)

                bookmaker_name = None
                name_loc = row.locator("p[data-testid='outrights-expanded-bookmaker-name']").first
                if await name_loc.count():
                    bookmaker_name = (await name_loc.inner_text()).strip()

                if not bookmaker_name:
                    logo_loc = row.locator("img.bookmaker-logo").first
                    if await logo_loc.count():
                        bookmaker_name = (
                            (await logo_loc.get_attribute("alt"))
                            or (await logo_loc.get_attribute("title"))
                            or ""
                        ).strip() or None

                odd_links = row.locator("div[data-testid='odd-container'] a.odds-link")
                odd_count = await odd_links.count()
                odd_values = []
                for j in range(min(odd_count, 3)):
                    txt = (await odd_links.nth(j).inner_text()).strip()
                    value = to_float(txt)
                    if value is not None:
                        odd_values.append(value)

                if len(odd_values) < 3:
                    # Fallback: scrape all decimal-looking anchors in row.
                    anchors = row.locator("a.odds-link")
                    ac = await anchors.count()
                    recovered = []
                    for j in range(ac):
                        txt = (await anchors.nth(j).inner_text()).strip()
                        val = to_float(txt)
                        if val is not None:
                            recovered.append(val)
                    if len(recovered) >= 3:
                        odd_values = recovered[:3]

                if bookmaker_name and len(odd_values) == 3:
                    raw_text = (await row.inner_text()).strip().replace("\n", " ")
                    result["odds"].append(
                        {
                            "bookmaker": bookmaker_name,
                            "home": odd_values[0],
                            "draw": odd_values[1],
                            "away": odd_values[2],
                            "timestamp": result["snapshot_ts_utc"],
                            "raw": raw_text[:500],
                        }
                    )
                else:
                    result["errors"].append(
                        {
                            "row_index": i,
                            "bookmaker": bookmaker_name,
                            "reason": "missing_bookmaker_or_3way_odds",
                        }
                    )

            await context.close()
            return result
        finally:
            await browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract one OddsPortal match market odds snapshot")
    parser.add_argument("--match-url", default=DEFAULT_MATCH_URL, help="OddsPortal match URL")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="Market label to include in output (default: 1X2)")
    parser.add_argument("--storage-state", default=str(DEFAULT_STORAGE_STATE_PATH), help="Playwright storage state JSON path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path (use '-' to skip file write)")
    parser.add_argument("--headless", action="store_true", help="Run Chromium in headless mode")
    parser.add_argument("--timeout-ms", type=int, default=120000, help="Navigation timeout in milliseconds")
    parser.add_argument("--settle-ms", type=int, default=2500, help="Post-render settle wait in milliseconds")
    parser.add_argument("--indent", type=int, default=2, help="JSON indent for stdout/file output")
    return parser.parse_args()


async def _run_cli(args: argparse.Namespace) -> int:
    result = await extract_odds(
        match_url=args.match_url,
        market=args.market,
        storage_state_path=Path(args.storage_state),
        headless=args.headless,
        timeout_ms=args.timeout_ms,
        settle_ms=args.settle_ms,
    )

    payload = json.dumps(result, ensure_ascii=False, indent=args.indent)
    if args.output != "-":
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    args = parse_args()
    try:
        raise SystemExit(asyncio.run(_run_cli(args)))
    except PlaywrightTimeoutError as e:
        raise SystemExit(f"Timed out while waiting for OddsPortal content: {e}")
