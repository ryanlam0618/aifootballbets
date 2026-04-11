from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

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


def _norm_team(x: str) -> str:
    x = str(x or "").lower().strip()
    x = re.sub(r"[^a-z0-9\u4e00-\u9fff\s]", " ", x)
    return re.sub(r"\s+", " ", x).strip()


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


# ============================================================
# A) Optional realtime fallback: The Odds API
#    Primary repo direction is SofaScore-first; supported markets stay limited to
#    1X2 / Over/Under / Asian Handicap.
# ============================================================

def _request_odds(league_key: str) -> list[dict]:
    # Primary + backup key fallback (for quota exhaustion)
    keys = [
        (settings_v2.odds_api_key or "").strip(),
        (getattr(settings_v2, "odds_api_key_backup", "") or "").strip(),
    ]
    keys = [k for k in keys if k]
    if not keys:
        return []

    url = f"https://api.the-odds-api.com/v4/sports/{league_key}/odds"

    for api_key in keys:
        params = {
            "apiKey": api_key,
            "regions": "eu,uk",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "decimal",
        }
        try:
            r = requests.get(url, params=params, timeout=25)
            if r.status_code != 200:
                continue
            data = r.json()
            return data if isinstance(data, list) else []
        except Exception:
            continue

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


def _event_matches_fixture(event: dict, fixtures_df: pd.DataFrame) -> bool:
    if fixtures_df is None or fixtures_df.empty:
        return True

    eh = _norm_team(event.get("home_team", ""))
    ea = _norm_team(event.get("away_team", ""))

    for _, fx in fixtures_df.iterrows():
        fh = _norm_team(fx.get("home_team", ""))
        fa = _norm_team(fx.get("away_team", ""))
        if (eh == fh and ea == fa) or (eh == fa and ea == fh):
            return True
    return False


