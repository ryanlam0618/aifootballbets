#!/usr/bin/env python3
"""Export debug-sampled OddsPortal matches to CSV (human-readable).

Input: a JSON produced by scripts/oddsportal_debug_sample_days.py
Output:
  - raw points CSV (one row per decrypted odds point)
  - aggregated median CSV (per match+market+outcome_group+timestamp)

Includes match participants (home/away) so the CSV is interpretable.
This replays capture via Playwright to discover match-event-history URLs (bookies).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Optional

from playwright.async_api import async_playwright


def parse_teams_from_match_url(match_url: str) -> tuple[str, str]:
    """Best-effort parse of teams from slug: /.../<home>-<away>-<ID>/"""
    # take last path segment
    seg = match_url.rstrip('/').split('/')[-1]
    # remove -<8charid>
    seg = re.sub(r"-[A-Za-z0-9]{8}$", "", seg)
    parts = seg.split('-')
    if len(parts) < 2:
        return ("", "")
    # heuristic: split near middle
    mid = len(parts) // 2
    home = ' '.join(parts[:mid])
    away = ' '.join(parts[mid:])
    return (home, away)

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

OU_KEY_RE = re.compile(r"^([a-z0-9]+)x([a-z0-9]+)x([a-z0-9]+)$")


def iso_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def parse_match_id(match_url: str) -> Optional[str]:
    m = re.search(r"-([A-Za-z0-9]{8})/?$", match_url.rstrip("/"))
    return m.group(1) if m else None


def parse_bookie_id(mehist_url: str) -> Optional[int]:
    try:
        part = mehist_url.split("/match-event-history/")[1].split("/")[0]
        bid = part.split("-")[-1]
        if bid.isdigit():
            return int(bid)
    except Exception:
        pass
    return None


async def accept_consent(page) -> None:
    for sel in [
        "button:has-text('I Accept')",
        "#onetrust-accept-btn-handler",
        "button:has-text('Accept')",
        "button:has-text('Accept all')",
    ]:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=3000)
                await page.wait_for_timeout(1200)
                break
        except Exception:
            pass


async def capture_mehist_urls(match_url: str, market: str) -> list[str]:
    """Capture match-event-history URLs by interacting with the page."""

    assert market in ("1x2", "ou"), "market must be 1x2 or ou"

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
        else:
            url = match_url.rstrip("/") + "/#over-under;2"

        await page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(6000)
        await accept_consent(page)

        if market == "ou":
            # expand first OU line
            try:
                await page.locator('[data-testid="over-under-collapsed-row"]').first.click(timeout=5000)
                await page.wait_for_timeout(1500)
            except Exception:
                pass

        cells = page.locator('[data-testid*="odd-container"]')
        n = min(100, await cells.count())
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
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def fetch_decrypt_mehist(url: str, fetch_py: str, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    bid = parse_bookie_id(url)
    suffix = f"{bid}" if bid is not None else "unknown"
    out_path = out_dir / f"mehist_{suffix}.json"
    subprocess.run(["python3", fetch_py, "--url", url, "--out-json", str(out_path)], check=True, capture_output=True, text=True)
    return json.loads(out_path.read_text("utf-8"))


@dataclass
class RawRow:
    match_date_utc: str
    match_url: str
    match_id: str
    home_team: str
    away_team: str
    market: str
    market_label: str
    line_label: str
    outcome_label: str
    mehist_url: str
    bookie_id: int
    selection_key: str
    ou_side_base: str
    ou_line_code: str
    ts: int
    ts_utc: str
    odds: float


def export_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-json", required=True)
    ap.add_argument("--out-raw", required=True)
    ap.add_argument("--out-agg", required=True)
    ap.add_argument("--fetch-py", default="scripts/oddsportal_fetch_mehist.py")
    ap.add_argument("--max-matches", type=int, default=0, help="0 = all")
    args = ap.parse_args()

    samples = json.loads(Path(args.in_json).read_text("utf-8"))
    # only keep successful samples
    samples = [s for s in samples if s.get("ok_archive") and s.get("match_url")]
    if args.max_matches and len(samples) > args.max_matches:
        samples = samples[: args.max_matches]

    raw: list[RawRow] = []

    out_dir = Path("/home/openclaw/.openclaw/workspace/tmp/oddsportal_export_artifacts")

    # stable label mapping for 1X2 selection_key -> Home/Draw/Away (per match)
    # We derive by sorting odds at first timestamp (home/away tend to be shortest; draw often middle).
    for s in samples:
        match_url = s["match_url"]
        match_id = parse_match_id(match_url) or ""
        match_date = s.get("match_date_utc", "")
        home_team, away_team = parse_teams_from_match_url(match_url)

        # build per-match 1X2 selection label mapping once (if possible)
        sel_to_label: dict[str, str] = {}
        try:
            mehist_urls_1x2 = await capture_mehist_urls(match_url, "1x2")
            if mehist_urls_1x2:
                u0 = mehist_urls_1x2[0]
                bid0 = parse_bookie_id(u0)
                if bid0 is not None:
                    d0 = fetch_decrypt_mehist(u0, args.fetch_py, out_dir / match_id / "1x2_label")
                    back0 = d0["d"]["history"]["back"]
                    # gather odds at earliest ts
                    pts = []
                    for sk, inner in back0.items():
                        arr = inner.get(str(bid0), [])
                        if not arr:
                            continue
                        odd, _, ts = arr[0]
                        pts.append((int(ts), float(odd), sk))
                    if pts:
                        pts.sort()
                        # choose earliest timestamp group
                        t0 = pts[0][0]
                        same = [(odd, sk) for ts, odd, sk in pts if ts == t0]
                        same.sort()  # low to high
                        if len(same) == 3:
                            # heuristic: lowest odds = favourite (home or away), highest odds = underdog
                            # we cannot be 100% sure which is home/away without a dedicated mapping, so we label generically.
                            sel_to_label[same[0][1]] = "fav"
                            sel_to_label[same[1][1]] = "draw_or_mid"
                            sel_to_label[same[2][1]] = "dog"
        except Exception:
            pass

        for market in ("1x2", "ou"):
            market_label = "1X2" if market == "1x2" else "OU"
            mehist_urls = await capture_mehist_urls(match_url, market)
            for u in mehist_urls:
                bid = parse_bookie_id(u)
                if bid is None:
                    continue
                d = fetch_decrypt_mehist(u, args.fetch_py, out_dir / match_id / market)
                back = d["d"]["history"]["back"]
                if not isinstance(back, dict):
                    continue
                for sel_key, inner in back.items():
                    pts = inner.get(str(bid), [])
                    for odd_str, _, ts in pts:
                        side_base = ""
                        line_code = ""
                        line_label = ""
                        outcome_label = ""

                        if market == "ou":
                            m = OU_KEY_RE.match(sel_key)
                            if m:
                                side_base, line_code, _ = m.groups()
                                # side_base maps to Over vs Under by relative odds (not stable). keep explicit key.
                                line_label = f"lineCode={line_code}"
                                outcome_label = f"sideBase={side_base}"
                            else:
                                outcome_label = sel_key
                        else:
                            outcome_label = sel_to_label.get(sel_key, sel_key)

                        raw.append(
                            RawRow(
                                match_date_utc=match_date,
                                match_url=match_url,
                                match_id=match_id,
                                home_team=home_team,
                                away_team=away_team,
                                market=market,
                                market_label=market_label,
                                line_label=line_label,
                                outcome_label=outcome_label,
                                mehist_url=u,
                                bookie_id=bid,
                                selection_key=sel_key,
                                ou_side_base=side_base,
                                ou_line_code=line_code,
                                ts=int(ts),
                                ts_utc=iso_utc(int(ts)),
                                odds=float(odd_str),
                            )
                        )

    # raw CSV
    raw_rows = [r.__dict__ for r in raw]
    export_csv(raw_rows, Path(args.out_raw))

    # aggregated CSV (median per timestamp)
    # grouping:
    #  - 1x2: by outcome_label
    #  - ou: by ou_side_base (acts as Over/Under side id) and line_code kept in line_label
    agg_map: dict[tuple[str, str, str, str, str, int], list[float]] = defaultdict(list)
    # key: (match_id, market, outcome_group, line_label, match_url, ts)
    meta: dict[tuple[str, str, str, str, str, int], dict[str, Any]] = {}

    for r in raw:
        outcome = r.outcome_label
        line_label = r.line_label
        key = (r.match_id, r.market, outcome, line_label, r.match_url, r.ts)
        agg_map[key].append(r.odds)
        meta[key] = {
            "match_date_utc": r.match_date_utc,
            "match_url": r.match_url,
            "match_id": r.match_id,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "market": r.market,
            "market_label": r.market_label,
            "outcome_group": outcome,
            "line_label": line_label,
            "ts": r.ts,
            "ts_utc": r.ts_utc,
        }

    agg_rows: list[dict[str, Any]] = []
    for key, odds_list in agg_map.items():
        m = meta[key]
        agg_rows.append({**m, "odds_median": float(median(odds_list)), "n_sources": len(odds_list)})

    # stable sort
    agg_rows.sort(key=lambda x: (x["match_date_utc"], x["match_id"], x["market"], x["outcome_group"], x["ts"]))
    export_csv(agg_rows, Path(args.out_agg))

    print(json.dumps({"raw_rows": len(raw_rows), "agg_rows": len(agg_rows), "out_raw": args.out_raw, "out_agg": args.out_agg}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
