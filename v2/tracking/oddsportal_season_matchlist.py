#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
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
    """Return True if the last path segment looks like an OddsPortal match slug.

    Examples:
      - team-a-team-b-0jR7cwU6
      - newcastle-utd-tottenham-xYXMWvIM

    Note: the trailing id token is often alnum, but it may contain *no digits*.
    So we only require:
      - hyphenated slug
      - trailing id token: at least one letter, only [a-z0-9], length>=5
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


def decrypt_payload(enc: str, decrypt_js: str) -> dict[str, Any]:
    # Prefer node decrypt (keeps parity with existing scripts).
    p = subprocess.run(["node", decrypt_js], input=enc, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "decrypt failed")
    return json.loads(p.stdout)


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
    decrypt_js: str = "scripts/oddsportal_decrypt_match_event.js",
) -> list[dict]:
    """Scrape match list for a season.

    Approach:
    - Use Playwright to capture the ajax-sport-country-tournament-archive_ base URL.
    - Then fetch each archive page via requests (fast/stable), decrypt with node JS,
      and extract match URLs from the returned rows.

    This avoids fragile SPA pagination / hash routing.
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        archive_urls: list[str] = []

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

        await page.goto(listing_url, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(settle_ms)

        # accept cookie if present
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
                    await page.wait_for_timeout(1200)
                    break
            except Exception:
                pass

        # trigger archive XHR
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        await page.wait_for_timeout(2500)

        await context.close()
        await browser.close()

    if not archive_urls:
        raise RuntimeError("could not capture archive XHR url")

    def _norm_base(x: str) -> str:
        x = (x or "").split("?_=")[0].rstrip("/")
        x = re.sub(r"/page/\d+$", "", x)
        return x

    # We may capture multiple archive URLs; pick the one that yields the largest archive.
    candidates: list[str] = []
    seen = set()
    for u0 in archive_urls:
        b0 = _norm_base(u0)
        if b0 and b0 not in seen:
            seen.add(b0)
            candidates.append(b0)

    def _fetch_meta(base: str) -> tuple[int, int]:
        """Return (pageCount, totalRows) best-effort for base using page 1."""
        try:
            url = f"{base}/page/1/"
            r = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept-Encoding": "identity",
                },
                timeout=30,
            )
            r.raise_for_status()
            j = decrypt_payload(r.text.strip(), decrypt_js)
            d = j.get("d") or {}
            pg = d.get("pagination") or {}
            page_count = int(pg.get("pageCount") or 0) if isinstance(pg, dict) else 0
            total = int(d.get("total") or 0)
            # Fallback if total missing
            if total <= 0:
                total = len(d.get("rows") or [])
            return page_count, total
        except Exception:
            return 0, 0

    best = candidates[-1]
    best_meta = (0, 0)
    for c in candidates:
        meta = _fetch_meta(c)
        if meta > best_meta:
            best = c
            best_meta = meta

    u = best

    all_rows: dict[str, dict] = {}

    for pn in range(1, max_pages + 1):
        url = f"{u}/page/{pn}/"
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "X-Requested-With": "XMLHttpRequest",
                "Accept-Encoding": "identity",
            },
            timeout=30,
        )
        r.raise_for_status()
        j = decrypt_payload(r.text.strip(), decrypt_js)

        rows = (j.get("d") or {}).get("rows") or []
        if not rows:
            break

        for row in rows:
            match_url = row.get("url")
            if not isinstance(match_url, str):
                continue
            normalized = normalize_match_url("https://www.oddsportal.com" + match_url, listing_url)
            if not normalized:
                continue
            all_rows.setdefault(
                normalized,
                {
                    "match_url": normalized,
                    "date_text": "",
                    "home_team": _normalize_text(row.get("home-name") or ""),
                    "away_team": _normalize_text(row.get("away-name") or ""),
                    "anchor_text": "",
                    "source_page": listing_url,
                },
            )

        # Stop early if pagination says no more.
        pg = (j.get("d") or {}).get("pagination") or {}
        if isinstance(pg, dict) and pn >= int(pg.get("pageCount") or 0):
            break

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
