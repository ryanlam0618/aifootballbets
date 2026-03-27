#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Capture OddsPortal match-event-history URLs across different markets")
    p.add_argument("--match-url", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max-clicks", type=int, default=80)
    p.add_argument("--timeout-ms", type=int, default=120000)
    p.add_argument("--headless", action="store_true")
    return p.parse_args()


async def accept_consent(page) -> None:
    for sel in ["#onetrust-accept-btn-handler", "button:has-text('I Accept')", "button:has-text('Accept')", "button:has-text('Accept all')"]:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=2500)
                await page.wait_for_timeout(800)
                return
        except Exception:
            pass


async def main() -> int:
    args = parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    seen: dict[str, dict[str, Any]] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        context = await browser.new_context()
        page = await context.new_page()

        async def on_response(resp):
            try:
                url = resp.url
                if "match-event-history" not in url:
                    return
                if url in seen:
                    return
                txt = await resp.text()
                seen[url] = {
                    "status": resp.status,
                    "len": len(txt),
                    "preview": txt[:120],
                }
            except Exception:
                return

        page.on("response", on_response)

        await page.goto(args.match_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
        await page.wait_for_timeout(2500)
        await accept_consent(page)
        await page.wait_for_timeout(1500)

        # Try multiple possible odd containers
        selectors = [
            "div[data-testid='odd-container']",
            "div[data-testid='odd-container-default']",
            "[data-testid$='odd-container-default']",
            "[data-testid*='odd-container']",
        ]

        picked = None
        count = 0
        for sel in selectors:
            try:
                loc = page.locator(sel)
                c = await loc.count()
                if c > count:
                    picked = sel
                    count = c
            except Exception:
                continue

        if not picked or count == 0:
            out_path.write_text(json.dumps({"match_url": args.match_url, "error": "no_odd_containers_found"}, indent=2), encoding="utf-8")
            print(json.dumps({"out": str(out_path), "count": 0, "picked": picked, "cell_count": count}))
            await context.close()
            await browser.close()
            return 2

        cells = page.locator(picked)
        n = min(args.max_clicks, await cells.count())
        for i in range(n):
            try:
                await cells.nth(i).scroll_into_view_if_needed(timeout=5000)
                await page.wait_for_timeout(150)
                await cells.nth(i).click(timeout=5000)
                await page.wait_for_timeout(700)
            except Exception:
                continue

        out_path.write_text(
            json.dumps({"match_url": args.match_url, "picked_selector": picked, "cell_count": count, "urls": seen}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(json.dumps({"out": str(out_path), "count": len(seen), "picked": picked, "cell_count": count}, ensure_ascii=False))

        await context.close()
        await browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
