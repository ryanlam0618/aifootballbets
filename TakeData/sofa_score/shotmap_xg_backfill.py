#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shotmap xG backfill (resume-safe)
---------------------------------
- Fetch SofaScore /event/{event_id}/shotmap
- Store per-match shotmap xG aggregates
- Optionally patch matches.home_xg_total / away_xg_total when currently 0

Usage:
  python TakeData/sofa_score/shotmap_xg_backfill.py \
    --db data/backfill_sofascore_10y/backfill_10y.sqlite \
    --state data/backfill_sofascore_10y/shotmap_backfill_state.json \
    --only-missing-xg --update-matches
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shotmap_xg_backfill (
          event_id INTEGER PRIMARY KEY,
          match_date TEXT,
          league TEXT,
          home_team TEXT,
          away_team TEXT,
          status_code INTEGER,
          has_shotmap INTEGER,
          has_xg INTEGER,
          shot_count INTEGER,
          home_shotmap_xg REAL,
          away_shotmap_xg REAL,
          fetched_at TEXT,
          error TEXT
        )
        """
    )
    conn.commit()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "started_at": now_iso(),
            "updated_at": now_iso(),
            "processed": 0,
            "ok": 0,
            "not_found": 0,
            "errors": 0,
            "has_shotmap": 0,
            "has_xg": 0,
            "matches_patched": 0,
            "last_event_id": None,
            "last_date": None,
            "total_targets": 0,
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "started_at": now_iso(),
            "updated_at": now_iso(),
            "processed": 0,
            "ok": 0,
            "not_found": 0,
            "errors": 0,
            "has_shotmap": 0,
            "has_xg": 0,
            "matches_patched": 0,
            "last_event_id": None,
            "last_date": None,
            "total_targets": 0,
        }


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def build_target_query(only_missing_xg: bool) -> str:
    base = """
    SELECT m.event_id, m.match_date, m.league, m.home_team, m.away_team,
           m.home_xg_total, m.away_xg_total
    FROM matches m
    LEFT JOIN shotmap_xg_backfill s ON s.event_id = m.event_id
    WHERE m.event_id IS NOT NULL
      AND s.event_id IS NULL
    """
    if only_missing_xg:
        base += " AND (COALESCE(m.home_xg_total,0)=0 OR COALESCE(m.away_xg_total,0)=0) "
    base += " ORDER BY m.match_date ASC, m.event_id ASC "
    return base


def fetch_shotmap(session: requests.Session, event_id: int, timeout: int = 20):
    url = f"https://www.sofascore.com/api/v1/event/{event_id}/shotmap"
    r = session.get(url, timeout=timeout)
    return r


def main() -> None:
    parser = argparse.ArgumentParser(description="Shotmap xG backfill")
    parser.add_argument("--db", default="data/backfill_sofascore_10y/backfill_10y.sqlite")
    parser.add_argument("--state", default="data/backfill_sofascore_10y/shotmap_backfill_state.json")
    parser.add_argument("--only-missing-xg", action="store_true", default=True)
    parser.add_argument("--update-matches", action="store_true", default=True)
    parser.add_argument("--sleep-min", type=float, default=0.05)
    parser.add_argument("--sleep-max", type=float, default=0.15)
    parser.add_argument("--checkpoint-every", type=int, default=100)
    args = parser.parse_args()

    db_path = Path(args.db)
    state_path = Path(args.state)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_tables(conn)

    state = load_state(state_path)

    q = build_target_query(args.only_missing_xg)
    rows = conn.execute(q).fetchall()
    total_targets = len(rows)
    state["total_targets"] = total_targets
    save_state(state_path, state)

    print(f"[INFO] targets={total_targets} only_missing_xg={args.only_missing_xg}")
    if total_targets == 0:
        print("[INFO] Nothing to process")
        return

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
    })

    processed_in_run = 0

    for row in rows:
        event_id = int(row["event_id"])
        match_date = str(row["match_date"])
        league = str(row["league"])
        home = str(row["home_team"])
        away = str(row["away_team"])

        status_code = 0
        has_shotmap = 0
        has_xg = 0
        shot_count = 0
        home_xg = 0.0
        away_xg = 0.0
        err = ""

        try:
            r = fetch_shotmap(s, event_id)
            status_code = r.status_code
            if r.status_code == 200:
                payload = r.json() if r.text else {}
                arr = (payload or {}).get("shotmap") or []
                shot_count = len(arr)
                has_shotmap = 1 if shot_count > 0 else 0
                for sh in arr:
                    xg = sh.get("xg")
                    try:
                        xv = float(xg) if xg is not None else 0.0
                    except Exception:
                        xv = 0.0
                    if sh.get("isHome") is True:
                        home_xg += xv
                    elif sh.get("isHome") is False:
                        away_xg += xv
                has_xg = 1 if (home_xg > 0 or away_xg > 0) else 0
            elif r.status_code == 404:
                pass
            else:
                err = f"HTTP {r.status_code}"
        except Exception as e:
            err = str(e)

        conn.execute(
            """
            INSERT OR REPLACE INTO shotmap_xg_backfill
            (event_id, match_date, league, home_team, away_team, status_code, has_shotmap, has_xg,
             shot_count, home_shotmap_xg, away_shotmap_xg, fetched_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                match_date,
                league,
                home,
                away,
                status_code,
                has_shotmap,
                has_xg,
                shot_count,
                round(home_xg, 6),
                round(away_xg, 6),
                now_iso(),
                err,
            ),
        )

        patched = 0
        if args.update_matches and has_xg:
            # 只回填目前為 0 的 xG 欄位
            cur = conn.execute(
                "SELECT home_xg_total, away_xg_total FROM matches WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if cur is not None:
                h0 = float(cur[0] or 0)
                a0 = float(cur[1] or 0)
                nh = home_xg if h0 == 0 and home_xg > 0 else h0
                na = away_xg if a0 == 0 and away_xg > 0 else a0
                if nh != h0 or na != a0:
                    conn.execute(
                        "UPDATE matches SET home_xg_total=?, away_xg_total=? WHERE event_id=?",
                        (round(nh, 6), round(na, 6), event_id),
                    )
                    patched = 1

        # update state counters
        state["processed"] = int(state.get("processed", 0)) + 1
        processed_in_run += 1
        state["last_event_id"] = event_id
        state["last_date"] = match_date

        if status_code == 200:
            state["ok"] = int(state.get("ok", 0)) + 1
        elif status_code == 404:
            state["not_found"] = int(state.get("not_found", 0)) + 1
        else:
            state["errors"] = int(state.get("errors", 0)) + 1

        if has_shotmap:
            state["has_shotmap"] = int(state.get("has_shotmap", 0)) + 1
        if has_xg:
            state["has_xg"] = int(state.get("has_xg", 0)) + 1
        if patched:
            state["matches_patched"] = int(state.get("matches_patched", 0)) + 1

        if processed_in_run % args.checkpoint_every == 0:
            conn.commit()
            save_state(state_path, state)
            pct = (processed_in_run / total_targets) * 100 if total_targets else 100
            print(
                f"[CHK] run_processed={processed_in_run}/{total_targets} ({pct:.2f}%) "
                f"ok={state['ok']} 404={state['not_found']} err={state['errors']} "
                f"has_xg={state['has_xg']} patched={state['matches_patched']}"
            )

        time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    conn.commit()
    save_state(state_path, state)
    print("[DONE] Shotmap xG backfill completed")


if __name__ == "__main__":
    main()
