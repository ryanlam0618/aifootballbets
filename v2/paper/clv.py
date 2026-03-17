from __future__ import annotations


def compute_clv(odds_bet: float, odds_close: float) -> tuple[float, float]:
    """
    Returns (clv_abs, clv_pct).

    clv_abs = odds_close - odds_bet
    clv_pct = clv_abs / odds_bet * 100
    """
    ob = float(odds_bet)
    oc = float(odds_close)
    if ob <= 0:
        return 0.0, 0.0
    clv_abs = oc - ob
    clv_pct = (clv_abs / ob) * 100.0
    return clv_abs, clv_pct
