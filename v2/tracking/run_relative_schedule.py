#!/usr/bin/env python3
from __future__ import annotations

"""Track OddsPortal odds snapshots on a fixed relative-to-kickoff schedule.

Design goal (Kris):
- kickoff time is sourced from SofaScore
- sample at:
  * T-24h to T-60m: every 60m
  * last hour: every 5m (T-55m..T-5m)
- markets: 1X2 + OU + AH
- as many bookmakers as possible

Notes:
- This script does NOT attempt to backfill historical intra-day odds for past kickoffs.
  It is meant for upcoming matches.
- Writes to the existing odds_tracker sqlite schema, and also emits a JSONL log that includes
  kickoff metadata (event_id, kickoff_utc, minutes_to_kickoff) for easy CSV export.
"""

import argparse
import asyncio
import json
import math
import os
import re
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from v2.tracking.odds_tracker import (
    Target,
    append_jsonl,
    ensure_db,
    load_schema,
    save_snapshot,
    upsert_match,
)
from v2.tracking.oddsportal_one_match import extract_odds, normalize_market_type


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def _run_node_fetch(url: str, timeout_sec: int = 20) -> dict[str, Any]:
    # Reuse the existing fetch wrapper so we don't reinvent headers/timeouts.
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "sofascore_fetch.js"
    cmd = ["node", str(script), "--url", url, "--timeout-ms", str(int(max(1000, timeout_sec * 1000)))]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=max(10, timeout_sec + 10))
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"fetch failed: {url}")
    return json.loads(proc.stdout) if proc.stdout else {}


def _slug_tokens(s: str) -> list[str]:
    s = (s or "").strip().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    toks = [t for t in s.split() if t]
    return toks


def _oddsportal_url_tokens(match_url: str) -> tuple[list[str], str, str]:
    """Return (tokens, competition_slug, country_slug)."""
    # Example:
    # /football/england/premier-league/arsenal-manchester-city-OUNtGjHL/
    parts = [p for p in (match_url or "").split("/") if p]
    country = ""
    competition = ""
    if len(parts) >= 4 and parts[0].endswith(":") is False and parts[0] in {"https:", "http:"}:
        # crude split for absolute URLs
        pass

    # safer parse
    try:
        from urllib.parse import urlsplit

        u = urlsplit(match_url)
        segs = [s for s in (u.path or "").split("/") if s]
        if len(segs) >= 4 and segs[0] == "football":
            country = segs[1]
            competition = segs[2]
            slug = segs[3]
        else:
            slug = segs[-1] if segs else ""
    except Exception:
        slug = match_url.rsplit("/", 1)[-1]

    slug = slug.strip().strip("/")
    toks = _slug_tokens(slug)

    # Drop trailing mixed-alnum id token (OddsPortal match id).
    # Heuristic: token length >= 5 and contains both letters and digits.
    if toks:
        last = toks[-1]
        if len(last) >= 5 and re.search(r"[a-z]", last) and re.search(r"\d", last):
            toks = toks[:-1]

    return toks, competition.lower(), country.lower()


def _find_subseq(hay: list[str], needle: list[str]) -> int | None:
    """Return start index if needle appears contiguously in hay."""
    if not needle:
        return None
    n = len(needle)
    for i in range(0, max(0, len(hay) - n) + 1):
        if hay[i : i + n] == needle:
            return i
    return None


@dataclass
class SofaEvent:
    event_id: int
    kickoff_utc: datetime
    home: str
    away: str
    tournament: str
    tournament_slug: str


def _score_event(url_tokens: list[str], ev_home_toks: list[str], ev_away_toks: list[str]) -> float:
    """Score how well a SofaScore event matches an OddsPortal URL token sequence."""
    # Prefer exact contiguous matches for both teams in correct order.
    h_pos = _find_subseq(url_tokens, ev_home_toks)
    a_pos = _find_subseq(url_tokens, ev_away_toks)
    if h_pos is None or a_pos is None:
        return 0.0
    if h_pos >= a_pos:
        return 0.0

    # Base score: longer matches are better.
    score = 10.0 + 2.0 * (len(ev_home_toks) + len(ev_away_toks))

    # Penalize large gaps (means boundary ambiguity)
    gap = a_pos - (h_pos + len(ev_home_toks))
    if gap > 0:
        score -= min(3.0, 0.5 * gap)

    return max(0.0, score)


