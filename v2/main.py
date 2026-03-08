from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pandas as pd
from openai import OpenAI

from config import settings
from v2.config import settings_v2
from v2.features.build_features import build_features
from v2.ingest.fixtures import fixtures_to_csv, parse_match_lines, resolve_fixtures
from v2.ingest.odds import (
    build_odds_24h_csv,
    collect_and_store_snapshot,
    current_market_snapshot,
    current_market_snapshot_by_teams,
)
from v2.ingest.team_news import (
    collect_lineup_and_injury,
    grok_research,
    injuries_to_csv,
    injury_rows,
    write_lineup_text,
)
from v2.models.predict import predict_markets
from v2.reports.exporters import (
    export_betting_records_xlsx,
    export_recommendations,
    export_summary_report,
)
from v2.risk.allocator import allocate_stakes
from v2.sync.google_drive import sync_outputs_local_gdrive, upload_with_service_account


def _read_matches_interactive() -> List[str]:
    print("請逐行輸入比賽（格式：league_key|Home vs Away；league_key 可省略）。")
    print("輸入空白行結束，例如：soccer_epl|Arsenal vs Chelsea")
    lines: List[str] = []
    while True:
        line = input("> ").strip()
        if not line:
            break
        lines.append(line)
    return lines


def _ask_bankroll(default_value: float) -> float:
    val = input(f"請輸入 bankroll（預設 {default_value}）: ").strip()
    if not val:
        return float(default_value)
    try:
        return float(val)
    except Exception:
        return float(default_value)


def _json_preview(df: pd.DataFrame, n: int = 3) -> str:
    if df.empty:
        return "[]"
    return df.head(n).to_json(orient="records", force_ascii=False)


