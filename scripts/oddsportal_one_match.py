#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

DEFAULT_MATCH_URL = "https://www.oddsportal.com/football/england/premier-league/brentford-wolves-0jR7cwU6/#1X2;2"
DEFAULT_MARKET = "1X2"
DEFAULT_STORAGE_STATE_PATH = Path("/tmp/oddsportal_storage.json")
DEFAULT_OUTPUT_PATH = Path("/tmp/oddsportal_match.json")

MARKET_TO_TAB = {
    "1X2": "1X2",
    "OU": "Over/Under",
    "AH": "Asian Handicap",
}
MARKET_TO_FRAGMENT = {
    "1X2": "#1X2;2",
    "OU": "#over-under;2",
    "AH": "#ah;2",
}


def to_float(value: str | None):
    if value is None:
        return None
    value = value.strip().replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def round_line(line: float | None) -> float | None:
    if line is None:
        return None
    return round(float(line), 3)


def parse_line_csv(value: str | None) -> list[float]:
    if not value:
        return []
    out: list[float] = []
    for token in value.split(","):
        v = to_float(token)
        if v is not None:
            out.append(round_line(v))
    dedup: list[float] = []
    seen = set()
    for v in out:
        if v not in seen:
            dedup.append(v)
            seen.add(v)
    return dedup


def normalize_market_type(market: str | None) -> str:
    m = (market or "1X2").strip().upper().replace(" ", "")
    if m in {"1X2", "3WAY", "HDA"}:
        return "1X2"
    if m in {"OU", "O/U", "OVERUNDER", "TOTALS"}:
        return "OU"
    if m in {"AH", "ASIANHANDICAP", "HANDICAP"}:
        return "AH"
    return (market or "1X2").strip().upper()


def _canonical_market_url(match_url: str, market_type: str) -> str:
    base = match_url.split("#", 1)[0]
    fragment = MARKET_TO_FRAGMENT.get(market_type, "")
    return f"{base}{fragment}" if fragment else match_url


def _extract_line_from_text(text: str, market_type: str) -> float | None:
    s = text.replace("−", "-")
    pats: list[str]
    if market_type == "OU":
        pats = [
            r"(?:OVER/UNDER|OVER\s*UNDER|O/U)\s*([+\-]?\d+(?:[\.,]\d+)?)",
            r"\b([+\-]?\d+(?:[\.,]\d+)?)\b",
        ]
    elif market_type == "AH":
        pats = [
            r"(?:ASIAN\s*HANDICAP|AH|HANDICAP)\s*([+\-]?\d+(?:[\.,]\d+)?)",
            r"\b([+\-]?\d+(?:[\.,]\d+)?)\b",
        ]
    else:
        return None

    for pat in pats:
        m = re.search(pat, s, flags=re.IGNORECASE)
        if not m:
            continue
        v = to_float(m.group(1))
        if v is None:
            continue
        if market_type == "OU" and 0.0 <= v <= 15.0:
            return round_line(v)
        if market_type == "AH" and -10.0 <= v <= 10.0:
            return round_line(v)
    return None


def _select_main_lines(
    quotes: list[dict],
    top_lines: int,
    preferred_lines: Iterable[float] | None = None,
    fixed_lines: Iterable[float] | None = None,
) -> tuple[list[float], dict[float, int]]:
    freq_pairs: set[tuple[float, str]] = set()
    for q in quotes:
        line = round_line(q.get("line"))
        bm = (q.get("bookmaker") or "").strip().lower()
        if line is None or not bm:
            continue
        freq_pairs.add((line, bm))

    counter: Counter[float] = Counter()
    for line, _bm in freq_pairs:
        counter[line] += 1

    ranked = sorted(counter.keys(), key=lambda x: (-counter[x], x))

    fixed = [round_line(x) for x in (fixed_lines or []) if x is not None]
    if fixed:
        return fixed, dict(counter)

    preferred = {round_line(x) for x in (preferred_lines or []) if x is not None}
    if preferred:
        constrained = [x for x in ranked if x in preferred]
        if constrained:
            ranked = constrained

    k = max(1, int(top_lines))
    return ranked[:k], dict(counter)


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


