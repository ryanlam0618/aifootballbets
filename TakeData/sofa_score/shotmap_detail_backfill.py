#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Backfill detailed shotmap rows (resume-safe)
- Reads event list from shotmap_xg_backfill where has_shotmap=1
- Fetches /api/v1/event/{event_id}/shotmap
- Stores per-shot rows in shotmap_details table
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


API_TMPL = "https://www.sofascore.com/api/v1/event/{event_id}/shotmap"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "started_at": now_iso(),
            "updated_at": now_iso(),
            "processed": 0,
            "ok": 0,
            "not_found": 0,
            "errors": 0,
            "rows_upserted": 0,
            "last_event_id": None,
            "last_date": None,
            "total_targets": 0,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shotmap_details (
          event_id INTEGER,
          match_date TEXT,
          league TEXT,
          home_team TEXT,
          away_team TEXT,
          shot_id INTEGER,
          is_home_shot INTEGER,
          team_name TEXT,
          player_id INTEGER,
          player_name TEXT,
          player_position TEXT,
          minute INTEGER,
          added_time INTEGER,
          time_seconds INTEGER,
          period_time_seconds INTEGER,
          incident_type TEXT,
          shot_type TEXT,
          situation TEXT,
          body_part TEXT,
          goal_mouth_location TEXT,
          player_x REAL,
          player_y REAL,
          player_z REAL,
          goal_mouth_x REAL,
          goal_mouth_y REAL,
          goal_mouth_z REAL,
          block_x REAL,
          block_y REAL,
          block_z REAL,
          xg REAL,
          status_code INTEGER,
          fetched_at TEXT,
          error TEXT,
          PRIMARY KEY (event_id, shot_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shotmap_detail_events (
          event_id INTEGER PRIMARY KEY,
          match_date TEXT,
          league TEXT,
          home_team TEXT,
          away_team TEXT,
          status_code INTEGER,
          shot_count INTEGER,
          fetched_at TEXT,
          error TEXT
        )
        """
    )
    conn.commit()


def to_int(v):
    try:
        return int(v)
    except Exception:
        return None


def to_float(v):
    try:
        return float(v)
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill detailed shotmap rows")
    ap.add_argument("--db", default="data/backfill_sofascore_10y/backfill_10y.sqlite")
    ap.add_argument("--state", default="data/backfill_sofascore_10y/shotmap_detail_state.json")
    ap.add_argument("--sleep-min", type=float, default=0.03)
    ap.add_argument("--sleep-max", type=float, default=0.08)
    ap.add_argument("--checkpoint-every", type=int, default=100)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=60000")
    ensure_tables(db)

    state_path = Path(args.state)
    state = load_state(state_path)

    done_ids = set(r[0] for r in db.execute("SELECT event_id FROM shotmap_detail_events").fetchall())
    rows = db.execute(
        """
        SELECT event_id, match_date, league, home_team, away_team
        FROM shotmap_xg_backfill
        WHERE has_shotmap=1
        ORDER BY match_date ASC, event_id ASC
        """
    ).fetchall()
    rows = [r for r in rows if int(r["event_id"]) not in done_ids]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    total = len(rows)
    state["total_targets"] = total
    save_state(state_path, state)
    print(f"[INFO] targets={total}")

    if total == 0:
        print("[INFO] Nothing to process")
        return

    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
    })

    processed_run = 0

    for r in rows:
        event_id = int(r["event_id"])
        match_date = str(r["match_date"])
        league = str(r["league"])
        home = str(r["home_team"])
        away = str(r["away_team"])

        status_code = 0
        err = ""
        upserted = 0

        try:
            resp = sess.get(API_TMPL.format(event_id=event_id), timeout=20)
            status_code = resp.status_code
            shots = []
            if status_code == 200:
                payload = resp.json() if resp.text else {}
                shots = (payload or {}).get("shotmap") or []
                for sh in shots:
                    db.execute(
                        """
                        INSERT OR REPLACE INTO shotmap_details
                        (event_id, match_date, league, home_team, away_team, shot_id, is_home_shot,
                         team_name, player_id, player_name, player_position,
                         minute, added_time, time_seconds, period_time_seconds,
                         incident_type, shot_type, situation, body_part, goal_mouth_location,
                         player_x, player_y, player_z,
                         goal_mouth_x, goal_mouth_y, goal_mouth_z,
                         block_x, block_y, block_z,
                         xg, status_code, fetched_at, error)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            match_date,
                            league,
                            home,
                            away,
                            to_int(sh.get("id")),
                            1 if sh.get("isHome") is True else 0 if sh.get("isHome") is False else None,
                            (sh.get("team") or {}).get("name") if isinstance(sh.get("team"), dict) else None,
                            to_int((sh.get("player") or {}).get("id") if isinstance(sh.get("player"), dict) else None),
                            (sh.get("player") or {}).get("name") if isinstance(sh.get("player"), dict) else None,
                            (sh.get("player") or {}).get("position") if isinstance(sh.get("player"), dict) else None,
                            to_int(sh.get("time")),
                            to_int(sh.get("addedTime")),
                            to_int(sh.get("timeSeconds")),
                            to_int(sh.get("periodTimeSeconds")),
                            sh.get("incidentType"),
                            sh.get("shotType"),
                            sh.get("situation"),
                            sh.get("bodyPart"),
                            sh.get("goalMouthLocation"),
                            to_float(sh.get("playerCoordinates", {}).get("x") if isinstance(sh.get("playerCoordinates"), dict) else None),
                            to_float(sh.get("playerCoordinates", {}).get("y") if isinstance(sh.get("playerCoordinates"), dict) else None),
                            to_float(sh.get("playerCoordinates", {}).get("z") if isinstance(sh.get("playerCoordinates"), dict) else None),
                            to_float(sh.get("goalMouthCoordinates", {}).get("x") if isinstance(sh.get("goalMouthCoordinates"), dict) else None),
                            to_float(sh.get("goalMouthCoordinates", {}).get("y") if isinstance(sh.get("goalMouthCoordinates"), dict) else None),
                            to_float(sh.get("goalMouthCoordinates", {}).get("z") if isinstance(sh.get("goalMouthCoordinates"), dict) else None),
                            to_float(sh.get("blockCoordinates", {}).get("x") if isinstance(sh.get("blockCoordinates"), dict) else None),
                            to_float(sh.get("blockCoordinates", {}).get("y") if isinstance(sh.get("blockCoordinates"), dict) else None),
                            to_float(sh.get("blockCoordinates", {}).get("z") if isinstance(sh.get("blockCoordinates"), dict) else None),
                            to_float(sh.get("xg")),
                            status_code,
                            now_iso(),
                            "",
                        ),
                    )
                    upserted += 1
                state["ok"] = int(state.get("ok", 0)) + 1
            elif status_code == 404:
                state["not_found"] = int(state.get("not_found", 0)) + 1
            else:
                state["errors"] = int(state.get("errors", 0)) + 1
                err = f"HTTP {status_code}"

            db.execute(
                """
                INSERT OR REPLACE INTO shotmap_detail_events
                (event_id, match_date, league, home_team, away_team, status_code, shot_count, fetched_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, match_date, league, home, away, status_code, len(shots), now_iso(), err),
            )

        except Exception as e:
            state["errors"] = int(state.get("errors", 0)) + 1
            err = str(e)
            db.execute(
                """
                INSERT OR REPLACE INTO shotmap_detail_events
                (event_id, match_date, league, home_team, away_team, status_code, shot_count, fetched_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, match_date, league, home, away, status_code, 0, now_iso(), err),
            )

        state["rows_upserted"] = int(state.get("rows_upserted", 0)) + upserted
        state["processed"] = int(state.get("processed", 0)) + 1
        state["last_event_id"] = event_id
        state["last_date"] = match_date
        processed_run += 1

        if processed_run % args.checkpoint_every == 0:
            db.commit()
            save_state(state_path, state)
            pct = (processed_run / total) * 100 if total else 100
            print(
                f"[CHK] run={processed_run}/{total} ({pct:.2f}%) "
                f"ok={state['ok']} 404={state['not_found']} err={state['errors']} upserted={state['rows_upserted']}"
            )

        time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    db.commit()
    save_state(state_path, state)
    print("[DONE] detailed shotmap backfill completed")


if __name__ == "__main__":
    main()