def lookup_sofascore_event_for_oddsportal_url(
    match_url: str,
    start_date: date,
    lookahead_days: int,
    cache_path: Path,
    refresh_if_older_sec: int = 6 * 3600,
) -> SofaEvent | None:
    """Best-effort mapping: OddsPortal match_url -> SofaScore event (id + kickoff).

    Strategy:
    - Fetch SofaScore scheduled-events for [start_date, start_date+lookahead]
    - Score each event against match_url slug tokens
    """

    url_tokens, comp_slug, _country = _oddsportal_url_tokens(match_url)
    if not url_tokens:
        return None

    # Load/refresh cache.
    events: list[dict[str, Any]] = []
    now = time.time()
    if cache_path.exists() and cache_path.stat().st_size > 0:
        age = now - cache_path.stat().st_mtime
        if age < refresh_if_older_sec:
            try:
                events = json.loads(cache_path.read_text(encoding="utf-8")).get("events", [])
            except Exception:
                events = []

    if not events:
        all_events: list[dict[str, Any]] = []
        for i in range(max(1, int(lookahead_days) + 1)):
            d = start_date + timedelta(days=i - 0)  # include start_date
            url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{d.isoformat()}"
            data = _run_node_fetch(url, timeout_sec=25)
            all_events.extend(data.get("events", []) or [])
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"generated_at_utc": iso(utc_now()), "events": all_events}, ensure_ascii=False), encoding="utf-8")
        events = all_events

    best: tuple[float, SofaEvent] | None = None

    for e in events:
        try:
            ev_id = int(e.get("id"))
            ts = int(e.get("startTimestamp"))
            kickoff = datetime.fromtimestamp(ts, tz=timezone.utc)
            home = str((e.get("homeTeam") or {}).get("name") or "")
            away = str((e.get("awayTeam") or {}).get("name") or "")
            tour = str((e.get("tournament") or {}).get("name") or "")
            tour_slug = str((e.get("tournament") or {}).get("slug") or "")
        except Exception:
            continue

        # Quick comp hint (soft): if we have comp_slug and tour_slug overlaps, boost.
        comp_boost = 0.0
        if comp_slug and tour_slug:
            if comp_slug == tour_slug or comp_slug in tour_slug or tour_slug in comp_slug:
                comp_boost = 3.0

        h_toks = _slug_tokens(home)
        a_toks = _slug_tokens(away)
        if not h_toks or not a_toks:
            continue

        score = _score_event(url_tokens, h_toks, a_toks) + comp_boost
        if score <= 0:
            continue

        ev = SofaEvent(
            event_id=ev_id,
            kickoff_utc=kickoff,
            home=home,
            away=away,
            tournament=tour,
            tournament_slug=tour_slug,
        )
        if best is None or score > best[0]:
            best = (score, ev)

    return best[1] if best else None


def build_minutes_schedule() -> list[int]:
    # Hourly from -1440 to -60 (inclusive)
    hourly = list(range(-1440, -59, 60))
    # Every 5 minutes in last hour excluding -60 (already included) and excluding 0
    last_hour = list(range(-55, 0, 5))
    return hourly + last_hour


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"generated_at_utc": iso(utc_now()), "matches": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"generated_at_utc": iso(utc_now()), "matches": {}}


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at_utc"] = iso(utc_now())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


async def _sample_market(
    match_url: str,
    market: str,
    storage_state: Path,
    headless: bool,
    timeout_ms: int,
    settle_ms: int,
    top_lines: int,
    adjacent_delta: float,
    prefer_lines: list[float] | None,
    fixed_lines: list[float] | None,
) -> dict:
    payload = await extract_odds(
        match_url=match_url,
        market=market,
        storage_state_path=storage_state,
        headless=headless,
        timeout_ms=timeout_ms,
        settle_ms=settle_ms,
        top_lines=top_lines,
        prefer_lines=prefer_lines,
        fixed_lines=fixed_lines,
        adjacent_delta=adjacent_delta,
    )
    # ensure market_type in payload
    payload.setdefault("market_type", normalize_market_type(market))
    return payload


