from __future__ import annotations

import argparse
import asyncio
import json
import math
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from v2.tracking.oddsportal_one_match import extract_odds, normalize_market_type, parse_line_csv


@dataclass(frozen=True)
class Target:
    match_url: str
    market: str = "1X2"
    label: str | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_schema(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def ensure_db(conn: sqlite3.Connection, schema_sql: str) -> None:
    conn.executescript(schema_sql)
    conn.commit()

    # Migration-friendly guard in case old schema is used.
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(odds_quote)").fetchall()
    }
    if "line" not in cols:
        conn.execute("ALTER TABLE odds_quote ADD COLUMN line REAL")
    if "market_type" not in cols:
        conn.execute("ALTER TABLE odds_quote ADD COLUMN market_type TEXT NOT NULL DEFAULT '1X2'")
    conn.commit()


def upsert_match(conn: sqlite3.Connection, target: Target) -> int:
    conn.execute(
        """
        INSERT OR IGNORE INTO odds_match (match_url, market, label)
        VALUES (?, ?, ?)
        """,
        (target.match_url, target.market, target.label),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM odds_match WHERE match_url = ? AND market = ?",
        (target.match_url, target.market),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Failed to resolve odds_match id for {target.match_url} [{target.market}]")
    return int(row[0])


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def save_snapshot(conn: sqlite3.Connection, match_id: int, payload: dict, success: bool, error: str | None) -> int:
    snapshot_ts = payload.get("snapshot_ts_utc") or utc_now_iso()
    row_count_seen = payload.get("row_count_seen")
    quotes = payload.get("odds") or []

    cur = conn.execute(
        """
        INSERT INTO odds_snapshot (match_id, snapshot_ts_utc, success, row_count_seen, quote_count, error)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (match_id, snapshot_ts, 1 if success else 0, row_count_seen, len(quotes), error),
    )
    snapshot_id = int(cur.lastrowid)

    if quotes:
        conn.executemany(
            """
            INSERT OR REPLACE INTO odds_quote (snapshot_id, bookmaker, market_type, line, home, draw, away, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, 
            [
                (
                    snapshot_id,
                    q.get("bookmaker"),
                    q.get("market_type") or payload.get("market_type") or "1X2",
                    q.get("line"),
                    q.get("home"),
                    q.get("draw"),
                    q.get("away"),
                    q.get("raw"),
                )
                for q in quotes
                if q.get("bookmaker")
            ],
        )

    conn.commit()
    return snapshot_id


def parse_targets(args: argparse.Namespace) -> list[Target]:
    targets: list[Target] = []

    for u in args.match_url or []:
        targets.append(Target(match_url=u, market=args.market))

    if args.targets_json:
        data = json.loads(Path(args.targets_json).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise SystemExit("--targets-json must contain a JSON array of target objects")
        for item in data:
            if not isinstance(item, dict) or "match_url" not in item:
                raise SystemExit("Each target in --targets-json must be an object with match_url")
            targets.append(
                Target(
                    match_url=item["match_url"],
                    market=item.get("market", args.market),
                    label=item.get("label"),
                )
            )

    dedup: dict[tuple[str, str], Target] = {}
    for t in targets:
        dedup[(t.match_url, t.market)] = t

    out = list(dedup.values())
    if not out:
        raise SystemExit("No targets provided. Use --match-url and/or --targets-json")
    return out


async def sample_one(
    target: Target,
    storage_state: Path,
    headless: bool,
    timeout_ms: int,
    settle_ms: int,
    top_lines: int,
    prefer_lines: Iterable[float] | None,
    fixed_lines: Iterable[float] | None,
) -> tuple[dict, bool, str | None]:
    try:
        payload = await extract_odds(
            match_url=target.match_url,
            market=target.market,
            storage_state_path=storage_state,
            headless=headless,
            timeout_ms=timeout_ms,
            settle_ms=settle_ms,
            top_lines=top_lines,
            prefer_lines=prefer_lines,
            fixed_lines=fixed_lines,
        )
        quote_count = len(payload.get("odds") or [])
        success = quote_count > 0
        err = None if success else "no_quotes_extracted"
        return payload, success, err
    except Exception as e:
        return {
            "match_url": target.match_url,
            "market": target.market,
            "market_type": normalize_market_type(target.market),
            "snapshot_ts_utc": utc_now_iso(),
            "row_count_seen": 0,
            "odds": [],
            "selected_lines": list(fixed_lines or []),
            "line_frequency": {},
        }, False, str(e)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track OddsPortal odds movement over time")
    parser.add_argument("--match-url", action="append", help="Target match URL (repeat for multiple matches)")
    parser.add_argument("--targets-json", help="JSON file with list of targets: [{match_url, market?, label?}, ...]")
    parser.add_argument("--market", default="1X2", help="Default market label for targets without market")

    parser.add_argument("--sample-every-min", type=int, default=10, help="Sampling interval in minutes")
    parser.add_argument("--duration-hours", type=float, default=24.0, help="Total tracking duration in hours")
    parser.add_argument("--between-match-delay-sec", type=float, default=8.0, help="Delay between matches in a cycle")

    parser.add_argument("--sqlite", default="data/v2/tracking/odds_tracker.sqlite", help="SQLite output path")
    parser.add_argument("--schema", default="v2/tracking/schema_odds_tracker_v2.sql", help="Schema SQL path")
    parser.add_argument("--jsonl", default="", help="Optional JSONL append path for raw snapshots")

    parser.add_argument("--storage-state", default="/tmp/oddsportal_storage.json", help="Playwright storage_state path")
    parser.add_argument("--headless", action="store_true", help="Use headless Chromium")
    parser.add_argument("--timeout-ms", type=int, default=120000, help="Navigation timeout in ms")
    parser.add_argument("--settle-ms", type=int, default=2500, help="Post-render settle time in ms")

    parser.add_argument("--top-lines", type=int, default=2, help="Top-K lines to keep for OU/AH (default: 2)")
    parser.add_argument(
        "--prefer-lines",
        default="",
        help="Preferred OU lines CSV, e.g. '2.5,2.75'. Applied to OU targets.",
    )
    parser.add_argument(
        "--prefer-lines-ah",
        default="",
        help="Preferred AH lines CSV, e.g. '-0.25,0.0'. Applied to AH targets.",
    )
    parser.add_argument(
        "--pin-lines-first-snapshot",
        action="store_true",
        default=True,
        help="Pin selected lines after first successful snapshot per match+market (default: on)",
    )
    parser.add_argument(
        "--no-pin-lines-first-snapshot",
        action="store_false",
        dest="pin_lines_first_snapshot",
        help="Disable line pinning; recompute top lines each snapshot.",
    )
    return parser.parse_args()


async def run_tracker(args: argparse.Namespace) -> int:
    targets = parse_targets(args)

    sqlite_path = Path(args.sqlite)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = load_schema(Path(args.schema))
    storage_state = Path(args.storage_state)
    jsonl_path = Path(args.jsonl) if args.jsonl else None

    prefer_lines_ou = parse_line_csv(args.prefer_lines)
    prefer_lines_ah = parse_line_csv(args.prefer_lines_ah)

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_db(conn, schema_sql)
        target_ids = {t: upsert_match(conn, t) for t in targets}

        interval_sec = max(60, int(args.sample_every_min * 60))
        total_sec = max(interval_sec, int(args.duration_hours * 3600))
        cycles = max(1, math.ceil(total_sec / interval_sec))

        # Pinned line memory per (match_url, market_type)
        pinned_lines: dict[tuple[str, str], list[float]] = {}

        for cycle_idx in range(cycles):
            cycle_started = time.time()
            print(f"[{utc_now_iso()}] cycle {cycle_idx + 1}/{cycles}: sampling {len(targets)} matches")

            for idx, t in enumerate(targets, start=1):
                mt = normalize_market_type(t.market)
                key = (t.match_url, mt)
                preferred = prefer_lines_ou if mt == "OU" else (prefer_lines_ah if mt == "AH" else [])
                fixed = pinned_lines.get(key) if (args.pin_lines_first_snapshot and mt in {"OU", "AH"}) else None

                payload, success, err = await sample_one(
                    target=t,
                    storage_state=storage_state,
                    headless=args.headless,
                    timeout_ms=args.timeout_ms,
                    settle_ms=args.settle_ms,
                    top_lines=args.top_lines,
                    prefer_lines=preferred,
                    fixed_lines=fixed,
                )

                selected_lines = payload.get("selected_lines") or []
                if (
                    args.pin_lines_first_snapshot
                    and mt in {"OU", "AH"}
                    and success
                    and key not in pinned_lines
                    and selected_lines
                ):
                    pinned_lines[key] = list(selected_lines)

                snapshot_id = save_snapshot(conn, target_ids[t], payload, success=success, error=err)
                qn = len(payload.get("odds") or [])
                lines_note = ""
                if mt in {"OU", "AH"}:
                    lines_note = f" selected_lines={selected_lines or pinned_lines.get(key, [])}"
                print(
                    f"  - [{idx}/{len(targets)}] snapshot_id={snapshot_id} success={success} quotes={qn}"
                    f" market={mt}{lines_note} url={t.match_url}"
                )

                if jsonl_path:
                    append_jsonl(
                        jsonl_path,
                        {
                            "snapshot_id": snapshot_id,
                            "success": success,
                            "error": err,
                            **payload,
                        },
                    )

                if idx < len(targets):
                    await asyncio.sleep(max(0.0, float(args.between_match_delay_sec)))

            elapsed = time.time() - cycle_started
            remaining = interval_sec - elapsed
            if cycle_idx < cycles - 1 and remaining > 0:
                print(f"[{utc_now_iso()}] cycle complete, sleeping {remaining:.1f}s")
                await asyncio.sleep(remaining)

        print(f"[{utc_now_iso()}] tracking complete")
        return 0
    finally:
        conn.close()


def main() -> None:
    args = parse_args()
    raise SystemExit(asyncio.run(run_tracker(args)))


if __name__ == "__main__":
    main()