def collect_and_store_snapshot(
    league_keys: list[str],
    db_path: Path,
    fixtures_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Optional realtime fallback only (The Odds API). No 24h history reliance here.
    Primary repo direction is SofaScore-first, and this collector only normalizes
    the 3 supported market families: 1X2 / Over/Under / Asian Handicap.
    - fetch only requested leagues
    - cap leagues per run with ODDS_API_MAX_LEAGUES_PER_RUN
    - keep only events matching target fixtures (if provided)
    """
    _init_db(db_path)
    ts_utc = datetime.now(timezone.utc).isoformat()

    uniq_leagues = list(dict.fromkeys([k for k in league_keys if k]))
    if settings_v2.odds_api_max_leagues_per_run > 0:
        uniq_leagues = uniq_leagues[: settings_v2.odds_api_max_leagues_per_run]

    all_rows: list[OddsRow] = []
    for league_key in uniq_leagues:
        events = _request_odds(league_key)
        for ev in events:
            if not _event_matches_fixture(ev, fixtures_df if fixtures_df is not None else pd.DataFrame()):
                continue
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


# ============================================================
# B) OddsPortal/OddsHarvester: 24h history source
# ============================================================

def maybe_run_oddsharvester_refresh() -> None:
    """
    Optional: run external OddsHarvester command before parsing files.
    User can set ODDSHARVESTER_CMD in .env.
    """
    cmd = (settings_v2.oddsharvester_cmd or "").strip()
    if not cmd:
        return
    try:
        subprocess.run(cmd, shell=True, check=False, timeout=900)
    except Exception:
        pass


def _iter_json_files(root: Path, within_hours: int = 30) -> List[Path]:
    if not root.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    files: List[Path] = []
    for p in root.rglob("*.json"):
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            if mtime >= cutoff:
                files.append(p)
        except Exception:
            continue
    return sorted(files, key=lambda x: x.stat().st_mtime)


def _extract_match_list(obj) -> List[dict]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for key in ["matches", "data", "events", "fixtures", "results"]:
            v = obj.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        return [obj]
    return []


def _extract_timestamp(match_obj: dict, fallback_ts: datetime) -> str:
    for key in ["timestamp", "updated_at", "updatedAt", "scraped_at", "collected_at", "time"]:
        val = match_obj.get(key)
        if not val:
            continue
        if isinstance(val, (int, float)):
            try:
                return datetime.fromtimestamp(float(val), tz=timezone.utc).isoformat()
            except Exception:
                pass
        if isinstance(val, str):
            s = val.strip().replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(s).astimezone(timezone.utc).isoformat()
            except Exception:
                continue
    return fallback_ts.isoformat()


def _line_from_market_name(name: str) -> str:
    # over_under_2_5 -> 2.5 ; asian_handicap_-0_5 -> -0.5
    if name.startswith("over_under_"):
        return name.replace("over_under_", "").replace("_", ".")
    if name.startswith("asian_handicap_"):
        return name.replace("asian_handicap_", "").replace("_", ".")
    return ""


def _to_float(x) -> Optional[float]:
    try:
        v = float(x)
        return v if v > 1.0 else None
    except Exception:
        return None


def _infer_bookmaker(row: dict) -> str:
    for k in ["bookmaker", "bookie", "name", "site"]:
        if k in row and row[k]:
            return str(row[k])
    return "OddsPortal"


def _mkrow(
    match_id: str,
    league_key: str,
    home_team: str,
    away_team: str,
    ts_iso: str,
    bookmaker: str,
    market: str,
    line: str,
    selection: str,
    odd: float,
) -> dict:
    return {
        "match_id": match_id,
        "league_key": league_key,
        "home_team": home_team,
        "away_team": away_team,
        "timestamp_utc": ts_iso,
        "bookmaker": bookmaker or "OddsPortal",
        "market": market,
        "line": line,
        "selection": selection,
        "decimal_odds": odd,
    }


def _extract_market_rows_from_generic_markets(
    match_obj: dict,
    match_id: str,
    league_key: str,
    home_team: str,
    away_team: str,
    ts_iso: str,
) -> List[dict]:
    """
    Fallback parser for non-standard schemas, e.g.:
    {
      "markets": [
        {"market":"1X2","bookmaker":"x","home":1.9,"draw":3.4,"away":4.2},
        {"market":"OU","line":2.5,"over":1.91,"under":1.95},
        {"market":"AH","line":-0.25,"home":1.96,"away":1.90}
      ]
    }
    """
    out: List[dict] = []
    generic = match_obj.get("markets")
    if not isinstance(generic, list):
        return out

    for row in generic:
        if not isinstance(row, dict):
            continue

        mk_raw = str(row.get("market") or row.get("type") or row.get("name") or "").lower()
        bk = _infer_bookmaker(row)
        line = str(row.get("line") or row.get("point") or "")

        if mk_raw in {"1x2", "h2h", "moneyline"}:
            h = _to_float(row.get("home") or row.get("1"))
            d = _to_float(row.get("draw") or row.get("x") or row.get("X"))
            a = _to_float(row.get("away") or row.get("2"))
            if h:
                out.append(_mkrow(match_id, league_key, home_team, away_team, ts_iso, bk, "1X2", "", "Home", h))
            if d:
                out.append(_mkrow(match_id, league_key, home_team, away_team, ts_iso, bk, "1X2", "", "Draw", d))
            if a:
                out.append(_mkrow(match_id, league_key, home_team, away_team, ts_iso, bk, "1X2", "", "Away", a))

        elif mk_raw in {"ou", "o/u", "totals", "over_under", "over under"}:
            over = _to_float(row.get("over") or row.get("o") or row.get("Over"))
            under = _to_float(row.get("under") or row.get("u") or row.get("Under"))
            if over:
                out.append(_mkrow(match_id, league_key, home_team, away_team, ts_iso, bk, "Over/Under", line, "Over", over))
            if under:
                out.append(_mkrow(match_id, league_key, home_team, away_team, ts_iso, bk, "Over/Under", line, "Under", under))

        elif mk_raw in {"ah", "asian", "asian handicap", "spreads"}:
            h = _to_float(row.get("home") or row.get("1") or row.get("h"))
            a = _to_float(row.get("away") or row.get("2") or row.get("a"))
            if h:
                out.append(_mkrow(match_id, league_key, home_team, away_team, ts_iso, bk, "Asian Handicap", line, "Home", h))
            if a:
                out.append(_mkrow(match_id, league_key, home_team, away_team, ts_iso, bk, "Asian Handicap", line, "Away", a))

    return out


def _extract_market_rows(
    match_obj: dict,
    match_id: str,
    league_key: str,
    home_team: str,
    away_team: str,
    ts_iso: str,
) -> List[dict]:
    out: List[dict] = []

    # New/known structure: keys ending with _market
    for key, value in match_obj.items():
        if not str(key).endswith("_market"):
            continue
        if not isinstance(value, list):
            continue

        mname = str(key).replace("_market", "")
        line = _line_from_market_name(mname)

        if mname == "1x2":
            market = "1X2"
            for row in value:
                if not isinstance(row, dict):
                    continue
                bk = _infer_bookmaker(row)
                pairs = [
                    ("Home", row.get("1") or row.get("home")),
                    ("Draw", row.get("X") or row.get("x") or row.get("draw")),
                    ("Away", row.get("2") or row.get("away")),
                ]
                for sel, odd in pairs:
                    ov = _to_float(odd)
                    if ov:
                        out.append(_mkrow(match_id, league_key, home_team, away_team, ts_iso, bk, market, "", sel, ov))

        elif mname.startswith("over_under_"):
            market = "Over/Under"
            for row in value:
                if not isinstance(row, dict):
                    continue
                bk = _infer_bookmaker(row)
                over = _to_float(row.get("over") or row.get("o") or row.get("Over"))
                under = _to_float(row.get("under") or row.get("u") or row.get("Under"))
                if over:
                    out.append(_mkrow(match_id, league_key, home_team, away_team, ts_iso, bk, market, line, "Over", over))
                if under:
                    out.append(_mkrow(match_id, league_key, home_team, away_team, ts_iso, bk, market, line, "Under", under))

        elif mname.startswith("asian_handicap_"):
            market = "Asian Handicap"
            for row in value:
                if not isinstance(row, dict):
                    continue
                bk = _infer_bookmaker(row)
                home = _to_float(row.get("home") or row.get("1") or row.get("h"))
                away = _to_float(row.get("away") or row.get("2") or row.get("a"))
                if home:
                    out.append(_mkrow(match_id, league_key, home_team, away_team, ts_iso, bk, market, line, "Home", home))
                if away:
                    out.append(_mkrow(match_id, league_key, home_team, away_team, ts_iso, bk, market, line, "Away", away))

    # fallback parser if no rows parsed from *_market keys
    if not out:
        out = _extract_market_rows_from_generic_markets(
            match_obj,
            match_id=match_id,
            league_key=league_key,
            home_team=home_team,
            away_team=away_team,
            ts_iso=ts_iso,
        )

    return out


def _match_fixture_id(fixtures_df: pd.DataFrame, home: str, away: str) -> Optional[str]:
    eh = _norm_team(home)
    ea = _norm_team(away)
    for _, fx in fixtures_df.iterrows():
        fh = _norm_team(fx.get("home_team", ""))
        fa = _norm_team(fx.get("away_team", ""))
        if (eh == fh and ea == fa) or (eh == fa and ea == fh):
            return str(fx.get("match_id"))
    return None


def validate_and_normalize_24h_schema(df: pd.DataFrame) -> pd.DataFrame:
    required = {
        "match_id": "",
        "league_key": "",
        "home_team": "",
        "away_team": "",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "bookmaker": "OddsPortal",
        "market": "",
        "line": "",
        "selection": "",
        "decimal_odds": pd.NA,
    }

    out = df.copy()
    for col, default_val in required.items():
        if col not in out.columns:
            out[col] = default_val

    out["bookmaker"] = out["bookmaker"].fillna("OddsPortal").replace("", "OddsPortal")

    # decimal odds validation
    out["decimal_odds"] = pd.to_numeric(out["decimal_odds"], errors="coerce")
    out = out[(out["decimal_odds"].notna()) & (out["decimal_odds"] > 1.0)]

    # known market normalization fallback
    mk = out["market"].astype(str).str.lower()
    out.loc[mk.isin(["h2h", "moneyline"]), "market"] = "1X2"
    out.loc[mk.isin(["ou", "totals", "over_under", "over under"]), "market"] = "Over/Under"
    out.loc[mk.isin(["ah", "asian", "asian handicap", "spreads"]), "market"] = "Asian Handicap"

    # keep only target markets
    out = out[out["market"].isin(["1X2", "Over/Under", "Asian Handicap"])]

    # selection fallback
    out["selection"] = out["selection"].replace({"1": "Home", "2": "Away", "X": "Draw", "x": "Draw"})

    # canonical order
    out = out[
        [
            "match_id",
            "league_key",
            "home_team",
            "away_team",
            "timestamp_utc",
            "bookmaker",
            "market",
            "line",
            "selection",
            "decimal_odds",
        ]
    ]
    return out


def build_odds_24h_csv(fixtures_df: pd.DataFrame, out_csv: Path, source_dir: Optional[Path] = None) -> pd.DataFrame:
    """
    Build 24h odds history from local normalized JSON outputs.
    Supported market families remain limited to 1X2 / Over/Under / Asian Handicap.
    """
    src = source_dir or Path(settings_v2.oddsharvester_data_dir)
    maybe_run_oddsharvester_refresh()

    files = _iter_json_files(src, within_hours=30)
    rows: List[dict] = []

    for fp in files:
        try:
            obj = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue

        mtime = datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc)
        match_list = _extract_match_list(obj)

        for m in match_list:
            home = m.get("home_team") or m.get("home") or m.get("homeTeam") or ""
            away = m.get("away_team") or m.get("away") or m.get("awayTeam") or ""
            if not home or not away:
                continue

            match_id = _match_fixture_id(fixtures_df, str(home), str(away))
            if not match_id:
                continue

            league_key = str(m.get("league_key") or m.get("league") or "")
            ts_iso = _extract_timestamp(m, mtime)
            rows.extend(
                _extract_market_rows(
                    m,
                    match_id=match_id,
                    league_key=league_key,
                    home_team=str(home),
                    away_team=str(away),
                    ts_iso=ts_iso,
                )
            )

    df = pd.DataFrame(rows)

    if not df.empty:
        df = validate_and_normalize_24h_schema(df)

        # Keep last 24h only
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        ts = pd.to_datetime(df["timestamp_utc"], errors="coerce", utc=True)
        df = df[ts >= cutoff]
        df = df.sort_values("timestamp_utc")
        df["implied_prob"] = (1.0 / df["decimal_odds"]).round(6)
        # NOTE: OddsPortal integration removed.
        df["source"] = "sofascore_first_local_history"

        # schema quality stats
        needs_line = df[df["market"].isin(["Over/Under", "Asian Handicap"])]
        if len(needs_line):
            missing_line = (needs_line["line"].astype(str).str.strip() == "").mean()
        else:
            missing_line = 0
        missing_bookie = (df["bookmaker"].astype(str).str.strip() == "").mean() if len(df) else 0
        df["schema_quality"] = "ok"
        if missing_line > 0.2 or missing_bookie > 0.2:
            df["schema_quality"] = "fallback"

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    return df


# ============================================================
# C) Realtime market map for model pricing (normalized 1X2 / OU / AH only)
# ============================================================

def current_market_snapshot(match_ids: list[str], db_path: Path) -> Dict[Tuple[str, str, str], float]:
    """
    Return latest realtime odds map keyed by (match_id, market, selection)
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
    Fallback: map latest realtime snapshot rows by home/away names and rewrite key to fixture.match_id.
    """

    def n(x: str) -> str:
        return _norm_team(x)

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
