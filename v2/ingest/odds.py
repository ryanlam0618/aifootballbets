from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import requests

from v2.config import settings_v2


@dataclass
class OddsRow:
    match_id: str
    league_key: str
    home_team: str
    away_team: str
    timestamp_utc: str
    bookmaker: str
    market: str
    line: str
    selection: str
    decimal_odds: float


def _init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS odds_snapshots (
              match_id TEXT,
              league_key TEXT,
              home_team TEXT,
              away_team TEXT,
              timestamp_utc TEXT,
              bookmaker TEXT,
              market TEXT,
              line TEXT,
              selection TEXT,
              decimal_odds REAL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _request_odds(league_key: str) -> list[dict]:
    if not settings_v2.odds_api_key:
        return []

    url = f"https://api.the-odds-api.com/v4/sports/{league_key}/odds"
    params = {
        "apiKey": settings_v2.odds_api_key,
        "regions": "eu,uk",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "decimal",
    }
    try:
        r = requests.get(url, params=params, timeout=25)
        if r.status_code != 200:
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _event_to_rows(event: dict, ts_utc: str, league_key: str) -> list[OddsRow]:
    rows: list[OddsRow] = []
    match_id = str(event.get("id", ""))
    home = event.get("home_team", "")
    away = event.get("away_team", "")

    for bk in event.get("bookmakers", []) or []:
        bk_name = bk.get("title", "Unknown")
        for mk in bk.get("markets", []) or []:
            mkey = mk.get("key", "")
            for out in mk.get("outcomes", []) or []:
                line = out.get("point")
                line_str = "" if line is None else str(line)
                market = ""
                selection = out.get("name", "")

                if mkey == "h2h":
                    market = "1X2"
                    if selection == home:
                        selection = "Home"
                    elif selection == away:
                        selection = "Away"
                    else:
                        selection = "Draw"
                elif mkey == "spreads":
                    market = "Asian Handicap"
                    if selection == home:
                        selection = "Home"
                    elif selection == away:
                        selection = "Away"
                elif mkey == "totals":
                    market = "Over/Under"
                    if selection.lower().startswith("over"):
                        selection = "Over"
                    elif selection.lower().startswith("under"):
                        selection = "Under"
                else:
                    continue

                try:
                    price = float(out.get("price"))
                except Exception:
                    continue

                rows.append(
                    OddsRow(
                        match_id=match_id,
                        league_key=league_key,
                        home_team=home,
                        away_team=away,
                        timestamp_utc=ts_utc,
                        bookmaker=bk_name,
                        market=market,
                        line=line_str,
                        selection=selection,
                        decimal_odds=price,
                    )
                )
    return rows


def collect_and_store_snapshot(league_keys: list[str], db_path: Path) -> pd.DataFrame:
    _init_db(db_path)
    ts_utc = datetime.now(timezone.utc).isoformat()
    all_rows: list[OddsRow] = []

    for league_key in league_keys:
        events = _request_odds(league_key)
        for ev in events:
            all_rows.extend(_event_to_rows(ev, ts_utc, league_key))

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame([r.__dict__ for r in all_rows])
    conn = sqlite3.connect(db_path)
    try:
        df.to_sql("odds_snapshots", conn, if_exists="append", index=False)
    finally:
        conn.close()
    return df


def build_odds_24h_csv(match_ids: list[str], db_path: Path, out_csv: Path) -> pd.DataFrame:
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        if not match_ids:
            return pd.DataFrame()

        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        placeholders = ",".join(["?"] * len(match_ids))
        sql = f"""
        SELECT match_id, league_key, home_team, away_team, timestamp_utc, bookmaker,
               market, line, selection, decimal_odds
        FROM odds_snapshots
        WHERE match_id IN ({placeholders})
          AND timestamp_utc >= ?
        ORDER BY timestamp_utc ASC
        """
        params = [*match_ids, since]
        df = pd.read_sql_query(sql, conn, params=params)

        if df.empty:
            out_csv.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out_csv, index=False, encoding="utf-8-sig")
            return df

        df["implied_prob"] = (1.0 / df["decimal_odds"]).round(6)
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        return df
    finally:
        conn.close()


def current_market_snapshot(match_ids: list[str], db_path: Path) -> Dict[Tuple[str, str, str], float]:
    """
    Return latest odds map keyed by (match_id, market, selection)
    using average across bookmakers for the latest timestamp.
    """
    conn = sqlite3.connect(db_path)
    try:
        if not match_ids:
            return {}
        placeholders = ",".join(["?"] * len(match_ids))
        sql = f"""
        SELECT match_id, market, line, selection, AVG(decimal_odds) AS avg_odds
        FROM odds_snapshots
        WHERE match_id IN ({placeholders})
          AND timestamp_utc = (
            SELECT MAX(s2.timestamp_utc)
            FROM odds_snapshots s2
            WHERE s2.match_id = odds_snapshots.match_id
          )
        GROUP BY match_id, market, line, selection
        """
        df = pd.read_sql_query(sql, conn, params=match_ids)
        out: Dict[Tuple[str, str, str], float] = {}
        for _, row in df.iterrows():
            mk = row["market"]
            line = str(row.get("line", "") or "")
            market_key = f"{mk} {line}".strip()
            out[(row["match_id"], market_key, row["selection"])] = float(row["avg_odds"])
        return out
    finally:
        conn.close()


def current_market_snapshot_by_teams(fixtures_df: pd.DataFrame, db_path: Path) -> Dict[Tuple[str, str, str], float]:
    """
    Fallback: map latest snapshot rows by home/away names and rewrite key to fixture.match_id.
    """

    def n(x: str) -> str:
        return " ".join(str(x or "").lower().replace("-", " ").split())

    conn = sqlite3.connect(db_path)
    try:
        if fixtures_df.empty:
            return {}

        sql = """
        SELECT match_id, home_team, away_team, market, line, selection, decimal_odds, timestamp_utc
        FROM odds_snapshots
        WHERE timestamp_utc = (SELECT MAX(timestamp_utc) FROM odds_snapshots)
        """
        snap = pd.read_sql_query(sql, conn)
        if snap.empty:
            return {}

        out: Dict[Tuple[str, str, str], float] = {}
        for _, fx in fixtures_df.iterrows():
            fmid = str(fx["match_id"])
            fh = n(fx["home_team"])
            fa = n(fx["away_team"])

            m = snap[(snap["home_team"].map(n) == fh) & (snap["away_team"].map(n) == fa)]
            if m.empty:
                m = snap[(snap["home_team"].map(n) == fa) & (snap["away_team"].map(n) == fh)]

            if m.empty:
                continue

            grouped = m.groupby(["market", "line", "selection"], as_index=False)["decimal_odds"].mean()
            for _, row in grouped.iterrows():
                mk = row["market"]
                line = str(row.get("line", "") or "")
                market_key = f"{mk} {line}".strip()
                out[(fmid, market_key, row["selection"])] = float(row["decimal_odds"])

        return out
    finally:
        conn.close()
