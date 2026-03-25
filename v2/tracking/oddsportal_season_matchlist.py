#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "unknown"


def resolve_url(url_template: str, season: str) -> str:
    if "{season}" in url_template:
        return url_template.replace("{season}", season)
    return url_template


async def _collect_rows(page, base_url: str) -> list[dict]:
    js = """
    () => {
      const rows = [];
      const anchors = Array.from(document.querySelectorAll('a[href*="/football/"]'));
      for (const a of anchors) {
        const href = a.getAttribute('href') || '';
        if (!href) continue;
        const full = href.startsWith('http') ? href : ('https://www.oddsportal.com' + href);
        if (!/\/football\/.+\/.+\/.+/.test(full)) continue;
        if (!/\/[^\/]+\/$/.test(full)) continue;

        const text = (a.textContent || '').trim();
        if (!text) continue;

        let dateText = '';
        let home = '';
        let away = '';
        const row = a.closest('div,li,tr,article') || a.parentElement;
        if (row) {
          const t = (row.textContent || '').replace(/\s+/g, ' ').trim();
          const m = t.match(/(\d{1,2}\.\d{1,2}\.\d{4}|\d{4}-\d{2}-\d{2})/);
          if (m) dateText = m[1];
          const vs = t.match(/([A-Za-z0-9 .\-']+)\s+(?:-|vs|v)\s+([A-Za-z0-9 .\-']+)/i);
          if (vs) {
            home = (vs[1] || '').trim();
            away = (vs[2] || '').trim();
          }
        }

        rows.push({
          match_url: full,
          anchor_text: text,
          date_text: dateText,
          home_team: home,
          away_team: away,
          source_page: window.location.href,
        });
      }
      return rows;
    }
    """
    raw = await page.evaluate(js)

    out: list[dict] = []
    seen = set()
    for r in raw:
        url = str(r.get("match_url") or "").split("#", 1)[0]
        if not url:
            continue
        # Stay in same competition path where possible.
        if "/football/" not in url:
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "match_url": url,
                "date_text": r.get("date_text") or "",
                "home_team": r.get("home_team") or "",
                "away_team": r.get("away_team") or "",
                "anchor_text": r.get("anchor_text") or "",
                "source_page": r.get("source_page") or base_url,
            }
        )
    return out


async def scrape_match_list(
    listing_url: str,
    max_pages: int = 40,
    headless: bool = False,
    settle_ms: int = 1800,
) -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(listing_url, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(settle_ms)

        all_rows: dict[str, dict] = {}
        visited = set()

        for i in range(max_pages):
            cur = page.url
            if cur in visited:
                break
            visited.add(cur)

            rows = await _collect_rows(page, listing_url)
            for r in rows:
                all_rows.setdefault(r["match_url"], r)

            # next-page best effort
            next_clicked = False
            for sel in [
                "a[rel='next']",
                "a:has-text('Next')",
                "button:has-text('Next')",
                "a[data-testid='pagination-next']",
            ]:
                loc = page.locator(sel).first
                try:
                    if await loc.count() and await loc.is_visible():
                        await loc.click(timeout=2500)
                        await page.wait_for_timeout(settle_ms)
                        next_clicked = True
                        break
                except Exception:
                    pass

            if not next_clicked:
                # try hash page increment fallback
                if "#/page/" in page.url:
                    m = re.search(r"#/page/(\d+)", page.url)
                    if m:
                        nxt = int(m.group(1)) + 1
                        nxt_url = re.sub(r"#/page/\d+", f"#/page/{nxt}", page.url)
                        if nxt_url not in visited:
                            await page.goto(nxt_url, wait_until="domcontentloaded", timeout=120000)
                            await page.wait_for_timeout(settle_ms)
                            continue
                break

        await context.close()
        await browser.close()
        return list(all_rows.values())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build OddsPortal season match-url list from listing/calendar URL")
    p.add_argument("--url-template", required=True, help="Competition listing URL template; can include {season}")
    p.add_argument("--season", required=True, help="Season label, e.g. 2015-2016")
    p.add_argument("--competition", required=True, help="Competition label (used in metadata/file name)")
    p.add_argument("--max-pages", type=int, default=40)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--settle-ms", type=int, default=1800)
    p.add_argument("--out-dir", default="data/oddsportal_history")
    return p.parse_args()


async def _run(args: argparse.Namespace) -> int:
    url = resolve_url(args.url_template, args.season)
    rows = await scrape_match_list(
        listing_url=url,
        max_pages=args.max_pages,
        headless=args.headless,
        settle_ms=args.settle_ms,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    matchlists_dir = out_dir / "match_lists"
    matchlists_dir.mkdir(parents=True, exist_ok=True)

    base = f"{slugify(args.competition)}_{slugify(args.season)}"
    out_jsonl = matchlists_dir / f"{base}.jsonl"

    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in rows:
            payload = {
                "competition": args.competition,
                "season": args.season,
                "listing_url": url,
                "scraped_at_utc": now_iso(),
                **r,
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    manifest = {
        "competition": args.competition,
        "season": args.season,
        "listing_url": url,
        "count": len(rows),
        "output": str(out_jsonl),
        "generated_at_utc": now_iso(),
    }
    (matchlists_dir / f"{base}.meta.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(parse_args())))
