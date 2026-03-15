from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
from typing import Dict, Optional

import pandas as pd


def export_recommendations(df: pd.DataFrame, out_csv: Path) -> pd.DataFrame:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "match_id",
        "league",
        "home_team",
        "away_team",
        "market",
        "line",
        "selection",
        "odds",
        "model_probability",
        "implied_probability",
        "edge",
        "ev",
        "confidence",
        "suggested_stake",
        "bankroll_pct",
        "rationale",
        "expected_value_assessment",
        "bet_flag",
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    out = df[cols].copy()
    out.to_csv(out_csv, index=False, encoding="utf-8-sig")
    return out


def export_betting_records_xlsx(reco_df: pd.DataFrame, out_xlsx: Path) -> pd.DataFrame:
    rows = []
    best = (
        reco_df[reco_df["bet_flag"] == True]
        .sort_values(["match_id", "edge"], ascending=[True, False])
        .groupby("match_id", as_index=False)
        .head(1)
    )

    for _, r in best.iterrows():
        rows.append(
            {
                "Date": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M"),
                "League": r.get("league"),
                "Home": r.get("home_team"),
                "Away": r.get("away_team"),
                "Market": r.get("market"),
                "Line": r.get("line"),
                "Selection": r.get("selection"),
                "Odds": r.get("odds"),
                "Model Prob": r.get("model_probability"),
                "EV": r.get("ev"),
                "Stake": r.get("suggested_stake"),
                "Stake %": r.get("bankroll_pct"),
                "Reason": r.get("rationale"),
                "Result (Win/Loss)": "",
                "Profit": "",
            }
        )

    columns = [
        "Date",
        "League",
        "Home",
        "Away",
        "Market",
        "Line",
        "Selection",
        "Odds",
        "Model Prob",
        "EV",
        "Stake",
        "Stake %",
        "Reason",
        "Result (Win/Loss)",
        "Profit",
    ]
    out_df = pd.DataFrame(rows, columns=columns)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_excel(out_xlsx, index=False)
    return out_df


def _market_winrate(df: pd.DataFrame, market: str) -> str:
    d = df[df["Market"] == market]
    settled = d[d["Result (Win/Loss)"].astype(str).str.strip() != ""]
    if settled.empty:
        return "N/A"
    wins = settled[settled["Result (Win/Loss)"].astype(str).str.upper().str.startswith("W")]
    return f"{len(wins)}/{len(settled)} ({len(wins)/len(settled):.1%})"


def export_summary_report(reco_df: pd.DataFrame, records_df: pd.DataFrame, out_md: Path) -> str:
    total = len(reco_df)
    bet_count = int((reco_df.get("bet_flag", False) == True).sum()) if total else 0

    if records_df.empty or "Stake %" not in records_df.columns:
        high_alloc = pd.DataFrame(columns=records_df.columns)
    else:
        stake_series = pd.to_numeric(records_df["Stake %"], errors="coerce")
        high_alloc = records_df[stake_series > 0.40]

    if not high_alloc.empty and "Result (Win/Loss)" in high_alloc.columns:
        settled_high = high_alloc[high_alloc["Result (Win/Loss)"].astype(str).str.strip() != ""]
    else:
        settled_high = pd.DataFrame(columns=high_alloc.columns)

    if not settled_high.empty:
        high_win = settled_high[settled_high["Result (Win/Loss)"].astype(str).str.upper().str.startswith("W")]
        high_line = f"{len(high_win)}/{len(settled_high)} ({len(high_win)/len(settled_high):.1%})"
    else:
        high_line = "N/A"

    content = f"""# v2 Summary Report

- Total candidate picks: {total}
- Recommended bets (edge filter): {bet_count}

## Market win rates (settled only)
- 1X2: {_market_winrate(records_df, '1X2')}
- Asian Handicap: {_market_winrate(records_df, 'Asian Handicap')}
- Over/Under: {_market_winrate(records_df, 'Over/Under')}

## High allocation (>40% bankroll) win rate
- {high_line}

## Notes
- 未結算注單不納入勝率。
- 如資料源缺失，對應指標以 NA 標記，並降低信心。
"""
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(content, encoding="utf-8")
    return content


