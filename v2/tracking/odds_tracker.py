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

from scripts.oddsportal_one_match import extract_odds


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
            INSERT OR REPLACE INTO odds_quote (snapshot_id, bookmaker, home, draw, away, raw)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot_id,
                    q.get("bookmaker"),
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


async def sample_one(target: Target, storage_state: Path, headless: bool, timeout_ms: int, settle_ms: int) -> tuple[dict, bool, str | None]:
    try:
        payload = await extract_odds(
            match_url=target.match_url,
            market=target.market,
            storage_state_path=storage_state,
            headless=headless,
            timeout_ms=timeout_ms,
            settle_ms=settle_ms,
        )
        quote_count = len(payload.get("odds") or [])
        success = quote_count > 0
        err = None if success else "no_quotes_extracted"
        return payload, success, err
    except Exception as e:
        return {
            "match_url": target.match_url,
            "market": target.market,
            "snapshot_ts_utc": utc_now_iso(),
            "row_count_seen": 0,
            "odds": [],
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
    parser.add_argument("--schema", default="v2/tracking/schema_odds_tracker.sql", help="Schema SQL path")
    parser.add_argument("--jsonl", default="", help="Optional JSONL append path for raw snapshots")

    parser.add_argument("--storage-state", default="/tmp/oddsportal_storage.json", help="Playwright storage_state path")
    parser.add_argument("--headless", action="store_true", help="Use headless Chromium")
    parser.add_argument("--timeout-ms", type=int, default=120000, help="Navigation timeout in ms")
    parser.add_argument("--settle-ms", type=int, default=2500, help="Post-render settle time in ms")
    return parser.parse_args()


async def run_tracker(args: argparse.Namespace) -> int:
    targets = parse_targets(args)

    sqlite_path = Path(args.sqlite)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = load_schema(Path(args.schema))
    storage_state = Path(args.storage_state)
    jsonl_path = Path(args.jsonl) if args.jsonl else None

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_db(conn, schema_sql)
        target_ids = {t: upsert_match(conn, t) for t in targets}

        interval_sec = max(60, int(args.sample_every_min * 60))
        total_sec = max(interval_sec, int(args.duration_hours * 3600))
        cycles = max(1, math.ceil(total_sec / interval_sec))

        for cycle_idx in range(cycles):
            cycle_started = time.time()
            print(f"[{utc_now_iso()}] cycle {cycle_idx + 1}/{cycles}: sampling {len(targets)} matches")

            for idx, t in enumerate(targets, start=1):
                payload, success, err = await sample_one(
                    target=t,
                    storage_state=storage_state,
                    headless=args.headless,
                    timeout_ms=args.timeout_ms,
                    settle_ms=args.settle_ms,
                )
                snapshot_id = save_snapshot(conn, target_ids[t], payload, success=success, error=err)
                qn = len(payload.get("odds") or [])
                print(
                    f"  - [{idx}/{len(targets)}] snapshot_id={snapshot_id} success={success} quotes={qn} "
                    f"url={t.match_url}"
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
