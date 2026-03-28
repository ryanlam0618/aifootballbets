#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

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


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _looks_like_match_slug(last_segment: str) -> bool:
    """
    OddsPortal match pages usually look like:
      /football/.../team-a-team-b-0jR7cwU6/
    We require:
      - hyphenated slug
      - trailing id token with mixed alnum (at least one letter + one digit)
    """
    seg = (last_segment or "").strip().lower()
    if not seg or "-" not in seg:
        return False

    # Exclude season index-like tails (e.g. 2021-2022)
    if re.fullmatch(r"\d{4}-\d{2,4}", seg):
        return False

    parts = [p for p in seg.split("-") if p]
    if len(parts) < 3:
        return False

    id_token = parts[-1]
    if len(id_token) < 5:
        return False
    if not re.search(r"[a-z]", id_token):
        return False
    if not re.search(r"\d", id_token):
        return False
    if not re.fullmatch(r"[a-z0-9]+", id_token):
        return False

    return True


def listing_context(listing_url: str) -> tuple[str, str]:
    """
    Parse listing context for competition scoping.
    Returns (country_slug, competition_slug_base).
    """
    p = urlparse(listing_url)
    segments = [s for s in (p.path or "").lower().split("/") if s]
    # e.g. /football/england/premier-league-2021-2022/results/
    #      -> country=england, competition_base=premier-league
    if len(segments) >= 3 and segments[0] == "football":
        country = segments[1]
        comp = segments[2]
        comp = re.sub(r"-\d{4}-\d{2,4}$", "", comp)
        return country, comp
    return "", ""


def normalize_match_url(raw_url: str, listing_url: str) -> str | None:
    full = urljoin("https://www.oddsportal.com", raw_url or "")
    p = urlparse(full)

    if p.scheme not in {"http", "https"}:
        return None
    if "oddsportal.com" not in (p.netloc or ""):
        return None

    path = p.path or ""
    if not path.startswith("/football/"):
        return None

    # Canonical trailing slash and strip query/fragment.
    if not path.endswith("/"):
        path = path + "/"

    low = path.lower()

    # Exclude section/index pages.
    if low.endswith("/results/") or low.endswith("/standings/") or low.endswith("/outrights/"):
        return None

    segments = [s for s in low.split("/") if s]
    # expected at least: football / country / competition / match-slug
    if len(segments) < 4:
        return None

    # Scope to listing competition path to avoid unrelated sidebar links.
    expected_country, expected_comp = listing_context(listing_url)
    if expected_country and segments[1] != expected_country:
        return None
    if expected_comp and not (
        segments[2] == expected_comp or segments[2].startswith(expected_comp + "-")
    ):
        return None

    last = segments[-1]
    if not _looks_like_match_slug(last):
        return None

    return f"{p.scheme}://{p.netloc}{path}"


async def _collect_rows(page, base_url: str) -> list[dict]:
    js = """
    () => {
      const rows = [];
      const anchors = Array.from(document.querySelectorAll('a[href*="/football/"]'));

      const badTail = /\/(results|standings|outrights)\/?$/i;
      const seasonTail = /\/\d{4}-\d{2,4}\/?$/;
      // Require hyphenated match key with trailing mixed-alnum id token.
      const matchTail = /\/([a-z0-9]+(?:-[a-z0-9]+)+-[a-z0-9]*[a-z][a-z0-9]*\d[a-z0-9]*)\/?$/i;

      for (const a of anchors) {
        const href = (a.getAttribute('href') || '').trim();
        if (!href) continue;

        const full = href.startsWith('http') ? href : ('https://www.oddsportal.com' + href);
        const noHash = full.split('#')[0].split('?')[0];

        if (!/\/football\//i.test(noHash)) continue;
        if (!/\/$/.test(noHash)) continue;
        if (badTail.test(noHash)) continue;
        if (seasonTail.test(noHash)) continue;
        if (!matchTail.test(noHash)) continue;

        const text = (a.textContent || '').replace(/\s+/g, ' ').trim();

        let dateText = '';
        let home = '';
        let away = '';

        const row = a.closest('tr,li,article,section,div') || a.parentElement;
        if (row) {
          const t = (row.textContent || '').replace(/\s+/g, ' ').trim();
          const d = t.match(/(\d{1,2}\.\d{1,2}\.\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}\/\d{1,2}\/\d{4})/);
          if (d) dateText = d[1];

          // Try team parsing from either row text or anchor text.
          const source = text || t;
          const vs = source.match(/([^\-]+?)\s+(?:-|vs|v)\s+(.+)/i);
          if (vs) {
            home = (vs[1] || '').trim();
            away = (vs[2] || '').trim();
          }
        }

        rows.push({
          match_url: noHash,
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
    seen: set[str] = set()
    for r in raw:
        normalized = normalize_match_url(str(r.get("match_url") or ""), base_url)
        if not normalized:
            continue

        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)

        out.append(
            {
                "match_url": normalized,
                "date_text": _normalize_text(r.get("date_text") or ""),
                "home_team": _normalize_text(r.get("home_team") or ""),
                "away_team": _normalize_text(r.get("away_team") or ""),
                "anchor_text": _normalize_text(r.get("anchor_text") or ""),
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

        for _ in range(max_pages):
            cur = page.url
            if cur in visited:
                break
            visited.add(cur)

            rows = await _collect_rows(page, listing_url)
            for r in rows:
                # Dedup by match_url (priority requirement)
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
    p.add_argument("--settle-ms", type=int, default=6500)
    p.add_argument("--min-match-urls", type=int, default=0, help="Optional sanity threshold. Non-zero exit if count is below this value.")
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

    count_ok = True
    if args.min_match_urls and len(rows) < args.min_match_urls:
        count_ok = False

    manifest = {
        "competition": args.competition,
        "season": args.season,
        "listing_url": url,
        "count": len(rows),
        "min_match_urls": args.min_match_urls,
        "count_ok": count_ok,
        "output": str(out_jsonl),
        "generated_at_utc": now_iso(),
    }
    (matchlists_dir / f"{base}.meta.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if count_ok else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(parse_args())))