async def _goto_market(page, match_url: str, market_type: str, timeout_ms: int, settle_ms: int) -> str:
    canonical_url = _canonical_market_url(match_url, market_type)
    await page.goto(canonical_url, wait_until="domcontentloaded", timeout=timeout_ms)
    await accept_consent_if_present(page)
    await page.wait_for_timeout(settle_ms)

    tab_text = MARKET_TO_TAB.get(market_type)
    if tab_text:
        tab = page.locator(
            "[data-testid='navigation-active-tab'], [data-testid='navigation-inactive-tab']",
            has_text=tab_text,
        ).first
        if await tab.count():
            await tab.click(timeout=5000)
            await page.wait_for_timeout(800)

    active = page.locator("[data-testid='navigation-active-tab']").first
    if await active.count():
        return ((await active.inner_text()) or "").strip()
    return ""


async def _extract_odds_from_expanded_row(row, expected_outcomes: int) -> list[float]:
    vals: list[float] = []

    odds_links = row.locator("div[data-testid='odd-container'] a.odds-link")
    for j in range(await odds_links.count()):
        v = to_float((await odds_links.nth(j).inner_text()).strip())
        if v is not None:
            vals.append(v)

    if len(vals) >= expected_outcomes:
        return vals[:expected_outcomes]

    vals = []
    boxes = row.locator("div[data-testid='odd-container']")
    for j in range(await boxes.count()):
        txt = (await boxes.nth(j).inner_text()).strip().replace("\n", " ")
        m = re.search(r"(?<!\d)(\d+(?:[\.,]\d+)?)(?!\d)", txt)
        if m:
            v = to_float(m.group(1))
            if v is not None:
                vals.append(v)

    return vals[:expected_outcomes]