def _refine_rationale_with_chatgpt(df: pd.DataFrame, bankroll: float) -> pd.DataFrame:
    if df.empty or not settings_v2.openai_api_key:
        return df

    client = OpenAI(base_url=settings_v2.api_base_url, api_key=settings_v2.openai_api_key)

    out = df.copy()
    best = (
        out[out["bet_flag"] == True]
        .sort_values(["match_id", "edge"], ascending=[True, False])
        .groupby("match_id", as_index=False)
        .head(1)
    )

    for _, r in best.iterrows():
        idx = r.name
        prompt = f"""
你是足球交易分析師。請用繁體中文（香港口語）簡短解釋以下投注，重點講：
1) 點解有 edge
2) 市場可能錯價位
3) 風險點（例如傷停/陣容不確定）

資料：
- 比賽：{r['home_team']} vs {r['away_team']}
- 市場：{r['market']} {r['line']} {r['selection']}
- odds={r['odds']}
- model_prob={r['model_probability']:.4f}
- implied_prob={r['implied_probability']:.4f}
- edge={r['edge']:.4f}
- ev={r['ev']:.4f}
- bankroll={bankroll}
- 建議下注={r.get('suggested_stake', 0):.2f}
""".strip()

        try:
            resp = client.chat.completions.create(
                model=settings_v2.model_gpt,
                messages=[
                    {"role": "system", "content": "Be concise and factual."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            txt = resp.choices[0].message.content if resp and resp.choices else ""
            if txt:
                out.at[idx, "rationale"] = txt.strip()
        except Exception:
            pass

    return out


def run(matches: List[str], bankroll: float | None, default_league_key: str = "soccer_epl") -> None:
    root = Path(__file__).resolve().parents[1]
    data_root = root / "data" / "v2"
    reports_root = root / "reports" / "v2"
    lineup_txt_dir = data_root / "lineup_texts"

    fixtures_csv = data_root / "fixtures_master.csv"
    odds_24h_csv = data_root / "odds_24h.csv"
    injuries_csv = data_root / "injuries.csv"
    features_csv = data_root / "features_master.csv"
    reco_csv = reports_root / "betting_recommendations.csv"
    records_xlsx = reports_root / "betting_records.xlsx"
    summary_md = reports_root / "summary_report.md"
    snapshot_db = data_root / "odds_snapshots.sqlite"

    # 1) fixture input + resolve
    reqs = parse_match_lines(matches, default_league_key=default_league_key)
    fixtures = resolve_fixtures(reqs)
    fixtures_df = fixtures_to_csv(fixtures, fixtures_csv)
    print(f"[OK] fixtures: {len(fixtures_df)} -> {fixtures_csv}")

    # 2) odds snapshots + 24h changes
    league_keys = sorted(set(fixtures_df["league_key"].tolist()))
    snap_df = collect_and_store_snapshot(league_keys, snapshot_db)
    print(f"[OK] snapshot rows: {len(snap_df)}")

    odds_24h_df = build_odds_24h_csv(fixtures_df["match_id"].astype(str).tolist(), snapshot_db, odds_24h_csv)
    print(f"[OK] odds 24h rows: {len(odds_24h_df)} -> {odds_24h_csv}")

    # 3) lineup + injuries + grok (T-60 gate)
    injury_all_rows = []
    for _, fx in fixtures_df.iterrows():
        match_id = str(fx["match_id"])
        home = fx["home_team"]
        away = fx["away_team"]
        match_date = str(fx.get("match_date"))

        payload = collect_lineup_and_injury(home, away, match_date)

        # T-60 gate
        grok_text = "[Skipped] Not in T-60 window"
        try:
            kickoff = datetime.fromisoformat(str(fx.get("commence_time_utc")).replace("Z", "+00:00"))
        except Exception:
            kickoff = datetime.now(timezone.utc)
        now = datetime.now(timezone.utc)
        if now >= (kickoff - timedelta(hours=1)):
            grok_text = grok_research(home, away, match_date)

        write_lineup_text(match_id, home, away, payload, grok_text, lineup_txt_dir)
        injury_all_rows.extend(injury_rows(match_id, home, away, payload.get("injury") or {}))

    injuries_df = injuries_to_csv(injury_all_rows, injuries_csv)
    print(f"[OK] injuries rows: {len(injuries_df)} -> {injuries_csv}")

    # 4) features
    features_df = build_features(
        fixtures_df=fixtures_df,
        odds_24h_df=odds_24h_df,
        injuries_df=injuries_df,
        history_csv_path=settings.HISTORY_CSV_PATH,
        out_csv=features_csv,
    )
    print(f"[OK] features: {len(features_df)} -> {features_csv}")

    # 5) model prediction
    market_odds = current_market_snapshot(fixtures_df["match_id"].astype(str).tolist(), snapshot_db)
    if not market_odds:
        market_odds = current_market_snapshot_by_teams(fixtures_df, snapshot_db)

    pred_df = predict_markets(features_df, market_odds)

    if pred_df.empty:
        print("[WARN] No prediction rows generated (check odds snapshot coverage).")
        pred_df = pd.DataFrame(
            [
                {
                    "match_id": r["match_id"],
                    "league": r["league"],
                    "home_team": r["home_team"],
                    "away_team": r["away_team"],
                    "market": "No Bet",
                    "line": "",
                    "selection": "None",
                    "odds": "",
                    "model_probability": 0,
                    "implied_probability": 0,
                    "edge": 0,
                    "ev": 0,
                    "confidence": "Low",
                    "rationale": "市場數據不足",
                    "expected_value_assessment": "Neutral",
                    "bet_flag": False,
                    "suggested_stake": 0,
                    "bankroll_pct": 0,
                }
                for _, r in fixtures_df.iterrows()
            ]
        )

    # bankroll stage (as requested)
    if bankroll is None:
        bankroll = _ask_bankroll(settings_v2.initial_bankroll)

    alloc_df = allocate_stakes(pred_df, bankroll=bankroll)

    # data quality score
    quality_base = features_df.copy()
    if not quality_base.empty:
        completeness = 1 - quality_base.isna().mean(axis=1)
        qmap = dict(zip(quality_base["match_id"], completeness))
        alloc_df["data_quality_score"] = alloc_df["match_id"].map(qmap).fillna(0).round(3)
    else:
        alloc_df["data_quality_score"] = 0

    # optional final LLM rationale refinement
    alloc_df = _refine_rationale_with_chatgpt(alloc_df, bankroll)

    # 6) reports
    reco_out = export_recommendations(alloc_df, reco_csv)
    records_df = export_betting_records_xlsx(reco_out, records_xlsx)
    export_summary_report(reco_out, records_df, summary_md)
    print(f"[OK] reports: {reco_csv}, {records_xlsx}, {summary_md}")

    # 7) sync
    outputs = [reco_csv, records_xlsx, summary_md]
    local_sync = sync_outputs_local_gdrive(outputs)
    drive_upload = upload_with_service_account(outputs)

    print("\n=== DONE ===")
    print(f"fixtures_master.csv: {fixtures_csv}")
    print(f"odds_24h.csv: {odds_24h_csv}")
    print(f"features_master.csv: {features_csv}")
    print(f"betting_recommendations.csv: {reco_csv}")
    print(f"betting_records.xlsx: {records_xlsx}")
    print(f"summary_report.md: {summary_md}")
    if local_sync:
        print(f"local GDrive sync: {local_sync}")
    if drive_upload:
        print(f"Drive upload IDs: {drive_upload}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ai_fb_bets v2 pipeline")
    parser.add_argument("--matches", nargs="*", default=None, help="Match lines, e.g. soccer_epl|Arsenal vs Chelsea")
    parser.add_argument("--bankroll", type=float, default=None)
    parser.add_argument("--league", type=str, default="soccer_epl", help="default league key")
    args = parser.parse_args()

    matches = args.matches or _read_matches_interactive()
    if not matches:
        raise SystemExit("No matches provided.")

    run(matches=matches, bankroll=args.bankroll, default_league_key=args.league)


if __name__ == "__main__":
    main()
