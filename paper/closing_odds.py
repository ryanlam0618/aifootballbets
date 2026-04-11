from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict


def _norm_text(s: str) -> str:
    low = (s or "").lower()
    low = re.sub(r"[^a-z0-9]+", " ", low)
    return " ".join(low.split())


def _norm_market_to_tracker(market: str) -> str:
    m = (market or "").strip().lower()
    if m == "1x2":
        return "1X2"
    if m.startswith("over/under"):
        return "OU"
    if m.startswith("asian handicap"):
        return "AH"
    return (market or "").strip().upper()


def _parse_ts(s: str) -> datetime | None:
    txt = (s or "").strip()
    if not txt:
        return None
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
        return dt
    except Exception:
        return None


def _line_match(expected_line: str, got_line) -> bool:
    exp = (expected_line or "").strip()
    if exp == "":
        return True
    try:
        a = float(exp)
        b = float(got_line)
        return abs(a - b) <= 1e-6
    except Exception:
        return False


def _extract_side_price(selection: str, home, draw, away) -> float | None:
    sel = (selection or "").strip().lower()
    if sel == "home":
        try:
            return float(home)
        except Exception:
            return None
    if sel == "draw":
        try:
            return float(draw)
        except Exception:
            return None
    if sel == "away":
        try:
            return float(away)
        except Exception:
            return None
    return None


def load_tracker_closing_odds_by_bet_id(odds_tracker_sqlite: Path, unsettled_rows: list) -> Dict[str, float]:
    """
    Optional hook: map bet_id -> closing odds from OddsPortal tracker snapshots.

    Matching strategy:
    - match by team names found in (label + match_url)
    - market mapping: 1X2 / OU / AH
    - OU/AH additionally require exact line match
    - pick latest successful snapshot <= kickoff if available, else latest successful snapshot
    - within that snapshot, use max quoted price for the selected side
    """
    p = Path(odds_tracker_sqlite)
    if not p.exists():
        return {}

    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
              m.id AS match_id,
              m.match_url,
              m.label,
              m.market AS match_market,
              s.id AS snapshot_id,
              s.snapshot_ts_utc,
              q.market_type,
              q.line,
              q.home,
              q.draw,
              q.away
            FROM odds_match m
            JOIN odds_snapshot s ON s.match_id = m.id
            JOIN odds_quote q ON q.snapshot_id = s.id
            WHERE s.success = 1
            """
        ).fetchall()
    except Exception:
        conn.close()
        return {}
    finally:
        conn.close()

    if not rows:
        return {}

    out: Dict[str, float] = {}

    for b in unsettled_rows:
        bet_id = str(b["bet_id"])
        home = _norm_text(str(b["home"] or ""))
        away = _norm_text(str(b["away"] or ""))
        market = _norm_market_to_tracker(str(b["market"] or ""))
        line = str(b["line"] or "").strip()
        selection = str(b["selection"] or "")
        kickoff = _parse_ts(str(b["kickoff_time_hkt"] or ""))

        if not (home and away and market and selection):
            continue

        by_snapshot: dict[int, dict] = {}

        for r in rows:
            mm = _norm_market_to_tracker(str(r["market_type"] or r["match_market"] or ""))
            if mm != market:
                continue

            hay = _norm_text(f"{r['label'] or ''} {r['match_url'] or ''}")
            if home not in hay or away not in hay:
                continue

            if market in {"OU", "AH"} and not _line_match(line, r["line"]):
                continue

            px = _extract_side_price(selection, r["home"], r["draw"], r["away"])
            if px is None or px <= 1.0:
                continue

            sid = int(r["snapshot_id"])
            ts = _parse_ts(str(r["snapshot_ts_utc"] or ""))
            prev = by_snapshot.get(sid)
            if prev is None:
                by_snapshot[sid] = {"ts": ts, "price": px}
            else:
                prev["price"] = max(float(prev["price"]), px)

        if not by_snapshot:
            continue

        items = list(by_snapshot.values())
        items.sort(key=lambda x: (x["ts"] is not None, x["ts"]), reverse=True)

        chosen = None
        if kickoff is not None:
            before = [x for x in items if x["ts"] is not None and x["ts"] <= kickoff]
            if before:
                before.sort(key=lambda x: x["ts"], reverse=True)
                chosen = before[0]

        if chosen is None:
            chosen = items[0]

        out[bet_id] = float(chosen["price"])

    return out
