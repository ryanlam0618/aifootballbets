#!/usr/bin/env python3
"""Relabel 1X2 selection_key -> 1/X/2 using match-event outcomeId mapping.

Reads a raw CSV (as produced by oddsportal_export_debug_samples_csv_v2.py) and writes a new CSV
with added columns:
- outcome_1x2: {1,X,2} (only for market==1x2; otherwise empty)
- outcome_1x2_label: {home,draw,away}

Method per match:
- Open match_url/#1x2;2 in Playwright
- Click a few odds cells to trigger a /match-event/ ... -1-2- ... .dat request
- Fetch+decrypt that match-event payload
- Use d.oddsdata.back['E-1-2-0-0-0'].outcomeId mapping:
    0 -> selection_key for '1' (home)
    1 -> selection_key for 'X' (draw)
    2 -> selection_key for '2' (away)

This is more stable than matching displayed odds strings.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import asyncio
from pathlib import Path
from typing import Optional

import requests
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


def decrypt_match_event(enc: str, decrypt_js: str) -> dict:
    p = subprocess.run(["node", decrypt_js], input=enc, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "decrypt failed")
    return json.loads(p.stdout)


async def infer_mapping_for_match(match_url: str, decrypt_js: str) -> dict[str, str]:
    me_urls: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900}, user_agent=UA)
        page = await ctx.new_page()

        async def on_resp(resp):
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                u = resp.url
                if "/match-event/" in u and "-1-2-" in u and u.endswith(".dat?geo=HK&lang=en"):
                    me_urls.append(u)
            except Exception:
                return

        page.on("response", on_resp)

        url = match_url.rstrip("/") + "/#1x2;2"
        await page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(6000)

        # accept cookies
        for sel in ["button:has-text('I Accept')", "#onetrust-accept-btn-handler", "button:has-text('Accept')", "button:has-text('Accept all')"]:
            try:
                loc = page.locator(sel).first
                if await loc.count() and await loc.is_visible():
                    await loc.click(timeout=3000)
                    await page.wait_for_timeout(1200)
                    break
            except Exception:
                pass

        # click a few odd containers to trigger match-event
        cells = page.locator('[data-testid*="odd-container"]')
        n = min(12, await cells.count())
        for i in range(n):
            try:
                await cells.nth(i).scroll_into_view_if_needed(timeout=5000)
                await page.wait_for_timeout(60)
                await cells.nth(i).click(timeout=2500)
                await page.wait_for_timeout(250)
            except Exception:
                continue

        await ctx.close();
        await browser.close();

    if not me_urls:
        return {}

    me_url = me_urls[0]
    enc = requests.get(me_url, headers={"User-Agent": UA}, timeout=30).text.strip()
    j = decrypt_match_event(enc, decrypt_js)

    try:
        outcome_id = j["d"]["oddsdata"]["back"]["E-1-2-0-0-0"]["outcomeId"]
        # 0=home(1), 1=draw(X), 2=away(2)
        m = {
            outcome_id.get("0", ""): "1",
            outcome_id.get("1", ""): "X",
            outcome_id.get("2", ""): "2",
        }
        return {k: v for k, v in m.items() if k}
    except Exception:
        return {}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_csv", required=True)
    ap.add_argument("--out", dest="out_csv", required=True)
    ap.add_argument("--decrypt-js", default="scripts/oddsportal_decrypt_match_event.js")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.in_csv, encoding="utf-8")))

    # group match_url
    match_urls = sorted({r["match_url"] for r in rows if r.get("match_url")})

    mappings: dict[str, dict[str, str]] = {}
    for mu in match_urls:
        mappings[mu] = await infer_mapping_for_match(mu, args.decrypt_js)

    # write output with extra columns
    out_rows = []
    for r in rows:
        outcome = ""
        label = ""
        if r.get("market") == "1x2":
            outcome = mappings.get(r.get("match_url", ""), {}).get(r.get("selection_key", ""), "")
            label = {"1": "home", "X": "draw", "2": "away"}.get(outcome, "")
        r["outcome_1x2"] = outcome
        r["outcome_1x2_label"] = label
        out_rows.append(r)

    Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    print(json.dumps({"matches": len(match_urls), "rows": len(out_rows), "out": args.out_csv}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