def _ensure_tracking_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS bet_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bet_id TEXT NOT NULL,
            bet_time_hkt TEXT,
            kickoff_time_hkt TEXT,
            closing_time_hkt TEXT,
            league TEXT,
            home TEXT,
            away TEXT,
            market TEXT,
            market_type TEXT,
            line TEXT,
            selection TEXT,
            odds_bet REAL,
            model_prob REAL,
            ev REAL,
            kelly_pct REAL,
            stake REAL,
            result TEXT,
            profit REAL,
            bankroll REAL,
            notes TEXT,
            source_book TEXT NOT NULL DEFAULT 'sport pp88',
            source_file TEXT,
            run_id TEXT,
            odds_close REAL,
            clv_abs REAL,
            clv_pct REAL,
            created_at_utc TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_bet_log_bet_time ON bet_log (bet_time_hkt);
        CREATE INDEX IF NOT EXISTS idx_bet_log_league ON bet_log (league);
        CREATE INDEX IF NOT EXISTS idx_bet_log_market_type ON bet_log (market_type);
        CREATE INDEX IF NOT EXISTS idx_bet_log_bet_id ON bet_log (bet_id);
        """
    )
    conn.commit()


def _market_type_and_line(market: object, line: object) -> tuple[str, Optional[str]]:
    m = str(market or "").strip()
    ln = str(line or "").strip() or None
    lower = m.lower()

    if lower.replace(" ", "") == "1x2":
        return "1X2", ln

    ah = "asian handicap"
    ou = "over/under"
    if lower.startswith(ah):
        tail = m[len(ah) :].strip()
        if not ln and tail:
            ln = tail
        return "Asian Handicap", ln
    if lower.startswith(ou):
        tail = m[len(ou) :].strip()
        if not ln and tail:
            ln = tail
        return "Over/Under", ln

    return m or "(unknown)", ln


def append_recommendations_to_tracking_sqlite(
    reco_df: pd.DataFrame,
    sqlite_path: Path,
    source_book: str = "sport pp88",
    run_id: Optional[str] = None,
) -> int:
    """
    Optional append-only hook. Intended to be off by default.
    Writes only rows with bet_flag=True into tracking SQLite bet_log.
    """
    if reco_df.empty:
        return 0

    chosen = reco_df[reco_df.get("bet_flag", False) == True].copy()
    if chosen.empty:
        return 0

    now_hkt = datetime.now(timezone(timedelta(hours=8))).replace(microsecond=0)
    run_id = run_id or now_hkt.strftime("run_%Y%m%dT%H%M%S%z")

    rows = []
    for _, r in chosen.iterrows():
        market = r.get("market")
        line = r.get("line")
        market_type, line_norm = _market_type_and_line(market, line)

        bet_material = "|".join(
            [
                str(run_id),
                str(r.get("match_id", "")),
                str(r.get("selection", "")),
                str(r.get("odds", "")),
            ]
        )
        bet_id = hashlib.sha1(bet_material.encode("utf-8")).hexdigest()[:16]

        rows.append(
            {
                "bet_id": bet_id,
                "bet_time_hkt": now_hkt.isoformat(timespec="seconds"),
                "kickoff_time_hkt": None,
                "closing_time_hkt": None,
                "league": r.get("league") or None,
                "home": r.get("home_team") or None,
                "away": r.get("away_team") or None,
                "market": str(market or "") or None,
                "market_type": market_type,
                "line": line_norm,
                "selection": r.get("selection") or None,
                "odds_bet": pd.to_numeric(r.get("odds"), errors="coerce"),
                "model_prob": pd.to_numeric(r.get("model_probability"), errors="coerce"),
                "ev": pd.to_numeric(r.get("ev"), errors="coerce"),
                "kelly_pct": pd.to_numeric(r.get("bankroll_pct"), errors="coerce"),
                "stake": pd.to_numeric(r.get("suggested_stake"), errors="coerce"),
                "result": None,
                "profit": None,
                "bankroll": None,
                "notes": r.get("rationale") or None,
                "source_book": source_book,
                "source_file": "v2/reports/exporters.py:append_recommendations_to_tracking_sqlite",
                "run_id": run_id,
                "odds_close": None,
                "clv_abs": None,
                "clv_pct": None,
            }
        )

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sqlite_path))
    try:
        _ensure_tracking_schema(conn)
        conn.executemany(
            """
            INSERT INTO bet_log (
                bet_id, bet_time_hkt, kickoff_time_hkt, closing_time_hkt,
                league, home, away,
                market, market_type, line, selection,
                odds_bet, model_prob, ev, kelly_pct, stake,
                result, profit, bankroll,
                notes, source_book, source_file, run_id,
                odds_close, clv_abs, clv_pct
            ) VALUES (
                :bet_id, :bet_time_hkt, :kickoff_time_hkt, :closing_time_hkt,
                :league, :home, :away,
                :market, :market_type, :line, :selection,
                :odds_bet, :model_prob, :ev, :kelly_pct, :stake,
                :result, :profit, :bankroll,
                :notes, :source_book, :source_file, :run_id,
                :odds_close, :clv_abs, :clv_pct
            )
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()