async def run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[2]

    targets_data = json.loads(Path(args.targets_json).read_text(encoding="utf-8"))
    if not isinstance(targets_data, list):
        raise SystemExit("--targets-json must be a JSON array")
    match_urls = [str(x.get("match_url") or "").strip() for x in targets_data if isinstance(x, dict) and x.get("match_url")]
    match_urls = [u.split("#", 1)[0].rstrip("/") + "/" for u in match_urls]
    match_urls = sorted(set(match_urls))
    if not match_urls:
        raise SystemExit("No match_url in targets-json")

    minutes_schedule = build_minutes_schedule()

    out_sqlite = Path(args.sqlite)
    out_sqlite.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path = Path(args.jsonl) if args.jsonl else None

    conn = sqlite3.connect(str(out_sqlite))
    conn.row_factory = sqlite3.Row
    try:
        ensure_db(conn, load_schema(repo_root / args.schema))

        state_path = Path(args.state)
        state = load_state(state_path)

        # Cache scheduled-events for mapping kickoff.
        cache_path = Path(args.sofascore_cache)

        # Prepare matches: resolve sofascore event once.
        matches: dict[str, dict[str, Any]] = state.setdefault("matches", {})

        start_d = date.fromisoformat(args.start_date) if args.start_date else utc_now().date()
        for u in match_urls:
            m = matches.setdefault(u, {})
            if not m.get("event_id") or not m.get("kickoff_utc"):
                ev = lookup_sofascore_event_for_oddsportal_url(
                    match_url=u,
                    start_date=start_d,
                    lookahead_days=args.lookahead_days,
                    cache_path=cache_path,
                )
                if ev:
                    m.update(
                        {
                            "event_id": ev.event_id,
                            "kickoff_utc": iso(ev.kickoff_utc),
                            "home": ev.home,
                            "away": ev.away,
                            "tournament": ev.tournament,
                            "tournament_slug": ev.tournament_slug,
                        }
                    )
                else:
                    m.setdefault("event_id", None)
                    m.setdefault("kickoff_utc", "")

            m.setdefault("done_minutes", [])
            m.setdefault("missed_minutes", [])

        save_state(state_path, state)

        storage_state = Path(args.storage_state)

        # Build targets for sqlite.
        markets = ["1X2", "OU", "AH"]
        target_ids: dict[tuple[str, str], int] = {}
        for u in match_urls:
            for market in markets:
                t = Target(match_url=u, market=market, label=None)
                target_ids[(u, market)] = upsert_match(conn, t)

        pinned_lines: dict[tuple[str, str], list[float]] = {}

        def _parse_iso(s: str) -> datetime | None:
            if not s:
                return None
            ss = s.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(ss).astimezone(timezone.utc)
            except Exception:
                return None

        # Main schedule loop
        while True:
            now = utc_now()

            due: list[tuple[datetime, str, int]] = []  # (scheduled_ts, match_url, minutes_to_kickoff)
            active_matches = 0

            for u in match_urls:
                m = matches.get(u) or {}
                kickoff = _parse_iso(str(m.get("kickoff_utc") or ""))
                if not kickoff:
                    continue
                if now >= kickoff:
                    continue
                active_matches += 1

                done = set(int(x) for x in (m.get("done_minutes") or []) if isinstance(x, (int, float, str)))
                missed = set(int(x) for x in (m.get("missed_minutes") or []) if isinstance(x, (int, float, str)))

                for mt in minutes_schedule:
                    if mt in done or mt in missed:
                        continue
                    ts = kickoff + timedelta(minutes=int(mt))
                    # consider due if in the future; we will sleep until the soonest
                    if ts >= now:
                        due.append((ts, u, int(mt)))
                    else:
                        # schedule point already passed; mark missed if too late
                        if (now - ts).total_seconds() > float(args.miss_grace_sec):
                            m.setdefault("missed_minutes", []).append(int(mt))

            if active_matches == 0:
                # Nothing to track.
                save_state(state_path, state)
                return 0

            if not due:
                save_state(state_path, state)
                # All remaining points are missed or no kickoff; stop.
                return 0

            due.sort(key=lambda x: x[0])
            next_ts = due[0][0]
            sleep_sec = max(0.0, (next_ts - now).total_seconds())
            if sleep_sec > 0:
                time.sleep(min(sleep_sec, 60.0))
                continue

            # Process all points within a small window.
            window = float(args.due_window_sec)
            batch = [(ts, u, mt) for (ts, u, mt) in due if abs((ts - next_ts).total_seconds()) <= window]

            for ts, u, mt in batch:
                m = matches.get(u) or {}
                kickoff = _parse_iso(str(m.get("kickoff_utc") or ""))
                if not kickoff:
                    continue

                # One scheduled timestamp: sample all markets.
                for market in markets:
                    key = (u, normalize_market_type(market))
                    fixed = pinned_lines.get(key)

                    prefer = None
                    if market == "OU" and args.prefer_lines_ou:
                        prefer = [float(x) for x in args.prefer_lines_ou.split(",") if x.strip()]
                    if market == "AH" and args.prefer_lines_ah:
                        prefer = [float(x) for x in args.prefer_lines_ah.split(",") if x.strip()]

                    payload: dict
                    success = False
                    err: str | None = None
                    try:
                        payload = await _sample_market(
                            match_url=u,
                            market=market,
                            storage_state=storage_state,
                            headless=args.headless,
                            timeout_ms=args.timeout_ms,
                            settle_ms=args.settle_ms,
                            top_lines=args.top_lines,
                            adjacent_delta=args.adjacent_delta,
                            prefer_lines=prefer,
                            fixed_lines=fixed,
                        )
                        success = len(payload.get("odds") or []) > 0
                        err = None if success else "no_quotes_extracted"

                        # pin lines for OU/AH after first success, so subsequent snapshots are stable.
                        if args.pin_lines_first_snapshot and success and key not in pinned_lines:
                            sel = payload.get("selected_lines")
                            if isinstance(sel, list) and sel:
                                pinned_lines[key] = [float(x) for x in sel if x is not None]

                    except Exception as e:
                        payload = {
                            "match_url": u,
                            "market": market,
                            "market_type": normalize_market_type(market),
                            "snapshot_ts_utc": iso(utc_now()),
                            "row_count_seen": 0,
                            "odds": [],
                            "selected_lines": fixed or [],
                            "line_frequency": {},
                        }
                        success = False
                        err = str(e)

                    match_id = target_ids[(u, market)]
                    snapshot_id = save_snapshot(conn, match_id=match_id, payload=payload, success=success, error=err)

                    if jsonl_path is not None:
                        envelope = {
                            "scheduled_snapshot_ts_utc": iso(ts),
                            "minutes_to_kickoff": mt,
                            "kickoff_utc": iso(kickoff),
                            "sofascore_event_id": m.get("event_id"),
                            "sofascore_home": m.get("home"),
                            "sofascore_away": m.get("away"),
                            "sofascore_tournament": m.get("tournament"),
                            "sofascore_tournament_slug": m.get("tournament_slug"),
                            "sqlite_snapshot_id": snapshot_id,
                            **payload,
                        }
                        append_jsonl(jsonl_path, envelope)

                    # small delay between markets to reduce bot-like burst
                    await asyncio.sleep(float(args.between_market_delay_sec))

                m.setdefault("done_minutes", []).append(int(mt))
                save_state(state_path, state)

                # small delay between matches at the same scheduled time
                await asyncio.sleep(float(args.between_match_delay_sec))

    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Track OddsPortal snapshots on a relative-to-kickoff schedule (SofaScore kickoff)")
    p.add_argument("--targets-json", default="v2/tracking/odds_targets_24h.json", help="JSON list with match_url entries")

    p.add_argument("--sqlite", default="data/v2/tracking/relative_schedule.sqlite")
    p.add_argument("--jsonl", default="data/v2/tracking/relative_schedule.jsonl")
    p.add_argument("--schema", default="v2/tracking/schema_odds_tracker_v2.sql")

    p.add_argument("--state", default="data/v2/tracking/relative_schedule_state.json")

    p.add_argument("--storage-state", default="/tmp/oddsportal_storage.json")
    p.add_argument("--headless", action="store_true", default=True)
    p.add_argument("--timeout-ms", type=int, default=120000)
    p.add_argument("--settle-ms", type=int, default=2500)

    p.add_argument("--top-lines", type=int, default=2)
    p.add_argument("--adjacent-delta", type=float, default=0.5)
    p.add_argument("--prefer-lines-ou", default="")
    p.add_argument("--prefer-lines-ah", default="")
    p.add_argument("--pin-lines-first-snapshot", action="store_true", default=True)

    p.add_argument("--between-market-delay-sec", type=float, default=1.5)
    p.add_argument("--between-match-delay-sec", type=float, default=6.0)

    p.add_argument("--start-date", default="", help="YYYY-MM-DD for SofaScore lookup start (default: today UTC)")
    p.add_argument("--lookahead-days", type=int, default=14)
    p.add_argument("--sofascore-cache", default="data/v2/tracking/sofascore_scheduled_cache.json")

    p.add_argument("--due-window-sec", type=float, default=90.0, help="Treat schedule points within this window as the same tick")
    p.add_argument("--miss-grace-sec", type=float, default=15 * 60, help="If a point is older than this, mark missed")

    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
