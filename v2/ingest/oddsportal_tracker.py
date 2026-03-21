from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd


@dataclass(frozen=True)
class TrackerQuote:
    home_team: str
    away_team: str
    market: str
    line: float | None
    selection: str
    odds: float


def _norm_team(x: str) -> str:
    return (x or "").strip().lower().replace("&", "and")


def _market_key(market_type: str, line: float | None) -> str:
    mt = (market_type or "").strip().upper()
    if mt in {"1X2", "H2H", "HDA"}:
        return "1X2"
    if mt in {"OU", "O/U", "TOTALS"}:
        return f"Over/Under {float(line):g}" if line is not None else "Over/Under"
    if mt in {"AH", "ASIANHANDICAP"}:
        return f"Asian Handicap {float(line):g}" if line is not None else "Asian Handicap"
    return mt or "1X2"


def load_latest_quotes(
    sqlite_path: Path,
    fixtures_df: pd.DataFrame,
    prefer_label: str | None = None,
) -> Dict[Tuple[str, str, str], float]:
    """Return market odds map compatible with v2.models.predict.predict_markets.

    Output key: (match_id, market_key, selection) -> avg_decimal_odds

    This reads OddsPortal tracker output sqlite (v2/tracking/odds_tracker.py schema).
    It uses the latest successful snapshot per match_url+market and averages odds across bookmakers.
    """

    if fixtures_df.empty:
        return {}
    if not sqlite_path.exists() or sqlite_path.stat().st_size == 0:
        return {}

    con = sqlite3.connect(str(sqlite_path))
    try:
        # latest successful snapshot per match
        q = """
        WITH latest AS (
          SELECT s.match_id, MAX(s.snapshot_ts_utc) AS ts
          FROM odds_snapshot s
          WHERE s.success = 1
          GROUP BY s.match_id
        )
        SELECT m.id AS match_id, m.match_url, m.label, l.ts AS snapshot_ts_utc
        FROM latest l
        JOIN odds_match m ON m.id = l.match_id
        """
        latest = pd.read_sql_query(q, con)
        if latest.empty:
            return {}

        if prefer_label is not None and "label" in latest.columns:
            latest = latest[latest["label"].fillna("") == prefer_label]
            if latest.empty:
                return {}

        # Join latest snapshots to quotes
        qq = """
        SELECT m.match_url, m.label, s.snapshot_ts_utc, q.bookmaker, q.market_type, q.line, q.home, q.draw, q.away
        FROM odds_quote q
        JOIN odds_snapshot s ON s.id = q.snapshot_id
        JOIN odds_match m ON m.id = s.match_id
        """
        quotes = pd.read_sql_query(qq, con)
        if quotes.empty:
            return {}

        quotes = quotes.merge(latest[["match_url", "snapshot_ts_utc"]], on=["match_url", "snapshot_ts_utc"], how="inner")
        if quotes.empty:
            return {}

        # Build a mapping from (home, away) to match_id using fixtures_df
        fx_map: dict[tuple[str, str], str] = {}
        for _, r in fixtures_df.iterrows():
            fx_map[(_norm_team(r.get("home_team")), _norm_team(r.get("away_team")))] = str(r.get("match_id"))

        out: dict[tuple[str, str, str], list[float]] = {}

        for _, r in quotes.iterrows():
            match_url = str(r.get("match_url") or "")

            # Map by slug contains BOTH team tokens (best-effort; no external parsing).
            slug = match_url.lower().replace("-", " ")
            match_id = None
            def _slug_token_hit(team: str) -> bool:
                # Team names vs OddsPortal slug often abbreviates ("Manchester United" -> "man united").
                toks = team.split()
                if all(tok in slug for tok in toks):
                    return True
                # common abbreviations
                if len(toks) >= 2:
                    abbr2 = f"{toks[0][:3]} {toks[1]}"  # man united
                    if abbr2 in slug:
                        return True
                if toks and toks[-1] in {"united", "city", "town", "rovers", "athletic"}:
                    # accept last token match
                    if toks[-1] in slug:
                        return True
                return False

            for (h, a), mid in fx_map.items():
                if not h or not a:
                    continue
                h_ok = _slug_token_hit(h)
                a_ok = _slug_token_hit(a)
                if h_ok and a_ok:
                    match_id = mid
                    break
            if not match_id:
                continue

            mt = str(r.get("market_type") or "1X2")
            line = r.get("line")
            try:
                line_f = float(line) if line is not None else None
            except Exception:
                line_f = None

            market_key = _market_key(mt, line_f)

            # Expand 1X2: home/draw/away; OU/AH: home/away as Over/Under
            if (str(r.get("home")) not in {"None", "nan", ""}):
                try:
                    out.setdefault((match_id, market_key, "Home"), []).append(float(r.get("home")))
                except Exception:
                    pass
            if (str(r.get("draw")) not in {"None", "nan", ""}):
                try:
                    out.setdefault((match_id, market_key, "Draw"), []).append(float(r.get("draw")))
                except Exception:
                    pass
            if (str(r.get("away")) not in {"None", "nan", ""}):
                try:
                    out.setdefault((match_id, market_key, "Away"), []).append(float(r.get("away")))
                except Exception:
                    pass

        # avg across bookmakers
        avg_map: dict[tuple[str, str, str], float] = {}
        for k, vals in out.items():
            if not vals:
                continue
            avg_map[k] = float(sum(vals) / len(vals))
        return avg_map
    finally:
        con.close()
