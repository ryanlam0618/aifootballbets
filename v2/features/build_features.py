from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd



@dataclass
class TeamRecentSummary:
    team: str
    n_matches: int
    goals_for_avg: float
    goals_against_avg: float
    xg_for_avg: float
    xg_against_avg: float
    shots_on_target_avg: float
    possession_avg: float
    corners_avg: float
    ppda_avg: float
    rest_days: float
    matches_last_14d: int


def _safe_float(x, default=np.nan):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _team_recent(repo_df: pd.DataFrame, team: str, ref_date: pd.Timestamp, n: int = 10) -> TeamRecentSummary:
    df = repo_df.copy()
    df = df[df["date"].notna()]
    df = df[df["date"] < ref_date]

    h = df[df["home_team"].astype(str).str.lower() == team.lower()].copy()
    a = df[df["away_team"].astype(str).str.lower() == team.lower()].copy()

    h["is_home"] = 1
    a["is_home"] = 0

    h["goals_for"] = pd.to_numeric(h.get("home_goals"), errors="coerce")
    h["goals_against"] = pd.to_numeric(h.get("away_goals"), errors="coerce")
    a["goals_for"] = pd.to_numeric(a.get("away_goals"), errors="coerce")
    a["goals_against"] = pd.to_numeric(a.get("home_goals"), errors="coerce")

    # xG 欄位兼容
    xg_col = "xg" if "xg" in df.columns else ("xG" if "xG" in df.columns else None)
    xga_col = "xga" if "xga" in df.columns else ("xGA" if "xGA" in df.columns else None)

    if xg_col:
        h["xg_for"] = pd.to_numeric(h.get(xg_col), errors="coerce")
        a["xg_for"] = pd.to_numeric(a.get(xga_col if xga_col else xg_col), errors="coerce")
    else:
        h["xg_for"] = h["goals_for"]
        a["xg_for"] = a["goals_for"]

    if xga_col:
        h["xg_against"] = pd.to_numeric(h.get(xga_col), errors="coerce")
        a["xg_against"] = pd.to_numeric(a.get(xg_col if xg_col else xga_col), errors="coerce")
    else:
        h["xg_against"] = h["goals_against"]
        a["xg_against"] = a["goals_against"]

    all_games = pd.concat([h, a], ignore_index=True).sort_values("date").tail(n)

    # 14日賽程密度
    last_14 = all_games[all_games["date"] >= (ref_date - pd.Timedelta(days=14))]

    # 休息天數
    rest_days = np.nan
    if not all_games.empty:
        last_date = all_games["date"].max()
        rest_days = (ref_date - last_date).days

    def _mean_col(col: str):
        if col not in all_games.columns:
            return np.nan
        return float(pd.to_numeric(all_games[col], errors="coerce").mean())

    return TeamRecentSummary(
        team=team,
        n_matches=len(all_games),
        goals_for_avg=float(all_games["goals_for"].mean()) if len(all_games) else np.nan,
        goals_against_avg=float(all_games["goals_against"].mean()) if len(all_games) else np.nan,
        xg_for_avg=float(all_games["xg_for"].mean()) if len(all_games) else np.nan,
        xg_against_avg=float(all_games["xg_against"].mean()) if len(all_games) else np.nan,
        shots_on_target_avg=_mean_col("shots_on_target") if len(all_games) else np.nan,
        possession_avg=_mean_col("possession") if len(all_games) else np.nan,
        corners_avg=_mean_col("corners") if len(all_games) else np.nan,
        ppda_avg=_mean_col("ppda") if len(all_games) else np.nan,
        rest_days=float(rest_days) if rest_days == rest_days else np.nan,
        matches_last_14d=int(len(last_14)),
    )


