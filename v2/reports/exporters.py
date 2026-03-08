from __future__ import annotations

from pathlib import Path
from typing import Dict

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
