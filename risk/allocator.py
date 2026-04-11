from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd

from config import settings_v2


@dataclass
class StakePlan:
    idx: int
    suggested_stake: float
    bankroll_pct: float


def _kelly_fraction(prob: float, odds: float) -> float:
    if odds <= 1:
        return 0.0
    b = odds - 1
    q = 1 - prob
    k = (b * prob - q) / b
    return max(0.0, k)


def allocate_stakes(
    picks_df: pd.DataFrame,
    bankroll: float,
    min_edge: float | None = None,
    kelly_fraction: float | None = None,
) -> pd.DataFrame:
    if picks_df.empty:
        return picks_df

    edge_cut = settings_v2.min_edge if min_edge is None else min_edge
    k_frac = settings_v2.kelly_fraction if kelly_fraction is None else kelly_fraction

    df = picks_df.copy()
    df["bet_flag"] = (df["edge"] >= edge_cut) & (df["ev"] > 0)

    stakes = []
    for idx, row in df.iterrows():
        if not row["bet_flag"]:
            stakes.append(StakePlan(idx, 0.0, 0.0))
            continue
        k = _kelly_fraction(float(row["model_probability"]), float(row.get("odds", row.get("decimal_odds", 0)) or 0))
        k_adj = k * k_frac
        stake = bankroll * k_adj
        stakes.append(StakePlan(idx, float(stake), float(k_adj)))

    stake_df = pd.DataFrame([s.__dict__ for s in stakes]).set_index("idx")
    for col in ["suggested_stake", "bankroll_pct"]:
        df[col] = 0.0
        if not stake_df.empty:
            df.loc[stake_df.index, col] = stake_df[col]

    # 簡單 Portfolio 收縮：同一時間窗下注總比例 cap 40%
    total_pct = df["bankroll_pct"].sum()
    if total_pct > 0.4:
        shrink = 0.4 / total_pct
        df["bankroll_pct"] = df["bankroll_pct"] * shrink
        df["suggested_stake"] = df["suggested_stake"] * shrink

    return df