def _odds_features(odds_24h: pd.DataFrame, match_id: str) -> dict:
    if odds_24h.empty:
        return {
            "opening_odds": np.nan,
            "latest_odds": np.nan,
            "odds_delta": np.nan,
            "history_insufficient": 1,
        }

    m = odds_24h[odds_24h["match_id"] == match_id].copy()
    if m.empty:
        return {
            "opening_odds": np.nan,
            "latest_odds": np.nan,
            "odds_delta": np.nan,
            "history_insufficient": 1,
        }

    m = m.sort_values("timestamp_utc")
    opening = m["decimal_odds"].iloc[0]
    latest = m["decimal_odds"].iloc[-1]
    return {
        "opening_odds": float(opening),
        "latest_odds": float(latest),
        "odds_delta": float(latest - opening),
        "history_insufficient": 0 if len(m) > 1 else 1,
    }


def _injury_features(injuries_df: pd.DataFrame, match_id: str) -> dict:
    if injuries_df.empty:
        return {"home_missing": 0, "away_missing": 0, "injury_diff": 0}

    m = injuries_df[injuries_df["match_id"] == match_id]
    home = len(m[m["team_side"] == "home"])
    away = len(m[m["team_side"] == "away"])
    return {"home_missing": home, "away_missing": away, "injury_diff": home - away}


