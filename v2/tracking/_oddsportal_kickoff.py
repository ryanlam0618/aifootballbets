from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright


@dataclass
class KickoffInfo:
    kickoff_utc: datetime | None
    source: str
    raw: str | int | None = None


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
    if num < 946684800 or num > 4102444800:
        return None
    return datetime.fromtimestamp(num, tz=timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def _rank_candidates(now: datetime, candidates: list[tuple[datetime, str, str | int | None]]) -> tuple[datetime, str, str | int | None] | None:
    if not candidates:
        return None

    # Keep dates within a sensible window around now (past 2d, future 365d)
    bounded = [c for c in candidates if -172800 <= (c[0] - now).total_seconds() <= 365 * 86400]
    if not bounded:
        bounded = candidates

    def rank(c: tuple[datetime, str, str | int | None]) -> tuple[int, float]:
        dt, src, _ = c
        src_l = src.lower()
        src_score = 0 if src_l.startswith("ldjson") else (1 if src_l.startswith("next_data") else 2)
        delta = (dt - now).total_seconds()
        future_penalty = 0 if delta >= -300 else 1
        return (src_score + future_penalty * 10, abs(delta))

    return sorted(bounded, key=rank)[0]


async def read_kickoff_from_oddsportal_page(match_url: str, storage_state: Path, timeout_ms: int = 120000) -> KickoffInfo:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            if storage_state.exists() and storage_state.stat().st_size > 0:
                context = await browser.new_context(storage_state=str(storage_state))
            else:
                context = await browser.new_context()
            page = await context.new_page()
            await page.goto(match_url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(2000)

            data = await page.evaluate(
                """
                () => {
                  const out = [];
                  const add = (v, src) => { if (v !== null && v !== undefined && v !== '') out.push({value: v, source: src}); };
                  const walk = (obj, src) => {
                    if (!obj || typeof obj !== 'object') return;
                    if (Array.isArray(obj)) { for (const x of obj) walk(x, src); return; }
                    for (const [k, v] of Object.entries(obj)) {
                      const key = String(k || '').toLowerCase();
                      if (['startdate','starttime','kickoff','kickofftime','date'].includes(key)) add(v, src + ':' + k);
                      if (typeof v === 'object' && v !== null) walk(v, src + '.' + k);
                    }
                  };

                  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                    try { const j = JSON.parse(s.textContent || '{}'); walk(j, 'ldjson'); } catch (e) {}
                  }

                  const next = document.querySelector('script#__NEXT_DATA__');
                  if (next) {
                    try { const j = JSON.parse(next.textContent || '{}'); walk(j, 'next_data'); } catch (e) {}
                  }

                  const dt = document.querySelector('time[datetime]')?.getAttribute('datetime');
                  if (dt) add(dt, 'time_datetime');

                  return out;
                }
                """
            )
            await context.close()
        finally:
            await browser.close()

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

    best = _rank_candidates(now, candidates)
    if not best:
        return KickoffInfo(None, "unparsed", None)
    return KickoffInfo(best[0], best[1], best[2])
