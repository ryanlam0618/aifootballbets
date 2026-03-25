#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

DEFAULT_MATCH_URL = "https://www.oddsportal.com/football/england/premier-league/brentford-wolves-0jR7cwU6/#1X2;2"
DEFAULT_MARKET = "1X2"
DEFAULT_STORAGE_STATE_PATH = Path("/tmp/oddsportal_storage.json")
DEFAULT_OUTPUT_PATH = Path("/tmp/oddsportal_match.json")
DEFAULT_ARTIFACTS_DIR = Path("/tmp/oddsportal_artifacts")

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

FAILURE_DIAG_SELECTORS = {
    "rows_expanded": "div[data-testid='over-under-expanded-row']",
    "rows_collapsed": "div[data-testid='over-under-collapsed-row']",
    "bookmakers": "p[data-testid='outrights-expanded-bookmaker-name']",
    "odd_links": "div[data-testid='odd-container'] a.odds-link",
    "consent_btn": "#onetrust-accept-btn-handler",
    "cf_iframe": "iframe[src*='challenge'], iframe[src*='captcha']",
    "main": "main",
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
    try:
        await page.wait_for_load_state("networkidle", timeout=min(15000, timeout_ms))
    except Exception:
        pass

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


async def _wait_for_market_rows(page, market_type: str, timeout_ms: int):
    if market_type == "1X2":
        selectors = [
            "div[data-testid='over-under-expanded-row']",
            "div[data-testid='odd-container'] a.odds-link",
            "p[data-testid='outrights-expanded-bookmaker-name']",
        ]
    else:
        selectors = [
            "div[data-testid='over-under-collapsed-row']",
            "div[data-testid='over-under-expanded-row']",
        ]

    last_err: Exception | None = None
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, state="visible", timeout=timeout_ms)
            return sel
        except Exception as e:
            last_err = e

    if last_err:
        raise last_err
    raise RuntimeError("market rows did not appear")


async def _collect_diag_counts(page) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, selector in FAILURE_DIAG_SELECTORS.items():
        try:
            counts[name] = await page.locator(selector).count()
        except Exception:
            counts[name] = -1
    return counts


async def _detect_block_signals(page) -> dict[str, bool]:
    signals = {
        "just_a_moment": False,
        "captcha": False,
        "cloudflare_challenge": False,
        "consent_visible": False,
    }
    try:
        text = ((await page.inner_text("body")) or "").lower()
        signals["just_a_moment"] = "just a moment" in text
        signals["captcha"] = "captcha" in text
        signals["cloudflare_challenge"] = "cloudflare" in text or "cf-challenge" in text
    except Exception:
        pass
    try:
        btn = page.locator("#onetrust-accept-btn-handler").first
        signals["consent_visible"] = bool(await btn.count() and await btn.is_visible())
    except Exception:
        pass
    return signals


