#!/usr/bin/env python3
"""OddsPortal debug sampler.

Goal: randomly sample matches from the last N seasons and verify we can:
- fetch/decrypt tournament archive pages (ajax-sport-country-tournament-archive_)
- pick a match URL
- capture + fetch + decrypt match-event-history for 1X2 and OU

This is meant for reliability testing ("random days over past 10 years").
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import subprocess
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from playwright.async_api import async_playwright


ROOT_RESULTS_URL = "https://www.oddsportal.com/football/england/premier-league/results/"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


def utc_date_str(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def run_node_decrypt(enc: str, decrypt_js: str) -> dict[str, Any]:
    p = subprocess.run(["node", decrypt_js], input=enc, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"decrypt failed: {p.stderr.strip()}")
    try:
        return json.loads(p.stdout)
    except Exception as e:
        raise RuntimeError(f"decrypt JSON parse failed: {e}")


async def capture_archive_base(results_url: str) -> str:
    """Open results page and capture full ajax-sport-country-tournament-archive_ base URL (with flags).

    Returns base ending with '/1/0' (no trailing slash), e.g.
      https://www.oddsportal.com/ajax-sport-country-tournament-archive_/1/<encId>/<FLAGS>/1/0
    """

    archive_urls: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900}, user_agent=UA)
        page = await ctx.new_page()

        async def on_resp(resp):
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                u = resp.url
                if "ajax-sport-country-tournament-archive_" in u:
                    archive_urls.append(u)
            except Exception:
                return

        page.on("response", on_resp)

        await page.goto(results_url, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(6000)

        # accept cookie if present
        for sel in ["button:has-text('I Accept')", "#onetrust-accept-btn-handler", "button:has-text('Accept')", "button:has-text('Accept all')"]:
            try:
                loc = page.locator(sel).first
                if await loc.count() and await loc.is_visible():
                    await loc.click(timeout=3000)
                    await page.wait_for_timeout(1200)
                    break
            except Exception:
                pass

        # Scroll to trigger initial archive XHR.
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2500)

        if not archive_urls:
            # try clicking pagination 2 if present
            try:
                await page.locator("a.pagination-link:has-text('2')").first.click(timeout=5000)
                await page.wait_for_timeout(2500)
            except Exception:
                pass

        await ctx.close()
        await browser.close()

    if not archive_urls:
        raise RuntimeError("could not capture archive XHR url")

    # Pick the last one; normalize to base .../1/0
    u = archive_urls[-1]
    u = u.split("?_=")[0].rstrip("/")
    # Sometimes contains /page/N; strip that.
    u = re.sub(r"/page/\d+$", "", u)
    return u


def fetch_archive_page(archive_base: str, page: int, decrypt_js: str) -> dict[str, Any]:
    url = f"{archive_base}/page/{page}/"
    r = requests.get(url, headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"}, timeout=30)
    r.raise_for_status()
    enc = r.text.strip()
    return run_node_decrypt(enc, decrypt_js)


async def capture_match_event_history_urls(match_url: str, market: str) -> list[str]:
    """Capture match-event-history URLs by interacting with the page.

    market:
      - '1x2' uses #1x2;2
      - 'ou' uses #over-under;2 and expands first row
    """

    urls: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900}, user_agent=UA)
        page = await ctx.new_page()

        async def on_resp(resp):
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                u = resp.url
                if "match-event-history" in u:
                    urls.append(u)
            except Exception:
                return

        page.on("response", on_resp)

        if market == "1x2":
            url = match_url.rstrip("/") + "/#1x2;2"
        elif market == "ou":
            url = match_url.rstrip("/") + "/#over-under;2"
        else:
            raise ValueError("market must be 1x2 or ou")

        await page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(6000)

        for sel in ["button:has-text('I Accept')", "#onetrust-accept-btn-handler", "button:has-text('Accept')", "button:has-text('Accept all')"]:
            try:
                loc = page.locator(sel).first
                if await loc.count() and await loc.is_visible():
                    await loc.click(timeout=3000)
                    await page.wait_for_timeout(1200)
                    break
            except Exception:
                pass

        if market == "ou":
            # expand first OU line, then click odds inside expanded section
            try:
                await page.locator('[data-testid="over-under-collapsed-row"]').first.click(timeout=5000)
                await page.wait_for_timeout(1500)
            except Exception:
                pass

        # Click a bunch of odd containers
        cells = page.locator('[data-testid*="odd-container"]')
        n = min(80, await cells.count())
        for i in range(n):
            try:
                await cells.nth(i).scroll_into_view_if_needed(timeout=5000)
                await page.wait_for_timeout(60)
                await cells.nth(i).click(timeout=2500)
                await page.wait_for_timeout(250)
            except Exception:
                continue

        await ctx.close()
        await browser.close()

    # unique preserve order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def parse_bookie_id(mehist_url: str) -> Optional[int]:
    # /match-event-history/1-<match>-<bt>-<sc>-0-<bookie>/
    try:
        part = mehist_url.split("/match-event-history/")[1].split("/")[0]
        bid = part.split("-")[-1]
        if bid.isdigit():
            return int(bid)
    except Exception:
        pass
    return None


@dataclass
class SampleResult:
    season_results_url: str
    archive_base: str
    archive_page: int
    match_url: str
    match_date_utc: str

    ok_archive: bool
    ok_1x2: bool
    ok_ou: bool

    n_1x2_urls: int
    n_ou_urls: int

    # median aggregation: unique timestamps observed (simple count across urls)
    ticks_1x2: int
    ticks_ou: int

    notes: str = ""


def count_unique_timestamps_from_mehist_json(path: str, bookie_id: int) -> int:
    d = json.load(open(path))
    back = d["d"]["history"]["back"]
    if not isinstance(back, dict):
        return 0
    ts = set()
    for _, inner in back.items():
        for odd, _, t in inner.get(str(bookie_id), []):
            ts.add(t)
    return len(ts)


async def run_one_sample(season_results_url: str, rng: random.Random, decrypt_js: str, fetch_py: str) -> SampleResult:
    archive_base = await capture_archive_base(season_results_url)

    # page 1 to learn pageCount
    j1 = fetch_archive_page(archive_base, 1, decrypt_js)
    page_count = int(j1["d"]["pagination"]["pageCount"])
    page = rng.randint(1, page_count)
    jp = fetch_archive_page(archive_base, page, decrypt_js)

    rows = jp["d"]["rows"]
    row = rng.choice(rows)
    match_url = "https://www.oddsportal.com" + row["url"]
    match_date = utc_date_str(int(row["date-start-timestamp"]))

    ok_archive = True

    # 1X2
    urls_1x2 = await capture_match_event_history_urls(match_url, market="1x2")
    ok_1x2 = len(urls_1x2) > 0

    ticks_1x2 = 0
    if ok_1x2:
        bid = parse_bookie_id(urls_1x2[0])
        if bid is not None:
            out = f"/home/openclaw/.openclaw/workspace/tmp/debug_mehist_1x2_{bid}.json"
            subprocess.run(["python3", fetch_py, "--url", urls_1x2[0], "--out-json", out], check=True, capture_output=True, text=True)
            ticks_1x2 = count_unique_timestamps_from_mehist_json(out, bid)

    # OU
    urls_ou = await capture_match_event_history_urls(match_url, market="ou")
    ok_ou = len(urls_ou) > 0

    ticks_ou = 0
    if ok_ou:
        bid = parse_bookie_id(urls_ou[0])
        if bid is not None:
            out = f"/home/openclaw/.openclaw/workspace/tmp/debug_mehist_ou_{bid}.json"
            subprocess.run(["python3", fetch_py, "--url", urls_ou[0], "--out-json", out], check=True, capture_output=True, text=True)
            ticks_ou = count_unique_timestamps_from_mehist_json(out, bid)

    return SampleResult(
        season_results_url=season_results_url,
        archive_base=archive_base,
        archive_page=page,
        match_url=match_url,
        match_date_utc=match_date,
        ok_archive=ok_archive,
        ok_1x2=ok_1x2,
        ok_ou=ok_ou,
        n_1x2_urls=len(urls_1x2),
        n_ou_urls=len(urls_ou),
        ticks_1x2=ticks_1x2,
        ticks_ou=ticks_ou,
    )


def seasons_last_n(n: int, end_year: int) -> list[str]:
    """Return results URLs for last n seasons ending with end_year/end_year+1.

    For example end_year=2025 => includes 2025/2026, 2024/2025, ...
    """
    out = []
    # include current season style results/ for 2025/2026 uses base 'premier-league/results/'
    # But to keep stable, use explicit season slugs for all.
    for y in range(end_year, end_year - n, -1):
        out.append(f"https://www.oddsportal.com/football/england/premier-league-{y}-{y+1}/results/")
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default="/home/openclaw/.openclaw/workspace/tmp/oddsportal_debug_samples.json")
    args = ap.parse_args()

    rng = random.Random(args.seed or int(time.time()))

    decrypt_js = "scripts/oddsportal_decrypt_match_event.js"
    fetch_py = "scripts/oddsportal_fetch_mehist.py"

    seasons = seasons_last_n(args.years, end_year=datetime.now(timezone.utc).year - 1)

    results: list[SampleResult] = []
    for _ in range(args.samples):
        season_url = rng.choice(seasons)
        try:
            r = await run_one_sample(season_url, rng, decrypt_js, fetch_py)
            results.append(r)
            print(json.dumps({"match": r.match_url, "date": r.match_date_utc, "ok_1x2": r.ok_1x2, "ok_ou": r.ok_ou, "ticks_1x2": r.ticks_1x2, "ticks_ou": r.ticks_ou}, ensure_ascii=False))
        except Exception as e:
            results.append(
                SampleResult(
                    season_results_url=season_url,
                    archive_base="",
                    archive_page=-1,
                    match_url="",
                    match_date_utc="",
                    ok_archive=False,
                    ok_1x2=False,
                    ok_ou=False,
                    n_1x2_urls=0,
                    n_ou_urls=0,
                    ticks_1x2=0,
                    ticks_ou=0,
                    notes=str(e),
                )
            )
            print(json.dumps({"season": season_url, "error": str(e)}, ensure_ascii=False))

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)

    # summary
    ok_archive = sum(1 for r in results if r.ok_archive)
    ok_1x2 = sum(1 for r in results if r.ok_1x2)
    ok_ou = sum(1 for r in results if r.ok_ou)
    print(json.dumps({"samples": len(results), "ok_archive": ok_archive, "ok_1x2": ok_1x2, "ok_ou": ok_ou, "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
