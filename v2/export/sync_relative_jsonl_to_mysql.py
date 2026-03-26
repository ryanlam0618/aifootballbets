#!/usr/bin/env python3
from __future__ import annotations

"""Sync relative-schedule JSONL (OddsPortal snapshots) into MySQL 8.

Input JSONL: produced by v2/tracking/run_relative_schedule.py
Each line includes the original extractor payload plus an envelope:
- scheduled_snapshot_ts_utc
- minutes_to_kickoff
- kickoff_utc
- sofascore_event_id
- sofascore_home/away/tournament

This script is idempotent:
- snapshots upserted by UNIQUE(match_url, market_type, snapshot_ts_utc)
- quotes upserted by UNIQUE(snapshot_id, bookmaker, line)

Usage:
  python3 -m v2.export.sync_relative_jsonl_to_mysql \
    --jsonl data/v2/tracking/relative_schedule.jsonl \
    --mysql-url "mysql://user:pass@host:3306/dbname" \
    --schema v2/export/mysql_schema_oddsportal_tracking.sql \
    --create-schema

Notes:
- Requires: pip install mysql-connector-python
"""

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse, unquote


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class MySQLConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


def parse_mysql_url(mysql_url: str) -> MySQLConfig:
    u = urlparse(mysql_url)
    if u.scheme not in {"mysql"}:
        raise ValueError("mysql-url must start with mysql://")
    host = u.hostname or "localhost"
    port = int(u.port or 3306)
    user = unquote(u.username or "")
    password = unquote(u.password or "")
    database = (u.path or "/").lstrip("/")
    if not user or not database:
        raise ValueError("mysql-url must include user and database")
    return MySQLConfig(host=host, port=port, user=user, password=password, database=database)


def read_env_mysql() -> str | None:
    # Allow keeping creds out of CLI.
    return os.getenv("MYSQL_URL") or None


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    yield obj
            except Exception:
                continue


def ensure_schema(cur, schema_sql: str) -> None:
    # mysql-connector does not support executescript; split by ; safely-ish.
    stmts = [s.strip() for s in schema_sql.split(";") if s.strip()]
    for s in stmts:
        cur.execute(s)


def upsert_snapshot(cur, row: dict[str, Any]) -> int:
    # Return snapshot_id.
    match_url = str(row.get("match_url") or "")
    market_type = str(row.get("market_type") or row.get("market") or "")
    snapshot_ts = parse_dt(row.get("snapshot_ts_utc"))
    if not match_url or not market_type or snapshot_ts is None:
        raise ValueError("missing match_url/market_type/snapshot_ts_utc")

    sched_ts = parse_dt(row.get("scheduled_snapshot_ts_utc"))
    kickoff_utc = parse_dt(row.get("kickoff_utc"))

    minutes_to_kickoff = row.get("minutes_to_kickoff")
    try:
        minutes_to_kickoff = int(minutes_to_kickoff) if minutes_to_kickoff is not None else None
    except Exception:
        minutes_to_kickoff = None

    sofascore_event_id = row.get("sofascore_event_id")
    try:
        sofascore_event_id = int(sofascore_event_id) if sofascore_event_id not in (None, "") else None
    except Exception:
        sofascore_event_id = None

    home = row.get("sofascore_home")
    away = row.get("sofascore_away")
    tournament = row.get("sofascore_tournament")
    tournament_slug = row.get("sofascore_tournament_slug")

    detected = row.get("detected_market_tab")
    row_count_seen = row.get("row_count_seen")
    quote_count = len(row.get("odds") or [])

    sql = (
        "INSERT INTO oddsportal_snapshot (match_url, market_type, snapshot_ts_utc, scheduled_snapshot_ts_utc, minutes_to_kickoff, "
        "sofascore_event_id, kickoff_utc, home_team, away_team, tournament, tournament_slug, detected_market_tab, row_count_seen, quote_count) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE "
        "scheduled_snapshot_ts_utc=VALUES(scheduled_snapshot_ts_utc), minutes_to_kickoff=VALUES(minutes_to_kickoff), "
        "sofascore_event_id=COALESCE(VALUES(sofascore_event_id), sofascore_event_id), "
        "kickoff_utc=COALESCE(VALUES(kickoff_utc), kickoff_utc), "
        "home_team=COALESCE(VALUES(home_team), home_team), away_team=COALESCE(VALUES(away_team), away_team), "
        "tournament=COALESCE(VALUES(tournament), tournament), tournament_slug=COALESCE(VALUES(tournament_slug), tournament_slug), "
        "detected_market_tab=VALUES(detected_market_tab), row_count_seen=VALUES(row_count_seen), quote_count=VALUES(quote_count)"
    )

    cur.execute(
        sql,
        (
            match_url,
            market_type,
            snapshot_ts,
            sched_ts,
            minutes_to_kickoff,
            sofascore_event_id,
            kickoff_utc,
            home,
            away,
            tournament,
            tournament_slug,
            detected,
            int(row_count_seen) if row_count_seen is not None else None,
            int(quote_count),
        ),
    )

    # Get id (for upsert, need SELECT)
    cur.execute(
        "SELECT id FROM oddsportal_snapshot WHERE match_url=%s AND market_type=%s AND snapshot_ts_utc=%s",
        (match_url, market_type, snapshot_ts),
    )
    r = cur.fetchone()
    return int(r[0])