def _artifact_run_dir(artifacts_dir: Path, market_type: str, attempt: int) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    d = artifacts_dir / f"{ts}_{market_type}_attempt{attempt}"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _capture_failure_artifacts(
    context,
    page,
    run_dir: Path,
    reason: str,
    err: Exception,
    match_url: str,
    market_type: str,
    traces_started: bool,
) -> None:
    meta: dict[str, Any] = {
        "reason": reason,
        "error": str(err),
        "error_type": type(err).__name__,
        "match_url": match_url,
        "market_type": market_type,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    try:
        meta["current_url"] = page.url
    except Exception:
        pass
    try:
        meta["title"] = await page.title()
    except Exception:
        pass

    try:
        screenshot_path = run_dir / "failure.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        meta["screenshot"] = str(screenshot_path)
    except Exception as e:
        meta["screenshot_error"] = str(e)

    try:
        html_path = run_dir / "failure.html"
        html_path.write_text(await page.content(), encoding="utf-8")
        meta["html_dump"] = str(html_path)
    except Exception as e:
        meta["html_dump_error"] = str(e)

    try:
        meta["selector_counts"] = await _collect_diag_counts(page)
    except Exception as e:
        meta["selector_counts_error"] = str(e)

    try:
        meta["block_signals"] = await _detect_block_signals(page)
    except Exception as e:
        meta["block_signals_error"] = str(e)

    if traces_started:
        try:
            trace_path = run_dir / "trace.zip"
            await context.tracing.stop(path=str(trace_path))
            meta["trace"] = str(trace_path)
        except Exception as e:
            meta["trace_error"] = str(e)

    try:
        await context.close()
    except Exception as e:
        meta["context_close_error"] = str(e)

    # Video files are finalized on context close.
    try:
        videos = sorted(str(p) for p in run_dir.glob("*.webm"))
        if videos:
            meta["video_files"] = videos
    except Exception as e:
        meta["video_scan_error"] = str(e)

    (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


async def _extract_once(
    context,
    page,
    match_url: str,
    market: str,
    market_type: str,
    timeout_ms: int,
    selector_timeout_ms: int,
    settle_ms: int,
    top_lines: int,
    prefer_lines: Iterable[float] | None,
    fixed_lines: Iterable[float] | None,
    adjacent_delta: float,
    debug: bool,
) -> dict:
    expected_outcomes = 3 if market_type == "1X2" else 2
    active_tab = await _goto_market(page, match_url, market_type, timeout_ms, settle_ms)
    await _wait_for_market_rows(page, market_type=market_type, timeout_ms=selector_timeout_ms)
    await page.wait_for_timeout(settle_ms)

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

        return result

    # OU / AH: parse collapsed lines and expand each line to parse bookmaker rows.
    collapsed_selector = "div[data-testid='over-under-collapsed-row']"
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
    if adjacent_delta and adjacent_delta > 0:
        expanded_set = set(selected_set)
        for line in list(selected_set):
            if line is None:
                continue
            expanded_set.add(round_line(line - float(adjacent_delta)))
            expanded_set.add(round_line(line + float(adjacent_delta)))
        selected_set = {x for x in expanded_set if x is not None}

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

    return result


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
    adjacent_delta: float = 0.0,
    debug: bool = False,
    selector_timeout_ms: int = 60000,
    max_retries: int = 2,
    capture_artifacts_on_failure: bool = True,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
) -> dict:
    market_type = normalize_market_type(market)
    attempts = max(1, int(max_retries) + 1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            await ensure_storage_state(browser, _canonical_market_url(match_url, market_type), storage_state_path)

            last_err: Exception | None = None
            for attempt in range(1, attempts + 1):
                run_dir = _artifact_run_dir(artifacts_dir, market_type, attempt)
                context = await browser.new_context(
                    storage_state=str(storage_state_path),
                    record_video_dir=str(run_dir),
                )
                await context.tracing.start(screenshots=True, snapshots=True, sources=True)
                traces_started = True
                page = await context.new_page()

                try:
                    result = await _extract_once(
                        context=context,
                        page=page,
                        match_url=match_url,
                        market=market,
                        market_type=market_type,
                        timeout_ms=timeout_ms,
                        selector_timeout_ms=selector_timeout_ms,
                        settle_ms=settle_ms,
                        top_lines=top_lines,
                        prefer_lines=prefer_lines,
                        fixed_lines=fixed_lines,
                        adjacent_delta=adjacent_delta,
                        debug=debug,
                    )
                    try:
                        if traces_started:
                            await context.tracing.stop()
                    except Exception:
                        pass
                    await context.close()
                    return result

                except Exception as e:
                    last_err = e
                    should_retry = attempt < attempts

                    if capture_artifacts_on_failure:
                        await _capture_failure_artifacts(
                            context=context,
                            page=page,
                            run_dir=run_dir,
                            reason=("retryable_failure" if should_retry else "final_failure"),
                            err=e,
                            match_url=match_url,
                            market_type=market_type,
                            traces_started=traces_started,
                        )
                    else:
                        try:
                            if traces_started:
                                await context.tracing.stop()
                        except Exception:
                            pass
                        await context.close()

                    if should_retry:
                        await asyncio.sleep(min(6.0, 1.25 * attempt))
                        continue
                    raise

            if last_err:
                raise last_err
            raise RuntimeError("odds extraction failed without explicit exception")
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
    parser.add_argument("--selector-timeout-ms", type=int, default=60000, help="Market-row selector timeout in milliseconds")
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
    parser.add_argument("--adjacent-delta", type=float, default=0.0, help="For OU/AH, include adjacent +/-delta lines around selected top lines")
    parser.add_argument("--max-retries", type=int, default=2, help="Retries after first attempt on transient failures")
    parser.add_argument(
        "--artifacts-dir",
        default=str(DEFAULT_ARTIFACTS_DIR),
        help="Directory for failure artifacts (trace/video/screenshot/html/meta)",
    )
    parser.add_argument(
        "--no-capture-artifacts-on-failure",
        action="store_true",
        help="Disable failure artifact capture",
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
        selector_timeout_ms=args.selector_timeout_ms,
        settle_ms=args.settle_ms,
        top_lines=args.top_lines,
        prefer_lines=parse_line_csv(args.prefer_lines),
        fixed_lines=parse_line_csv(args.fixed_lines),
        adjacent_delta=args.adjacent_delta,
        debug=args.debug,
        max_retries=args.max_retries,
        capture_artifacts_on_failure=not args.no_capture_artifacts_on_failure,
        artifacts_dir=Path(args.artifacts_dir),
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
