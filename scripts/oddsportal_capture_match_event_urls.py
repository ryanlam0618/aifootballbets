#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
from typing import Any

from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Capture OddsPortal /match-event/*.dat URLs triggered by a match page")
    p.add_argument("--match-url", required=True)
    p.add_argument("--fragment", default="", help="Optional fragment like /#over-under;2")
    p.add_argument("--click-text", default="", help="If set, try clicking a link/button containing this text")
    p.add_argument("--max-clicks", type=int, default=25)
    p.add_argument("--headless", action="store_true", default=True)
    p.add_argument("--timeout-ms", type=int, default=120000)
    return p.parse_args()


async def accept_consent(page) -> None:
    for sel in [
        "#onetrust-accept-btn-handler",
        "button:has-text('Accept')",
        "button:has-text('Accept all')",
        "button:has-text('I Accept')",
    ]:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=3000)
                await page.wait_for_timeout(1000)
                return
        except Exception:
            pass


async def main() -> int:
    args = parse_args()

    me_urls: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900}, user_agent=UA)
        page = await ctx.new_page()

        async def on_resp(resp):
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                u = resp.url
                if "/match-event/" in u and u.endswith(".dat?geo=HK&lang=en"):
                    me_urls.append(u)
            except Exception:
                return

        page.on("response", on_resp)

        url = args.match_url.rstrip("/") + args.fragment
        await page.goto(url, wait_until="domcontentloaded", timeout=args.timeout_ms)
        await page.wait_for_timeout(6000)
        await accept_consent(page)
        await page.wait_for_timeout(1500)

        if args.click_text:
            # try common elements first
            candidates = [
                page.get_by_role("link", name=re.compile(re.escape(args.click_text), re.I)).first,
                page.get_by_role("button", name=re.compile(re.escape(args.click_text), re.I)).first,
                page.locator(f"text={args.click_text}").first,
            ]
            for loc in candidates:
                try:
                    if await loc.count() and await loc.is_visible():
                        await loc.click(timeout=5000)
                        await page.wait_for_timeout(2500)
                        break
                except Exception:
                    pass

        # click a bunch of odd cells to trigger match-event requests
        cells = page.locator("div[data-testid='odd-container']")
        n = min(args.max_clicks, await cells.count())
        for i in range(n):
            try:
                await cells.nth(i).scroll_into_view_if_needed(timeout=5000)
                await page.wait_for_timeout(60)
                await cells.nth(i).click(timeout=2500)
                await page.wait_for_timeout(250)
            except Exception:
                continue

        await page.wait_for_timeout(1200)
        await ctx.close()
        await browser.close()

    uniq = []
    for u in me_urls:
        if u not in uniq:
            uniq.append(u)

    print(json.dumps({"count": len(uniq), "urls": uniq}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
