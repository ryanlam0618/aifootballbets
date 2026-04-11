from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import List, Tuple


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def _print_table(headers: List[str], rows: List[Tuple[object, ...]]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = "-+-".join("-" * widths[i] for i in range(len(headers)))
    print(line)
    print(sep)
    for row in rows:
        print(" | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))


def run_report(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                COUNT(*) AS bets,
                COALESCE(SUM(stake), 0) AS total_stake,
                COALESCE(SUM(profit), 0) AS total_profit,
                CASE WHEN COALESCE(SUM(stake),0)=0 THEN NULL ELSE SUM(profit)/SUM(stake) END AS roi,
                SUM(CASE WHEN lower(result)='win' THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN lower(result)='loss' THEN 1 ELSE 0 END) AS losses,
                SUM(CASE WHEN lower(result)='push' OR lower(result)='draw' THEN 1 ELSE 0 END) AS pushes
            FROM bet_log
            """
        )
        bets, total_stake, total_profit, roi, wins, losses, pushes = cur.fetchone()
        print("=== TOTALS ===")
        print(f"Bets: {bets}")
        print(f"Total Stake: {total_stake:.2f}")
        print(f"Total Profit: {total_profit:.2f}")
        print(f"ROI: {_pct(roi or 0.0)}")
        print(f"W/L/P: {wins}/{losses}/{pushes}")
        print()

        print("=== BY MARKET TYPE ===")
        cur.execute(
            """
            SELECT
                COALESCE(market_type, '(unknown)') AS market_type,
                COUNT(*) AS bets,
                ROUND(COALESCE(SUM(stake),0), 2) AS stake,
                ROUND(COALESCE(SUM(profit),0), 2) AS profit,
                ROUND(CASE WHEN COALESCE(SUM(stake),0)=0 THEN 0 ELSE (SUM(profit)/SUM(stake))*100 END, 2) AS roi_pct
            FROM bet_log
            GROUP BY COALESCE(market_type, '(unknown)')
            ORDER BY bets DESC
            """
        )
        rows = cur.fetchall()
        _print_table(["market_type", "bets", "stake", "profit", "roi%"], rows)
        print()

        print("=== BY LEAGUE ===")
        cur.execute(
            """
            SELECT
                COALESCE(league, '(unknown)') AS league,
                COUNT(*) AS bets,
                ROUND(COALESCE(SUM(stake),0), 2) AS stake,
                ROUND(COALESCE(SUM(profit),0), 2) AS profit,
                ROUND(CASE WHEN COALESCE(SUM(stake),0)=0 THEN 0 ELSE (SUM(profit)/SUM(stake))*100 END, 2) AS roi_pct
            FROM bet_log
            GROUP BY COALESCE(league, '(unknown)')
            ORDER BY bets DESC
            """
        )
        rows = cur.fetchall()
        _print_table(["league", "bets", "stake", "profit", "roi%"], rows)
        print()

        print("=== CALIBRATION (model_prob bins) ===")
        # Simple realized rate: win=1, loss=0, push/draw/other excluded
        cur.execute(
            """
            WITH b AS (
                SELECT
                    model_prob,
                    CASE
                        WHEN model_prob IS NULL THEN '(null)'
                        WHEN model_prob < 0.4 THEN '[0.0,0.4)'
                        WHEN model_prob < 0.5 THEN '[0.4,0.5)'
                        WHEN model_prob < 0.6 THEN '[0.5,0.6)'
                        WHEN model_prob < 0.7 THEN '[0.6,0.7)'
                        WHEN model_prob < 0.8 THEN '[0.7,0.8)'
                        ELSE '[0.8,1.0]'
                    END AS bin,
                    CASE
                        WHEN lower(result)='win' THEN 1.0
                        WHEN lower(result)='loss' THEN 0.0
                        ELSE NULL
                    END AS y
                FROM bet_log
            )
            SELECT
                bin,
                COUNT(*) AS n_all,
                SUM(CASE WHEN y IS NOT NULL THEN 1 ELSE 0 END) AS n_settled,
                ROUND(AVG(model_prob), 4) AS avg_model_prob,
                ROUND(AVG(y), 4) AS realized_win_rate
            FROM b
            GROUP BY bin
            ORDER BY
                CASE bin
                    WHEN '(null)' THEN 0
                    WHEN '[0.0,0.4)' THEN 1
                    WHEN '[0.4,0.5)' THEN 2
                    WHEN '[0.5,0.6)' THEN 3
                    WHEN '[0.6,0.7)' THEN 4
                    WHEN '[0.7,0.8)' THEN 5
                    WHEN '[0.8,1.0]' THEN 6
                    ELSE 99
                END
            """
        )
        rows = cur.fetchall()
        _print_table(["bin", "n_all", "n_settled", "avg_model_prob", "realized_win_rate"], rows)

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bet log report")
    parser.add_argument("--sqlite", default="data/v2/tracking/bets.sqlite", help="Path to sqlite db")
    args = parser.parse_args()
    db = Path(args.sqlite)
    if not db.exists():
        raise SystemExit(f"SQLite not found: {db}")
    run_report(db)


if __name__ == "__main__":
    main()