def build_features(
    fixtures_df: pd.DataFrame,
    odds_24h_df: pd.DataFrame,
    injuries_df: pd.DataFrame,
    history_csv_path: str,
    out_csv: Path,
    sofascore_features_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    try:
        hist = pd.read_csv(history_csv_path)
    except Exception:
        hist = pd.DataFrame()

    if not hist.empty:
        # normalize date column for downstream filters
        date_col = None
        for c in ["date", "match_date", "Date", "datetime"]:
            if c in hist.columns:
                date_col = c
                break
        if date_col and date_col != "date":
            hist = hist.rename(columns={date_col: "date"})
        if "date" in hist.columns:
            hist["date"] = pd.to_datetime(hist["date"], errors="coerce")

    rows = []

    for _, fx in fixtures_df.iterrows():
        match_id = fx["match_id"]
        home = fx["home_team"]
        away = fx["away_team"]
        league = fx["league"]

        try:
            ref_date = pd.to_datetime(fx.get("match_date"), errors="coerce")
            if pd.isna(ref_date):
                ref_date = pd.Timestamp(datetime.utcnow())
        except Exception:
            ref_date = pd.Timestamp(datetime.utcnow())

        home5 = _team_recent(hist, home, ref_date, n=5) if not hist.empty else TeamRecentSummary(home, 0, *([np.nan] * 9), matches_last_14d=0)
        away5 = _team_recent(hist, away, ref_date, n=5) if not hist.empty else TeamRecentSummary(away, 0, *([np.nan] * 9), matches_last_14d=0)
        home10 = _team_recent(hist, home, ref_date, n=10) if not hist.empty else TeamRecentSummary(home, 0, *([np.nan] * 9), matches_last_14d=0)
        away10 = _team_recent(hist, away, ref_date, n=10) if not hist.empty else TeamRecentSummary(away, 0, *([np.nan] * 9), matches_last_14d=0)

        of = _odds_features(odds_24h_df, match_id)
        inf = _injury_features(injuries_df, match_id)

        # Optional SofaScore structured features (default zeros if missing)
        ss = {}
        if sofascore_features_df is not None and (not sofascore_features_df.empty) and ("match_id" in sofascore_features_df.columns):
            mss = sofascore_features_df[sofascore_features_df["match_id"] == match_id]
            if not mss.empty:
                ss = mss.iloc[0].to_dict()

        rows.append(
            {
                "match_id": match_id,
                "league": league,
                "match_date": fx.get("match_date"),
                "match_time": fx.get("match_time"),
                "home_team": home,
                "away_team": away,
                "is_home_tag": 1,
                # 歷史/結果特徵
                "home_goals_avg_5": home5.goals_for_avg,
                "away_goals_avg_5": away5.goals_for_avg,
                "home_goals_against_avg_5": home5.goals_against_avg,
                "away_goals_against_avg_5": away5.goals_against_avg,
                "goal_diff_5": _safe_float(home5.goals_for_avg) - _safe_float(away5.goals_for_avg),
                # xG/xA/射門
                "home_xg_avg_5": home5.xg_for_avg,
                "away_xg_avg_5": away5.xg_for_avg,
                "home_xga_avg_5": home5.xg_against_avg,
                "away_xga_avg_5": away5.xg_against_avg,
                "home_xa_avg_5": np.nan,
                "away_xa_avg_5": np.nan,
                "home_shots_on_target_avg_5": home5.shots_on_target_avg,
                "away_shots_on_target_avg_5": away5.shots_on_target_avg,
                "shot_location_coords_available": 0,
                # 控球/傳球/PPDA
                "home_possession_avg_5": home5.possession_avg,
                "away_possession_avg_5": away5.possession_avg,
                "home_pass_accuracy_avg_5": np.nan,
                "away_pass_accuracy_avg_5": np.nan,
                "home_key_passes_avg_5": np.nan,
                "away_key_passes_avg_5": np.nan,
                "home_ppda_avg_5": home5.ppda_avg,
                "away_ppda_avg_5": away5.ppda_avg,
                # set-piece
                "home_corners_avg_5": home5.corners_avg,
                "away_corners_avg_5": away5.corners_avg,
                "home_free_kicks_avg_5": np.nan,
                "away_free_kicks_avg_5": np.nan,
                # 體能
                "home_matches_last_14d": home5.matches_last_14d,
                "away_matches_last_14d": away5.matches_last_14d,
                "home_rest_days": home5.rest_days,
                "away_rest_days": away5.rest_days,
                "home_flight_distance_km_14d": np.nan,
                "away_flight_distance_km_14d": np.nan,
                # 滾動平均
                "home_xg_avg_10": home10.xg_for_avg,
                "away_xg_avg_10": away10.xg_for_avg,
                "home_goals_avg_10": home10.goals_for_avg,
                "away_goals_avg_10": away10.goals_for_avg,
                # 市場
                "opening_odds": of["opening_odds"],
                "latest_odds": of["latest_odds"],
                "odds_delta": of["odds_delta"],
                "history_insufficient": of["history_insufficient"],
                # 陣容/傷停（傳統：injuries.csv）
                "home_missing_players": inf["home_missing"],
                "away_missing_players": inf["away_missing"],
                "lineup_change_proxy": inf["injury_diff"],

                # SofaScore（結構化；default off 時會係 0/NaN）
                "sofascore_lineup_confirmed": ss.get("lineup_confirmed"),
                "sofascore_home_missing_count": ss.get("home_missing_count", 0),
                "sofascore_away_missing_count": ss.get("away_missing_count", 0),
                "sofascore_home_doubtful_count": ss.get("home_doubtful_count", 0),
                "sofascore_away_doubtful_count": ss.get("away_doubtful_count", 0),
                "sofascore_home_missing_gk": ss.get("home_missing_gk", 0),
                "sofascore_home_missing_df": ss.get("home_missing_df", 0),
                "sofascore_home_missing_mf": ss.get("home_missing_mf", 0),
                "sofascore_home_missing_fw": ss.get("home_missing_fw", 0),
                "sofascore_away_missing_gk": ss.get("away_missing_gk", 0),
                "sofascore_away_missing_df": ss.get("away_missing_df", 0),
                "sofascore_away_missing_mf": ss.get("away_missing_mf", 0),
                "sofascore_away_missing_fw": ss.get("away_missing_fw", 0),
                # 評分系統相關必要佔位
                "home_elo": np.nan,
                "away_elo": np.nan,
                "opponent_rating": np.nan,
                "offseason_days": np.nan,
                "empty_stadium_flag": np.nan,
                # 相關性矩陣特徵占位
                "same_kickoff_bucket": np.nan,
                "portfolio_corr_proxy": np.nan,
            }
        )

    df = pd.DataFrame(rows)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    return df
