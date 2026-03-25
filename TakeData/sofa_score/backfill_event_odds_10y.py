#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Backfill historical odds from SofaScore event odds endpoint.
Markets covered:
- 1X2 (Full time)
- Over/Under (Match goals, all available lines)
- Asian Handicap

Resume-safe with sqlite + state json.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TABLE_NAME = "event_odds_10y_multi"

def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _fetch_json_node(url: str, timeout: int = 20) -> tuple[int, dict[str, Any]]:
    script = _project_root() / "scripts" / "sofascore_fetch.js"
    cmd = ["node", str(script), "--url", url, "--timeout-ms", str(int(max(1000, timeout * 1000)))]
    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=max(5, int(timeout + 5)),
    )
    if proc.returncode == 0:
        return 200, (json.loads(proc.stdout) if proc.stdout else {})
    err = (proc.stderr or "").lower()
    if "http 404" in err:
        return 404, {}
    raise RuntimeError(proc.stderr.strip() or f"fetch failed for {url}")


TARGET_LEAGUES = {
    "Premier League",
    "La Liga",
    "Serie A",
    "Bundesliga",
    "Ligue 1",
    "J1 League",
    "K League 1",
    "Chinese Super League",
    "A-League Men",
    "FA Cup",
    "EFL Cup",
    "Copa del Rey",
    "Coppa Italia",
    "DFB Pokal",
    "Coupe de France",
    "Emperor's Cup",
    "J.League Cup",
    "Korean FA Cup",
    "Chinese FA Cup",
    "Australia Cup",
    "AFC Champions League",
    "FIFA Club World Cup",
    "Intercontinental Cup",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def frac_to_decimal(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if "/" in s:
        try:
            a, b = s.split("/", 1)
            return 1.0 + (float(a) / float(b))
        except Exception:
            return None
    try:
        x = float(s)
        return x if x > 1.0 else None
    except Exception:
        return None


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
          event_id INTEGER,
          match_date TEXT,
          league TEXT,
          home_team TEXT,
          away_team TEXT,
          market TEXT,
          line TEXT,
          selection TEXT,
          open_decimal REAL,
          current_decimal REAL,
          source_id INTEGER,
          fetched_at TEXT,
          status_code INTEGER,
          error TEXT,
          PRIMARY KEY (event_id, source_id, market, line, selection)
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
            "rows_upserted": 0,
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
            "rows_upserted": 0,
            "last_event_id": None,
            "last_date": None,
            "total_targets": 0,
        }


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_ah_choice(name: str, home: str, away: str) -> tuple[str, str] | None:
    # Example: "(-1.75) RC Lens"
    if not isinstance(name, str):
        return None
    m = re.match(r"^\(([-+]?\d+(?:\.\d+)?)\)\s*(.+)$", name.strip())
    if not m:
        return None
    line = m.group(1)
    team = m.group(2).strip().lower()
    if team == home.lower():
        sel = "Home"
    elif team == away.lower():
        sel = "Away"
    else:
        # fallback by containment
        if home.lower() in team:
            sel = "Home"
        elif away.lower() in team:
            sel = "Away"
        else:
            return None
    return line, sel


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill event odds 10y from SofaScore API")
    parser.add_argument("--matches-db", default="data/backfill_sofascore_10y/backfill_10y.sqlite")
    parser.add_argument("--out-db", default="data/backfill_sofascore_10y/event_odds_10y.sqlite")
    parser.add_argument("--state", default="data/backfill_sofascore_10y/event_odds_backfill_state.json")
    parser.add_argument("--sleep-min", type=float, default=0.05)
    parser.add_argument("--sleep-max", type=float, default=0.15)
    parser.add_argument("--checkpoint-every", type=int, default=100)
    parser.add_argument("--all-leagues", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--provider-ids", default="1,5", help="comma-separated provider ids, e.g. 1,5")
    parser.add_argument("--start-date", default="", help="optional filter YYYY-MM-DD")
    parser.add_argument("--end-date", default="", help="optional filter YYYY-MM-DD")
    args = parser.parse_args()

    provider_ids = [int(x.strip()) for x in str(args.provider_ids).split(",") if x.strip().isdigit()]
    if not provider_ids:
        provider_ids = [1]

    matches_db = sqlite3.connect(args.matches_db)
    matches_db.row_factory = sqlite3.Row
    matches_db.execute("PRAGMA busy_timeout=60000")

    out_db = sqlite3.connect(args.out_db)
    out_db.row_factory = sqlite3.Row
    out_db.execute("PRAGMA busy_timeout=60000")

    ensure_table(out_db)

    state_path = Path(args.state)
    state = load_state(state_path)

    # target rows: only not yet existing in out table
    done_ids = set(
        r[0]
        for r in out_db.execute(
            f"SELECT DISTINCT event_id FROM {TABLE_NAME} WHERE event_id IS NOT NULL"
        ).fetchall()
    )

    q = """
    SELECT event_id, match_date, league, home_team, away_team
    FROM matches
    WHERE event_id IS NOT NULL
    """
    if args.start_date:
        q += f" AND match_date >= '{args.start_date}' "
    if args.end_date:
        q += f" AND match_date <= '{args.end_date}' "
    q += " ORDER BY match_date ASC, event_id ASC "
    rows = [r for r in matches_db.execute(q).fetchall() if int(r["event_id"]) not in done_ids]

    if not args.all_leagues:
        rows = [r for r in rows if str(r["league"]) in TARGET_LEAGUES]

    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    total_targets = len(rows)
    state["total_targets"] = total_targets
    save_state(state_path, state)
    print(f"[INFO] targets={total_targets}")

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
            got_any_200 = False
            got_any_non404 = False

            for provider_id in provider_ids:
                url = f"https://www.sofascore.com/api/v1/event/{event_id}/odds/{provider_id}/all"
                status_code, payload = _fetch_json_node(url, timeout=20)

                if status_code == 200:
                    got_any_200 = True
                    markets = payload.get("markets") or []
                    for m in markets:
                        name = str(m.get("marketName") or "")
                        choices = m.get("choices") or []

                        if name == "Full time":
                            for c in choices:
                                nm = c.get("name")
                                if nm == "1":
                                    sel = "Home"
                                elif nm in ("X", "x"):
                                    sel = "Draw"
                                elif nm == "2":
                                    sel = "Away"
                                else:
                                    continue
                                open_d = frac_to_decimal(c.get("initialFractionalValue"))
                                cur_d = frac_to_decimal(c.get("fractionalValue"))
                                out_db.execute(
                                    f"""
                                    INSERT OR REPLACE INTO {TABLE_NAME}
                                    (event_id, match_date, league, home_team, away_team, market, line, selection,
                                     open_decimal, current_decimal, source_id, fetched_at, status_code, error)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        event_id,
                                        match_date,
                                        league,
                                        home,
                                        away,
                                        "1x2",
                                        "",
                                        sel,
                                        open_d,
                                        cur_d,
                                        provider_id,
                                        now_iso(),
                                        status_code,
                                        "",
                                    ),
                                )
                                upserted += 1

                        elif name == "Match goals":
                            line = str(m.get("choiceGroup") or "")
                            for c in choices:
                                sel_raw = str(c.get("name") or "")
                                if sel_raw.lower() not in ("over", "under"):
                                    continue
                                sel = "Over" if sel_raw.lower() == "over" else "Under"
                                open_d = frac_to_decimal(c.get("initialFractionalValue"))
                                cur_d = frac_to_decimal(c.get("fractionalValue"))
                                out_db.execute(
                                    f"""
                                    INSERT OR REPLACE INTO {TABLE_NAME}
                                    (event_id, match_date, league, home_team, away_team, market, line, selection,
                                     open_decimal, current_decimal, source_id, fetched_at, status_code, error)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        event_id,
                                        match_date,
                                        league,
                                        home,
                                        away,
                                        "over_under",
                                        line,
                                        sel,
                                        open_d,
                                        cur_d,
                                        provider_id,
                                        now_iso(),
                                        status_code,
                                        "",
                                    ),
                                )
                                upserted += 1

                        elif name == "Asian handicap":
                            for c in choices:
                                parsed = parse_ah_choice(str(c.get("name") or ""), home, away)
                                if not parsed:
                                    continue
                                line, sel = parsed
                                open_d = frac_to_decimal(c.get("initialFractionalValue"))
                                cur_d = frac_to_decimal(c.get("fractionalValue"))
                                out_db.execute(
                                    f"""
                                    INSERT OR REPLACE INTO {TABLE_NAME}
                                    (event_id, match_date, league, home_team, away_team, market, line, selection,
                                     open_decimal, current_decimal, source_id, fetched_at, status_code, error)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        event_id,
                                        match_date,
                                        league,
                                        home,
                                        away,
                                        "asian_handicap",
                                        line,
                                        sel,
                                        open_d,
                                        cur_d,
                                        provider_id,
                                        now_iso(),
                                        status_code,
                                        "",
                                    ),
                                )
                                upserted += 1

                elif status_code != 404:
                    got_any_non404 = True

            if got_any_200:
                state["ok"] = int(state.get("ok", 0)) + 1
            elif not got_any_non404:
                state["not_found"] = int(state.get("not_found", 0)) + 1
                out_db.execute(
                    f"""
                    INSERT OR REPLACE INTO {TABLE_NAME}
                    (event_id, match_date, league, home_team, away_team, market, line, selection,
                     open_decimal, current_decimal, source_id, fetched_at, status_code, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        match_date,
                        league,
                        home,
                        away,
                        "meta",
                        "",
                        "",
                        None,
                        None,
                        None,
                        now_iso(),
                        404,
                        "not_found_all_providers",
                    ),
                )
            else:
                state["errors"] = int(state.get("errors", 0)) + 1
                err = "non-404 provider failure"

        except Exception as e:
            state["errors"] = int(state.get("errors", 0)) + 1
            err = str(e)

        if err:
            out_db.execute(
                f"""
                INSERT OR REPLACE INTO {TABLE_NAME}
                (event_id, match_date, league, home_team, away_team, market, line, selection,
                 open_decimal, current_decimal, source_id, fetched_at, status_code, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    match_date,
                    league,
                    home,
                    away,
                    "meta",
                    "",
                    "",
                    None,
                    None,
                    None,
                    now_iso(),
                    status_code,
                    err,
                ),
            )

        state["rows_upserted"] = int(state.get("rows_upserted", 0)) + upserted
        state["processed"] = int(state.get("processed", 0)) + 1
        processed_run += 1
        state["last_event_id"] = event_id
        state["last_date"] = match_date

        if processed_run % args.checkpoint_every == 0:
            out_db.commit()
            save_state(state_path, state)
            pct = (processed_run / total_targets) * 100 if total_targets else 100
            print(
                f"[CHK] run={processed_run}/{total_targets} ({pct:.2f}%) "
                f"ok={state['ok']} 404={state['not_found']} err={state['errors']} upserted={state['rows_upserted']}"
            )

        time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    out_db.commit()
    save_state(state_path, state)
    print("[DONE] event odds backfill complete")


if __name__ == "__main__":
    main()
