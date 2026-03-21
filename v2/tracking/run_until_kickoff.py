from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

from v2.tracking.oddsportal_one_match import normalize_market_type, parse_line_csv
from v2.tracking.odds_tracker import (
    Target,
    append_jsonl,
    ensure_db,
    load_schema,
    sample_one,
    save_snapshot,
    upsert_match,
)


@dataclass
class KickoffInfo:
    kickoff_utc: datetime | None
    source: str
    raw: str | int | None = None


@dataclass
class PinchTabVerifier:
    base_url: str
    token: str
    timeout_sec: float = 6.0

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = self.base_url.rstrip("/") + path
        data = None
        headers = {
            "Authorization": f"Bearer {self.token}",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url=url, data=data, method=method.upper(), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
            return json.loads(raw) if raw else {}

    def navigate(self, url: str) -> Any:
        # Prefer JSON POST and keep a fallback for query-string style APIs.
        try:
            return self._request("POST", "/navigate", {"url": url})
        except Exception:
            qs = urllib.parse.urlencode({"url": url})
            return self._request("GET", f"/navigate?{qs}")

    def tabs(self) -> Any:
        return self._request("GET", "/tabs")


@dataclass
class VerifyResult:
    verified: bool
    verify_error: str | None
    pinchtab_title: str | None
    pinchtab_tab_id: str | None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def to_shanghai(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(ZoneInfo("Asia/Shanghai"))


def _parse_iso_like(value: str) -> datetime | None:
    s = (value or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_epoch(value: int | float | str) -> datetime | None:
    try:
        num = float(value)
    except Exception:
        return None
    if num > 1e12:
        num = num / 1000.0
    if num < 946684800 or num > 4102444800:  # [2000, 2100]
        return None
    return datetime.fromtimestamp(num, tz=timezone.utc)


def _normalize_url_for_compare(url: str) -> tuple[str, str, str, str, str]:
    u = urllib.parse.urlsplit((url or "").strip())
    path = u.path.rstrip("/") or "/"
    query = u.query
    fragment = u.fragment
    return (u.scheme.lower(), u.netloc.lower(), path, query, fragment)


def _url_matches(expected: str, got: str) -> bool:
    if not expected or not got:
        return False

    e = _normalize_url_for_compare(expected)
    g = _normalize_url_for_compare(got)

    # Exact canonical match.
    if e == g:
        return True

    # Accept match even if one side does not include fragment.
    if e[:4] == g[:4] and (not e[4] or not g[4]):
        return True

    return False


def _expected_title_keywords(market_type: str) -> list[str]:
    mt = normalize_market_type(market_type)
    if mt == "OU":
        return ["oddsportal", "over/under", "totals"]
    if mt == "AH":
        return ["oddsportal", "asian handicap", "handicap"]
    return ["oddsportal", "1x2"]


def _extract_title(data: Any) -> str | None:
    if isinstance(data, dict):
        for key in ("title", "pageTitle", "name"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        for v in data.values():
            t = _extract_title(v)
            if t:
                return t
    elif isinstance(data, list):
        for item in data:
            t = _extract_title(item)
            if t:
                return t
    return None


def _extract_tab_id(data: Any) -> str | None:
    if isinstance(data, dict):
        for key in ("tabId", "tab_id", "id", "targetId", "target_id"):
            v = data.get(key)
            if v is not None and str(v).strip():
                return str(v)
        for v in data.values():
            tid = _extract_tab_id(v)
            if tid:
                return tid
    elif isinstance(data, list):
        for item in data:
            tid = _extract_tab_id(item)
            if tid:
                return tid
    return None


def _flatten_tabs(data: Any) -> list[dict[str, Any]]:
    tabs: list[dict[str, Any]] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                tabs.append(item)
    elif isinstance(data, dict):
        for key in ("tabs", "items", "data"):
            v = data.get(key)
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        tabs.append(item)

        if not tabs and ("url" in data or "tabId" in data or "id" in data):
            tabs.append(data)

    return tabs


def _pick_active_tab(tabs_data: Any, expected_url: str) -> dict[str, Any] | None:
    tabs = _flatten_tabs(tabs_data)
    if not tabs:
        return None

    # Prefer an explicitly active tab.
    for tab in tabs:
        if tab.get("active") is True or tab.get("isActive") is True:
            return tab

    # Fall back to URL match.
    for tab in tabs:
        tab_url = str(tab.get("url") or "")
        if _url_matches(expected_url, tab_url):
            return tab

    return tabs[0]


def _verify_with_pinchtab(verifier: PinchTabVerifier, url: str, market_type: str) -> VerifyResult:
    try:
        nav_data = verifier.navigate(url)
        tabs_data = verifier.tabs()
    except urllib.error.HTTPError as e:
        return VerifyResult(False, f"pinchtab_http_{e.code}", None, None)
    except urllib.error.URLError as e:
        return VerifyResult(False, f"pinchtab_network:{e.reason}", None, None)
    except Exception as e:
        return VerifyResult(False, f"pinchtab_error:{e}", None, None)

    title = _extract_title(nav_data)
    tab_id = _extract_tab_id(nav_data)

    active_tab = _pick_active_tab(tabs_data, url)
    active_url = str((active_tab or {}).get("url") or "")
    if active_tab and not tab_id:
        tab_id = _extract_tab_id(active_tab)

    keywords = _expected_title_keywords(market_type)
    title_l = (title or "").lower()
    title_ok = any(k in title_l for k in keywords)
    url_ok = _url_matches(url, active_url)

    if title_ok and url_ok:
        return VerifyResult(True, None, title, tab_id)

    parts = []
    if not title_ok:
        parts.append("title_mismatch")
    if not url_ok:
        parts.append("active_tab_url_mismatch")
    err = ",".join(parts) if parts else "unknown_verify_failure"
    return VerifyResult(False, err, title, tab_id)


async def read_kickoff_from_page(match_url: str, storage_state: Path, timeout_ms: int = 120000) -> KickoffInfo:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        try:
            if storage_state.exists() and storage_state.stat().st_size > 0:
                context = await browser.new_context(storage_state=str(storage_state))
            else:
                context = await browser.new_context()
            page = await context.new_page()
            await page.goto(match_url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(2500)

            data = await page.evaluate(
                """
                () => {
                  const out = [];
                  const add = (v, src) => { if (v !== null && v !== undefined && v !== '') out.push({value: v, source: src}); };
                  const walk = (obj, src) => {
                    if (!obj || typeof obj !== 'object') return;
                    if (Array.isArray(obj)) {
                      for (const x of obj) walk(x, src);
                      return;
                    }
                    for (const [k, v] of Object.entries(obj)) {
                      const key = String(k || '').toLowerCase();
                      if (['startdate','starttime','kickoff','kickofftime','date'].includes(key)) {
                        add(v, src + ':' + k);
                      }
                      if (typeof v === 'object' && v !== null) walk(v, src + '.' + k);
                    }
                  };

                  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                    try {
                      const j = JSON.parse(s.textContent || '{}');
                      walk(j, 'ldjson');
                    } catch (e) {}
                  }

                  const next = document.querySelector('script#__NEXT_DATA__');
                  if (next) {
                    try {
                      const j = JSON.parse(next.textContent || '{}');
                      walk(j, 'next_data');
                    } catch (e) {}
                  }

                  const dt = document.querySelector('time[datetime]')?.getAttribute('datetime');
                  if (dt) add(dt, 'time_datetime');

                  const metaDate = document.querySelector('meta[property="article:published_time"]')?.getAttribute('content');
                  if (metaDate) add(metaDate, 'meta_published_time');

                  return out;
                }
                """
            )
            await context.close()
        finally:
            await browser.close()

    # Rank candidates: prefer ISO string from ldjson/next_data and nearest future.
    now = utc_now()
    candidates: list[tuple[datetime, str, str | int | None]] = []
    for item in data or []:
        raw = item.get("value")
        src = str(item.get("source") or "unknown")
        dt = None
        if isinstance(raw, str):
            dt = _parse_iso_like(raw)
            if dt is None and raw.isdigit():
                dt = _parse_epoch(int(raw))
        elif isinstance(raw, (int, float)):
            dt = _parse_epoch(raw)
        if dt is not None:
            candidates.append((dt, src, raw))

    if not candidates:
        return KickoffInfo(None, "unparsed", None)

    # Keep dates within a sensible window around now (past 2d, future 14d)
    bounded = [c for c in candidates if -172800 <= (c[0] - now).total_seconds() <= 1209600]
    if not bounded:
        bounded = candidates

    def rank(c: tuple[datetime, str, str | int | None]) -> tuple[int, float]:
        dt, src, _ = c
        src_l = src.lower()
        src_score = 0 if src_l.startswith("ldjson") else (1 if src_l.startswith("next_data") else 2)
        # prefer future, then nearest absolute distance
        delta = (dt - now).total_seconds()
        future_penalty = 0 if delta >= -300 else 1
        return (src_score + future_penalty * 10, abs(delta))

    best = sorted(bounded, key=rank)[0]
    return KickoffInfo(kickoff_utc=best[0], source=best[1], raw=best[2])


async def run(args: argparse.Namespace) -> int:
    targets = [
        Target(match_url=args.base_url, market="1X2", label="brentford-wolves-1x2"),
        Target(match_url=args.base_url, market="OU", label="brentford-wolves-ou"),
        Target(match_url=args.base_url, market="AH", label="brentford-wolves-ah"),
    ]

    sqlite_path = Path(args.sqlite)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path = Path(args.jsonl)
    storage_state = Path(args.storage_state)

    pinchtab_token = (args.pinchtab_token or os.getenv("PINCHTAB_TOKEN") or "").strip()
    pinchtab_verifier = PinchTabVerifier(
        base_url=args.pinchtab_base_url,
        token=pinchtab_token,
        timeout_sec=max(1.0, float(args.pinchtab_timeout_ms) / 1000.0),
    )

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_db(conn, load_schema(Path(args.schema)))
        target_ids = {t: upsert_match(conn, t) for t in targets}

        kickoff = await read_kickoff_from_page(args.base_url, storage_state=storage_state, timeout_ms=args.timeout_ms)
        now = utc_now()
        kickoff_hkt = to_shanghai(kickoff.kickoff_utc)
        now_hkt = to_shanghai(now)

        print(f"[plan] now_utc={iso(now)} now_asia_shanghai={iso(now_hkt)}")
        if kickoff.kickoff_utc:
            print(
                f"[plan] kickoff_utc={iso(kickoff.kickoff_utc)} kickoff_asia_shanghai={iso(kickoff_hkt)} "
                f"source={kickoff.source} raw={kickoff.raw}"
            )
        else:
            print("[plan] kickoff could not be parsed reliably; fallback max cycles will be used")

        if args.pinchtab_verify and not pinchtab_token:
            print("[warn] --pinchtab-verify enabled but no token set (use --pinchtab-token or PINCHTAB_TOKEN)")

        prefer_ou = parse_line_csv(args.prefer_lines_ou)
        prefer_ah = parse_line_csv(args.prefer_lines_ah)
        pinned_lines: dict[tuple[str, str], list[float]] = {}

        cycle = 0
        while True:
            now = utc_now()
            if kickoff.kickoff_utc and now >= kickoff.kickoff_utc:
                print(
                    f"[stop] current time {iso(now)} >= kickoff {iso(kickoff.kickoff_utc)}; stopping tracker"
                )
                break

            if args.max_cycles and cycle >= args.max_cycles:
                print(f"[stop] reached --max-cycles={args.max_cycles}; stopping tracker")
                break

            if (not kickoff.kickoff_utc) and cycle >= args.max_cycles_no_kickoff:
                print(
                    f"[stop] kickoff unparsed and reached --max-cycles-no-kickoff={args.max_cycles_no_kickoff}; "
                    "kickoff parsing needs adjustment"
                )
                break

            cycle += 1
            cycle_started = time.time()
            print(f"[{iso(utc_now())}] cycle {cycle}: sampling {len(targets)} markets")

            for idx, t in enumerate(targets, start=1):
                mt = normalize_market_type(t.market)
                key = (t.match_url, mt)
                preferred = prefer_ou if mt == "OU" else (prefer_ah if mt == "AH" else [])
                fixed = pinned_lines.get(key) if mt in {"OU", "AH"} else None

                payload, success, err = await sample_one(
                    target=t,
                    storage_state=storage_state,
                    headless=False,
                    timeout_ms=args.timeout_ms,
                    settle_ms=args.settle_ms,
                    top_lines=args.top_lines,
                    prefer_lines=preferred,
                    fixed_lines=fixed,
                )

                selected_lines = payload.get("selected_lines") or []
                if mt in {"OU", "AH"} and success and key not in pinned_lines and selected_lines:
                    pinned_lines[key] = list(selected_lines)

                payload["kickoff_utc"] = iso(kickoff.kickoff_utc) if kickoff.kickoff_utc else None
                payload["kickoff_asia_shanghai"] = iso(kickoff_hkt) if kickoff_hkt else None
                payload["kickoff_source"] = kickoff.source

                verify = VerifyResult(
                    verified=False,
                    verify_error=("disabled" if not args.pinchtab_verify else "skipped_snapshot_failed"),
                    pinchtab_title=None,
                    pinchtab_tab_id=None,
                )
                if args.pinchtab_verify and success:
                    if not pinchtab_token:
                        verify = VerifyResult(
                            verified=False,
                            verify_error="pinchtab_token_missing",
                            pinchtab_title=None,
                            pinchtab_tab_id=None,
                        )
                    else:
                        verify = await asyncio.to_thread(
                            _verify_with_pinchtab,
                            pinchtab_verifier,
                            str(payload.get("match_url") or t.match_url),
                            mt,
                        )

                snapshot_id = save_snapshot(conn, target_ids[t], payload, success=success, error=err)
                append_jsonl(
                    jsonl_path,
                    {
                        "cycle": cycle,
                        "snapshot_id": snapshot_id,
                        "success": success,
                        "error": err,
                        "market": mt,
                        "verified": verify.verified,
                        "verify_error": verify.verify_error,
                        "pinchtab_title": verify.pinchtab_title,
                        "pinchtab_tab_id": verify.pinchtab_tab_id,
                        **payload,
                    },
                )

                qn = len(payload.get("odds") or [])
                line_note = f" selected_lines={selected_lines}" if mt in {"OU", "AH"} else ""
                verify_note = (
                    f" verified={verify.verified}"
                    if args.pinchtab_verify
                    else ""
                )
                print(
                    f"  - [{idx}/{len(targets)}] snapshot_id={snapshot_id} market={mt} success={success} "
                    f"quotes={qn}{line_note}{verify_note}"
                )

                if idx < len(targets):
                    await asyncio.sleep(max(0.0, float(args.between_market_delay_sec)))

            elapsed = time.time() - cycle_started
            sleep_s = max(0, int(args.sample_every_min * 60 - elapsed))
            if sleep_s > 0:
                stop_at = utc_now().timestamp() + sleep_s
                print(
                    f"[{iso(utc_now())}] cycle {cycle} complete; sleeping {sleep_s}s until "
                    f"{iso(datetime.fromtimestamp(stop_at, tz=timezone.utc))}"
                )
                await asyncio.sleep(sleep_s)

        print(f"[done] cycles_completed={cycle} sqlite={sqlite_path} jsonl={jsonl_path}")
        return 0
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run OddsPortal tracking every 10m until kickoff")
    p.add_argument(
        "--base-url",
        default="https://www.oddsportal.com/football/england/premier-league/brentford-wolves-0jR7cwU6/",
        help="Match base URL (without market fragment needed)",
    )
    p.add_argument("--sample-every-min", type=int, default=10)
    p.add_argument("--between-market-delay-sec", type=float, default=8.0)
    p.add_argument("--top-lines", type=int, default=2)
    p.add_argument("--prefer-lines-ou", default="2.5,2.75")
    p.add_argument("--prefer-lines-ah", default="-0.25,0.0")
    p.add_argument("--timeout-ms", type=int, default=120000)
    p.add_argument("--settle-ms", type=int, default=2500)

    p.add_argument("--sqlite", default="data/v2/tracking/brentford_wolves_until_kickoff.sqlite")
    p.add_argument("--jsonl", default="data/v2/tracking/brentford_wolves_until_kickoff.jsonl")
    p.add_argument("--schema", default="v2/tracking/schema_odds_tracker_v2.sql")
    p.add_argument("--storage-state", default="/tmp/oddsportal_storage.json")

    p.add_argument(
        "--max-cycles-no-kickoff",
        type=int,
        default=6,
        help="Fallback hard stop when kickoff cannot be parsed",
    )
    p.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="Optional hard stop for testing/demo (0 = no explicit cap)",
    )
    p.add_argument(
        "--pinchtab-verify",
        action="store_true",
        help="Enable lightweight PinchTab verification for each successful snapshot.",
    )
    p.add_argument(
        "--pinchtab-base-url",
        default="http://pinchtabd:9867",
        help="PinchTab API base URL.",
    )
    p.add_argument(
        "--pinchtab-token",
        default="",
        help="PinchTab Bearer token (prefer setting PINCHTAB_TOKEN env var).",
    )
    p.add_argument(
        "--pinchtab-timeout-ms",
        type=int,
        default=6000,
        help="Per-request timeout for PinchTab navigate/tabs checks.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