def upsert_quotes(cur, snapshot_id: int, odds: list[dict[str, Any]]) -> int:
    n = 0
    if not odds:
        return 0

    sql = (
        "INSERT INTO oddsportal_quote (snapshot_id, bookmaker, line, home_odds, draw_odds, away_odds, raw) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE home_odds=VALUES(home_odds), draw_odds=VALUES(draw_odds), away_odds=VALUES(away_odds), raw=VALUES(raw)"
    )

    for q in odds:
        bm = str(q.get("bookmaker") or "").strip()
        if not bm:
            continue
        line = q.get("line")
        try:
            line = float(line) if line is not None else None
        except Exception:
            line = None

        def f(x):
            try:
                return float(x) if x is not None else None
            except Exception:
                return None

        cur.execute(
            sql,
            (
                int(snapshot_id),
                bm,
                line,
                f(q.get("home")),
                f(q.get("draw")),
                f(q.get("away")),
                (str(q.get("raw"))[:512] if q.get("raw") is not None else None),
            ),
        )
        n += 1
    return n


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sync OddsPortal relative-schedule JSONL to MySQL 8")
    p.add_argument("--jsonl", required=True, help="Path to relative_schedule.jsonl")
    p.add_argument("--mysql-url", default="", help="mysql://user:pass@host:3306/db")
    p.add_argument("--schema", default="v2/export/mysql_schema_oddsportal_tracking.sql")
    p.add_argument("--create-schema", action="store_true")
    p.add_argument("--since-bytes", type=int, default=0, help="Start reading JSONL from byte offset")
    p.add_argument("--max-lines", type=int, default=0, help="Optional cap for testing")
    p.add_argument("--commit-every", type=int, default=200)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        raise SystemExit(f"JSONL not found: {jsonl_path}")

    mysql_url = (args.mysql_url or read_env_mysql() or "").strip()
    if not mysql_url:
        raise SystemExit("Provide --mysql-url or set MYSQL_URL env")

    cfg = parse_mysql_url(mysql_url)

    try:
        import mysql.connector  # type: ignore
    except Exception as e:
        raise SystemExit(
            "Missing dependency mysql-connector-python. Install it (pip) in the aifootballbets env. Error: " + str(e)
        )

    con = mysql.connector.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        autocommit=False,
    )
    cur = con.cursor()

    if args.create_schema:
        schema_sql = Path(args.schema).read_text(encoding="utf-8")
        ensure_schema(cur, schema_sql)
        con.commit()

    # Read with byte offset support.
    processed = 0
    upserted_quotes = 0
    with jsonl_path.open("rb") as f:
        if args.since_bytes:
            f.seek(int(args.since_bytes))
        while True:
            line = f.readline()
            if not line:
                break
            try:
                obj = json.loads(line.decode("utf-8", errors="replace").strip())
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue

            snap_id = upsert_snapshot(cur, obj)
            upserted_quotes += upsert_quotes(cur, snap_id, obj.get("odds") or [])
            processed += 1

            if processed % int(args.commit_every) == 0:
                con.commit()

            if args.max_lines and processed >= int(args.max_lines):
                break

    con.commit()
    cur.close()
    con.close()

    print(
        json.dumps(
            {
                "jsonl": str(jsonl_path),
                "processed_lines": processed,
                "upserted_quotes": upserted_quotes,
                "mysql": {"host": cfg.host, "port": cfg.port, "database": cfg.database, "user": cfg.user},
                "finished_at_utc": utc_now().isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
