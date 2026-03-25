#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.oddsportal_one_match import extract_odds


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    return rows


def ensure_db(conn: sqlite3.Connection, schema_path: Path) -> None:
    conn.executescript(schema_path.read_text(encoding="utf-8"))

    # label segmentation helpers (migration-safe)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(odds_match)").fetchall()}
    if "competition" not in cols:
        conn.execute("ALTER TABLE odds_match ADD COLUMN competition TEXT")
    if "season" not in cols:
        conn.execute("ALTER TABLE odds_match ADD COLUMN season TEXT")
    if "match_date" not in cols:
        conn.execute("ALTER TABLE odds_match ADD COLUMN match_date TEXT")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_odds_match_comp_season ON odds_match(competition, season)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_odds_match_label ON odds_match(label)")
    conn.commit()


def upsert_match(conn: sqlite3.Connection, row: dict, market: str, label: str) -> int:
    url = str(row.get("match_url") or "").split("#", 1)[0]
    conn.execute(
        """
        INSERT OR IGNORE INTO odds_match(match_url, market, label)
        VALUES (?, ?, ?)
        """,
        (url, market, label),
    )
    conn.execute(
        """
        UPDATE odds_match
        SET label = ?, competition = ?, season = ?, match_date = ?
        WHERE match_url = ? AND market = ?
        """,
        (
            label,
            row.get("competition") or "",
            row.get("season") or "",
            row.get("date_text") or "",
            url,
            market,
        ),
    )
    r = conn.execute(
        "SELECT id FROM odds_match WHERE match_url=? AND market=?",
        (url, market),
    ).fetchone()
    if not r:
        raise RuntimeError(f"failed upsert odds_match for {url} {market}")
    return int(r[0])


def has_success_snapshot(conn: sqlite3.Connection, match_id: int) -> bool:
    r = conn.execute(
        "SELECT 1 FROM odds_snapshot WHERE match_id=? AND success=1 LIMIT 1",
        (match_id,),
    ).fetchone()
    return r is not None


def insert_snapshot(conn: sqlite3.Connection, match_id: int, payload: dict, success: bool, error: str = "") -> int:
    ts = payload.get("snapshot_ts_utc") or now_iso()
    qn = len(payload.get("odds") or [])
    row_count = payload.get("row_count_seen")

    cur = conn.execute(
        """
        INSERT INTO odds_snapshot(match_id, snapshot_ts_utc, success, row_count_seen, quote_count, error)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (match_id, ts, 1 if success else 0, row_count, qn, error),
    )
    snapshot_id = int(cur.lastrowid)

    quotes = payload.get("odds") or []
    if quotes:
        conn.executemany(
            """
            INSERT OR REPLACE INTO odds_quote(snapshot_id, bookmaker, market_type, line, home, draw, away, raw)
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


async def run_one(
    conn: sqlite3.Connection,
    row: dict,
    market: str,
    storage_state: Path,
    headless: bool,
    top_lines: int,
    adjacent_delta: float,
    timeout_ms: int,
    settle_ms: int,
) -> tuple[bool, str, int]:
    label = f"{row.get('competition','')}-{row.get('season','')}"
    match_id = upsert_match(conn, row=row, market=market, label=label)

    if has_success_snapshot(conn, match_id):
        return True, "already_done", match_id

    try:
        payload = await extract_odds(
            match_url=row["match_url"],
            market=market,
            storage_state_path=storage_state,
            headless=headless,
            timeout_ms=timeout_ms,
            settle_ms=settle_ms,
            top_lines=top_lines,
            adjacent_delta=adjacent_delta,
        )
        success = len(payload.get("odds") or []) > 0
        err = "" if success else "no_quotes_extracted"
        insert_snapshot(conn, match_id, payload, success=success, error=err)
        return success, err or "ok", match_id
    except Exception as e:
        payload = {
            "snapshot_ts_utc": now_iso(),
            "row_count_seen": 0,
            "odds": [],
            "market_type": market,
        }
        insert_snapshot(conn, match_id, payload, success=False, error=str(e))
        return False, str(e), match_id


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill OddsPortal history from season match list")
    p.add_argument("--match-list", required=True, help="jsonl file generated by oddsportal_season_matchlist.py")
    p.add_argument("--markets", default="1X2,OU,AH", help="comma-separated market types")
    p.add_argument("--top-lines", type=int, default=2)
    p.add_argument("--adjacent-delta", type=float, default=0.5, help="adjacent +/- line delta for OU/AH")
    p.add_argument("--storage-state", default="/tmp/oddsportal_storage.json")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--timeout-ms", type=int, default=120000)
    p.add_argument("--settle-ms", type=int, default=2500)
    p.add_argument("--sqlite", default="data/oddsportal_history/oddsportal_history.sqlite")
    p.add_argument("--schema", default="v2/tracking/schema_odds_tracker_v2.sql")
    p.add_argument("--state", default="data/oddsportal_history/state_oddsportal_history.json")
    p.add_argument("--limit", type=int, default=0)
    return p.parse_args()


async def _run(args: argparse.Namespace) -> int:
    rows = load_jsonl(Path(args.match_list))
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    sqlite_path = Path(args.sqlite)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    ensure_db(conn, Path(args.schema))

    st_path = Path(args.state)
    if st_path.exists():
        try:
            state = json.loads(st_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    else:
        state = {}

    state.setdefault("started_at", now_iso())
    state["updated_at"] = now_iso()
    state["match_list"] = str(args.match_list)
    state["markets"] = markets
    state["total_matches"] = len(rows)
    state.setdefault("processed", 0)
    state.setdefault("ok", 0)
    state.setdefault("errors", 0)
    state.setdefault("skipped", 0)

    st_path.parent.mkdir(parents=True, exist_ok=True)

    for idx, row in enumerate(rows, start=1):
        if not row.get("match_url"):
            continue
        for m in markets:
            adj = float(args.adjacent_delta) if m in {"OU", "AH"} else 0.0
            success, note, match_id = await run_one(
                conn=conn,
                row=row,
                market=m,
                storage_state=Path(args.storage_state),
                headless=args.headless,
                top_lines=args.top_lines,
                adjacent_delta=adj,
                timeout_ms=args.timeout_ms,
                settle_ms=args.settle_ms,
            )
            if note == "already_done":
                state["skipped"] = int(state.get("skipped", 0)) + 1
            elif success:
                state["ok"] = int(state.get("ok", 0)) + 1
            else:
                state["errors"] = int(state.get("errors", 0)) + 1
            state["processed"] = int(state.get("processed", 0)) + 1
            state["last_match_url"] = row.get("match_url")
            state["last_market"] = m
            state["last_match_id"] = match_id
            state["updated_at"] = now_iso()
            st_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{idx}/{len(rows)}] market={m} success={success} note={note} url={row.get('match_url')}")

    conn.close()
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(parse_args())))