async def extract_odds(
    match_url: str,
    market: str = DEFAULT_MARKET,
    storage_state_path: Path = DEFAULT_STORAGE_STATE_PATH,
    headless: bool = False,
    timeout_ms: int = 120000,
    settle_ms: int = 2500,
    top_lines: int = 2,
    prefer_lines: Iterable[float] | None = None,
    fixed_lines: Iterable[float] | None = None,
    debug: bool = False,
) -> dict:
    market_type = normalize_market_type(market)
    expected_outcomes = 3 if market_type == "1X2" else 2

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            await ensure_storage_state(browser, _canonical_market_url(match_url, market_type), storage_state_path)

            context = await browser.new_context(storage_state=str(storage_state_path))
            page = await context.new_page()
            active_tab = await _goto_market(page, match_url, market_type, timeout_ms, settle_ms)

            result = {
                "match_url": match_url,
                "market": market,
                "market_type": market_type,
                "snapshot_ts_utc": datetime.now(timezone.utc).isoformat(),
                "detected_market_tab": active_tab,
                "row_count_seen": 0,
                "odds": [],
                "errors": [],
                "available_lines": [],
                "selected_lines": [],
                "line_frequency": {},
            }

            if market_type == "1X2":
                row_selector = "div[data-testid='over-under-expanded-row'], div.border-black-borders.flex.h-9"
                await page.wait_for_selector(row_selector, state="visible", timeout=60000)
                await page.wait_for_timeout(settle_ms)
                rows = page.locator(row_selector)
                row_count = await rows.count()
                result["row_count_seen"] = row_count

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

                    odd_values = await _extract_odds_from_expanded_row(row, expected_outcomes=3)
                    raw_text = (await row.inner_text()).strip().replace("\n", " ")

                    if bookmaker_name and len(odd_values) == 3:
                        result["odds"].append(
                            {
                                "bookmaker": bookmaker_name,
                                "market_type": "1X2",
                                "line": None,
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

            # OU / AH: parse collapsed lines and expand each line to parse bookmaker rows.
            collapsed_selector = "div[data-testid='over-under-collapsed-row']"
            await page.wait_for_selector(collapsed_selector, state="visible", timeout=60000)
            await page.wait_for_timeout(settle_ms)
            collapsed_rows = page.locator(collapsed_selector)
            collapsed_count = await collapsed_rows.count()
            result["row_count_seen"] = collapsed_count

            all_quotes: list[dict] = []
            available_lines: list[float] = []

            for i in range(collapsed_count):
                collapsed = collapsed_rows.nth(i)
                collapsed_text = (await collapsed.inner_text()).strip().replace("\n", " ")
                line = _extract_line_from_text(collapsed_text, market_type=market_type)
                if line is None:
                    continue
                available_lines.append(line)

                try:
                    await collapsed.click(timeout=5000)
                    await page.wait_for_timeout(450)
                except Exception as e:
                    result["errors"].append(
                        {
                            "row_index": i,
                            "bookmaker": None,
                            "reason": f"line_expand_click_failed: {e}",
                        }
                    )
                    continue

                expanded = page.locator("div[data-testid='over-under-expanded-row']")
                exp_count = await expanded.count()
                if exp_count == 0:
                    continue

                for j in range(exp_count):
                    row = expanded.nth(j)
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

                    odd_values = await _extract_odds_from_expanded_row(row, expected_outcomes=2)
                    raw_text = (await row.inner_text()).strip().replace("\n", " ")

                    line_in_row = line
                    line_loc = row.locator("[data-testid='outrights-expanded-hcp']").first
                    if await line_loc.count():
                        parsed_line = _extract_line_from_text((await line_loc.inner_text()).strip(), market_type=market_type)
                        if parsed_line is not None:
                            line_in_row = parsed_line

                    # Filter out expanded rows that belong to other opened lines.
                    if line_in_row is None or abs(line_in_row - line) > 1e-6:
                        continue

                    if bookmaker_name and len(odd_values) == 2:
                        all_quotes.append(
                            {
                                "bookmaker": bookmaker_name,
                                "market_type": market_type,
                                "line": line_in_row,
                                "home": odd_values[0],
                                "draw": None,
                                "away": odd_values[1],
                                "timestamp": result["snapshot_ts_utc"],
                                "raw": raw_text[:500],
                            }
                        )
                    else:
                        result["errors"].append(
                            {
                                "row_index": i,
                                "bookmaker": bookmaker_name,
                                "reason": "missing_bookmaker_or_2way_odds_or_line",
                            }
                        )

            # Deduplicate possible repeated rows per bookmaker+line inside one snapshot.
            dedup: dict[tuple[str, float], dict] = {}
            for q in all_quotes:
                key = ((q.get("bookmaker") or "").strip().lower(), round_line(q.get("line")))
                if key[0] and key[1] is not None:
                    dedup[key] = q
            all_quotes = list(dedup.values())

            selected_lines, freq = _select_main_lines(
                all_quotes,
                top_lines=top_lines,
                preferred_lines=prefer_lines,
                fixed_lines=fixed_lines,
            )
            selected_set = {round_line(x) for x in selected_lines}
            result["available_lines"] = sorted({round_line(x) for x in available_lines if x is not None})
            result["selected_lines"] = selected_lines
            result["line_frequency"] = {str(k): v for k, v in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))}
            result["odds"] = [q for q in all_quotes if round_line(q.get("line")) in selected_set]

            if debug:
                sample = result["odds"][:5]
                print(
                    f"[debug] market={market_type} tab={active_tab} available_lines={result['available_lines']} "
                    f"top_lines={selected_lines} sample_quotes={json.dumps(sample, ensure_ascii=False)}"
                )

            await context.close()
            return result
        finally:
            await browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract one OddsPortal match market odds snapshot")
    parser.add_argument("--match-url", default=DEFAULT_MATCH_URL, help="OddsPortal match URL")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="Market label (e.g. 1X2, OU, AH)")
    parser.add_argument("--storage-state", default=str(DEFAULT_STORAGE_STATE_PATH), help="Playwright storage state JSON path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Output JSON path (use '-' to skip file write)")
    parser.add_argument("--headless", action="store_true", help="Run Chromium in headless mode")
    parser.add_argument("--timeout-ms", type=int, default=120000, help="Navigation timeout in milliseconds")
    parser.add_argument("--settle-ms", type=int, default=2500, help="Post-render settle wait in milliseconds")
    parser.add_argument("--top-lines", type=int, default=2, help="Top-K lines to keep for OU/AH (default: 2)")
    parser.add_argument(
        "--prefer-lines",
        default="",
        help="Preferred lines CSV (e.g. '2.5,2.75'). If present, selection is constrained when possible.",
    )
    parser.add_argument(
        "--fixed-lines",
        default="",
        help="Fixed lines CSV to enforce (for pinned tracking across snapshots).",
    )
    parser.add_argument("--debug", action="store_true", help="Print debug summary (market/lines/sample quotes)")
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
        top_lines=args.top_lines,
        prefer_lines=parse_line_csv(args.prefer_lines),
        fixed_lines=parse_line_csv(args.fixed_lines),
        debug=args.debug,
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
