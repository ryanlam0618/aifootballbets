from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from v2.config import settings_v2
from v2.paper.ledger import bankroll_before_day


def _to_float(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _query_daily(conn: sqlite3.Connection, day: date):
    return conn.execute(
        """
        SELECT
          COUNT(*) AS bets,
          COALESCE(SUM(stake), 0) AS stake,
          COALESCE(SUM(CASE WHEN profit IS NULL THEN 0 ELSE profit END), 0) AS profit,
          SUM(CASE WHEN lower(COALESCE(result,''))='win' THEN 1 ELSE 0 END) AS wins,
          SUM(CASE WHEN lower(COALESCE(result,''))='loss' THEN 1 ELSE 0 END) AS losses,
          SUM(CASE WHEN lower(COALESCE(result,''))='push' THEN 1 ELSE 0 END) AS pushes
        FROM bet_log
        WHERE substr(kickoff_time_hkt, 1, 10) = ?
        """,
        (day.isoformat(),),
    ).fetchone()


def _query_source_split(conn: sqlite3.Connection, start: date, end: date):
    return conn.execute(
        """
        SELECT
          COALESCE(source_quality, 'synthetic_odds') AS source_quality,
          COUNT(*) AS bets,
          COALESCE(SUM(stake), 0) AS stake,
          COALESCE(SUM(CASE WHEN profit IS NULL THEN 0 ELSE profit END), 0) AS profit,
          SUM(CASE WHEN lower(COALESCE(result,''))='win' THEN 1 ELSE 0 END) AS wins,
          SUM(CASE WHEN lower(COALESCE(result,''))='loss' THEN 1 ELSE 0 END) AS losses,
          SUM(CASE WHEN lower(COALESCE(result,''))='push' THEN 1 ELSE 0 END) AS pushes
        FROM bet_log
        WHERE substr(kickoff_time_hkt, 1, 10) BETWEEN ? AND ?
        GROUP BY COALESCE(source_quality, 'synthetic_odds')
        ORDER BY source_quality
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()


def _query_clv_source_split(conn: sqlite3.Connection, start: date, end: date):
    return conn.execute(
        """
        SELECT
          COALESCE(source_quality, 'synthetic_odds') AS source_quality,
          SUM(CASE WHEN odds_close IS NOT NULL THEN 1 ELSE 0 END) AS clv_sample_size,
          COALESCE(AVG(CASE WHEN odds_close IS NOT NULL THEN clv_abs ELSE NULL END), 0) AS avg_clv_abs,
          COALESCE(AVG(CASE WHEN odds_close IS NOT NULL THEN clv_pct ELSE NULL END), 0) AS avg_clv_pct
        FROM bet_log
        WHERE substr(kickoff_time_hkt, 1, 10) BETWEEN ? AND ?
        GROUP BY COALESCE(source_quality, 'synthetic_odds')
        ORDER BY source_quality
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()


def summarize_window_metrics(db_path: Path, start: date, end: date, initial_bankroll: float) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS bets,
              COALESCE(SUM(stake), 0) AS stake,
              COALESCE(SUM(CASE WHEN profit IS NULL THEN 0 ELSE profit END), 0) AS profit,
              SUM(CASE WHEN lower(COALESCE(result,''))='win' THEN 1 ELSE 0 END) AS wins,
              SUM(CASE WHEN lower(COALESCE(result,''))='loss' THEN 1 ELSE 0 END) AS losses,
              SUM(CASE WHEN lower(COALESCE(result,''))='push' THEN 1 ELSE 0 END) AS pushes,
              COALESCE(AVG(model_prob - CASE WHEN odds_bet > 0 THEN (1.0 / odds_bet) ELSE 0 END), 0) AS avg_edge,
              COALESCE(AVG(CASE WHEN odds_close IS NOT NULL THEN clv_abs ELSE NULL END), 0) AS avg_clv_abs,
              COALESCE(AVG(CASE WHEN odds_close IS NOT NULL THEN clv_pct ELSE NULL END), 0) AS avg_clv_pct,
              SUM(CASE WHEN odds_close IS NOT NULL THEN 1 ELSE 0 END) AS clv_sample_size
            FROM bet_log
            WHERE substr(kickoff_time_hkt, 1, 10) BETWEEN ? AND ?
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchone()

        bets = int(row[0] or 0)
        stake = _to_float(row[1])
        pnl = _to_float(row[2])
        wins = int(row[3] or 0)
        losses = int(row[4] or 0)
        pushes = int(row[5] or 0)
        avg_edge = _to_float(row[6])
        avg_clv_abs = _to_float(row[7])
        avg_clv_pct = _to_float(row[8])
        clv_sample_size = int(row[9] or 0)
        clv_coverage_pct = (clv_sample_size / bets) * 100.0 if bets > 0 else 0.0

        roi_pct = (pnl / stake) * 100.0 if stake > 0 else 0.0
        winrate_pct = (wins / bets) * 100.0 if bets > 0 else 0.0

        rows_daily = conn.execute(
            """
            SELECT substr(kickoff_time_hkt, 1, 10) AS day,
                   COALESCE(SUM(CASE WHEN profit IS NULL THEN 0 ELSE profit END), 0) AS profit
            FROM bet_log
            WHERE substr(kickoff_time_hkt, 1, 10) BETWEEN ? AND ?
            GROUP BY substr(kickoff_time_hkt, 1, 10)
            ORDER BY day ASC
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        equity = float(initial_bankroll)
        peak = equity
        max_drawdown_pct = 0.0
        for _d, dprofit in rows_daily:
            equity += _to_float(dprofit)
            if equity > peak:
                peak = equity
            if peak > 0:
                dd = ((peak - equity) / peak) * 100.0
                if dd > max_drawdown_pct:
                    max_drawdown_pct = dd

        ending_bankroll = initial_bankroll + pnl

        market_rows = conn.execute(
            """
            SELECT
              COALESCE(market_type, 'UNKNOWN') AS market_type,
              COUNT(*) AS bets,
              COALESCE(SUM(stake), 0) AS stake,
              COALESCE(SUM(CASE WHEN profit IS NULL THEN 0 ELSE profit END), 0) AS profit,
              SUM(CASE WHEN lower(COALESCE(result,''))='win' THEN 1 ELSE 0 END) AS wins,
              COALESCE(AVG(model_prob - CASE WHEN odds_bet > 0 THEN (1.0 / odds_bet) ELSE 0 END), 0) AS avg_edge
            FROM bet_log
            WHERE substr(kickoff_time_hkt, 1, 10) BETWEEN ? AND ?
            GROUP BY COALESCE(market_type, 'UNKNOWN')
            ORDER BY market_type
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        by_market = []
        for r in market_rows:
            m_bets = int(r[1] or 0)
            m_stake = _to_float(r[2])
            m_pnl = _to_float(r[3])
            m_wins = int(r[4] or 0)
            m_avg_edge = _to_float(r[5])
            by_market.append(
                {
                    "market_type": str(r[0]),
                    "bets": m_bets,
                    "pnl": m_pnl,
                    "roi_pct": (m_pnl / m_stake) * 100.0 if m_stake > 0 else 0.0,
                    "winrate_pct": (m_wins / m_bets) * 100.0 if m_bets > 0 else 0.0,
                    "avg_edge_pct": m_avg_edge * 100.0,
                }
            )

        clv_source_rows = _query_clv_source_split(conn, start, end)
        clv_by_source_quality = []
        for r in clv_source_rows:
            clv_by_source_quality.append(
                {
                    "source_quality": str(r[0]),
                    "clv_sample_size": int(r[1] or 0),
                    "avg_clv_abs": _to_float(r[2]),
                    "avg_clv_pct": _to_float(r[3]),
                }
            )

        # Baseline: flat stake fraction per bet against starting bankroll.
        flat_frac = max(0.0, float(settings_v2.paper_flat_stake_fraction))
        flat_stake = initial_bankroll * flat_frac
        if flat_stake <= 0:
            baseline_pnl = 0.0
            baseline_total_stake = 0.0
        else:
            baseline = conn.execute(
                """
                SELECT
                  COALESCE(SUM(
                    CASE
                      WHEN lower(COALESCE(result,''))='win' THEN (? * (odds_bet - 1.0))
                      WHEN lower(COALESCE(result,''))='loss' THEN (-?)
                      ELSE 0
                    END
                  ), 0) AS pnl,
                  COUNT(*) AS bets
                FROM bet_log
                WHERE substr(kickoff_time_hkt, 1, 10) BETWEEN ? AND ?
                """,
                (flat_stake, flat_stake, start.isoformat(), end.isoformat()),
            ).fetchone()
            baseline_pnl = _to_float(baseline[0])
            baseline_bets = int(baseline[1] or 0)
            baseline_total_stake = baseline_bets * flat_stake

        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "bets": bets,
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "stake": stake,
            "pnl": pnl,
            "roi_pct": roi_pct,
            "winrate_pct": winrate_pct,
            "avg_edge_pct": avg_edge * 100.0,
            "avg_clv_abs": avg_clv_abs,
            "avg_clv_pct": avg_clv_pct,
            "clv_sample_size": clv_sample_size,
            "clv_coverage_pct": clv_coverage_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "starting_bankroll": float(initial_bankroll),
            "ending_bankroll": ending_bankroll,
            "by_market": by_market,
            "clv_by_source_quality": clv_by_source_quality,
            "baseline_flat": {
                "stake_per_bet": flat_stake,
                "total_stake": baseline_total_stake,
                "pnl": baseline_pnl,
                "roi_pct": (baseline_pnl / baseline_total_stake) * 100.0 if baseline_total_stake > 0 else 0.0,
            },
        }
    finally:
        conn.close()


def generate_reports(db_path: Path, day: date, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    daily_path = out_dir / f"paper_daily_{day.isoformat()}.md"
    weekly_path = out_dir / f"paper_weekly_{day.isoformat()}.md"

    conn = sqlite3.connect(str(db_path))
    try:
        d = _query_daily(conn, day)
        bets = int(d[0] or 0)
        stake = _to_float(d[1])
        profit = _to_float(d[2])
        roi = (profit / stake) if stake > 0 else 0.0

        day_start_bankroll = bankroll_before_day(db_path, day, settings_v2.initial_bankroll)
        bankroll_after = day_start_bankroll + profit
        stop_loss_pct = max(0.0, float(settings_v2.paper_daily_stop_loss_pct))
        stop_loss_triggered = profit <= (-stop_loss_pct * day_start_bankroll)

        source_rows_daily = _query_source_split(conn, day, day)
        source_lines_daily = []
        for row in source_rows_daily:
            sq = str(row[0])
            sbets = int(row[1] or 0)
            sstake = _to_float(row[2])
            sprofit = _to_float(row[3])
            sroi = (sprofit / sstake) if sstake > 0 else 0.0
            sw = int(row[4] or 0)
            sl = int(row[5] or 0)
            sp = int(row[6] or 0)
            source_lines_daily.append(
                f"  - {sq}: bets={sbets}, stake={sstake:.2f}, profit={sprofit:.2f}, roi={sroi * 100:.2f}%, W/L/P={sw}/{sl}/{sp}"
            )

        daily_md = (
            f"# Paper Daily Report ({day.isoformat()})\n\n"
            f"- Bets: {bets}\n"
            f"- Stake: {stake:.2f}\n"
            f"- Profit (PnL): {profit:.2f}\n"
            f"- ROI: {roi * 100:.2f}%\n"
            f"- Bankroll (start -> end): {day_start_bankroll:.2f} -> {bankroll_after:.2f}\n"
            f"- Stop-loss triggered ({stop_loss_pct * 100:.0f}%): {'YES' if stop_loss_triggered else 'NO'}\n"
            f"- W/L/P: {int(d[3] or 0)}/{int(d[4] or 0)}/{int(d[5] or 0)}\n"
            f"\n## By source_quality\n"
            + ("\n".join(source_lines_daily) if source_lines_daily else "- (no bets)")
            + "\n"
        )
        daily_path.write_text(daily_md, encoding="utf-8")

        start = day - timedelta(days=6)
        w = conn.execute(
            """
            SELECT
              COUNT(*) AS bets,
              COALESCE(SUM(stake), 0) AS stake,
              COALESCE(SUM(CASE WHEN profit IS NULL THEN 0 ELSE profit END), 0) AS profit,
              SUM(CASE WHEN lower(COALESCE(result,''))='win' THEN 1 ELSE 0 END) AS wins,
              SUM(CASE WHEN lower(COALESCE(result,''))='loss' THEN 1 ELSE 0 END) AS losses,
              SUM(CASE WHEN lower(COALESCE(result,''))='push' THEN 1 ELSE 0 END) AS pushes
            FROM bet_log
            WHERE substr(kickoff_time_hkt, 1, 10) BETWEEN ? AND ?
            """,
            (start.isoformat(), day.isoformat()),
        ).fetchone()

        w_stake = _to_float(w[1])
        w_profit = _to_float(w[2])
        w_roi = (w_profit / w_stake) if w_stake > 0 else 0.0

        source_rows_weekly = _query_source_split(conn, start, day)
        source_lines_weekly = []
        for row in source_rows_weekly:
            sq = str(row[0])
            sbets = int(row[1] or 0)
            sstake = _to_float(row[2])
            sprofit = _to_float(row[3])
            sroi = (sprofit / sstake) if sstake > 0 else 0.0
            sw = int(row[4] or 0)
            sl = int(row[5] or 0)
            sp = int(row[6] or 0)
            source_lines_weekly.append(
                f"  - {sq}: bets={sbets}, stake={sstake:.2f}, profit={sprofit:.2f}, roi={sroi * 100:.2f}%, W/L/P={sw}/{sl}/{sp}"
            )

        summary = summarize_window_metrics(
            db_path=db_path,
            start=start,
            end=day,
            initial_bankroll=float(settings_v2.initial_bankroll),
        )

        weekly_md = (
            f"# Paper Weekly Report ({start.isoformat()} -> {day.isoformat()})\n\n"
            f"- Bets: {int(w[0] or 0)}\n"
            f"- Stake: {w_stake:.2f}\n"
            f"- Profit: {w_profit:.2f}\n"
            f"- ROI: {w_roi * 100:.2f}%\n"
            f"- W/L/P: {int(w[3] or 0)}/{int(w[4] or 0)}/{int(w[5] or 0)}\n"
            f"- Max drawdown: {summary['max_drawdown_pct']:.2f}%\n"
            f"- Winrate: {summary['winrate_pct']:.2f}%\n"
            f"- Avg edge: {summary['avg_edge_pct']:.2f}%\n"
            f"- CLV sample size: {summary['clv_sample_size']}\n"
            f"- Avg CLV (abs): {summary['avg_clv_abs']:.4f}\n"
            f"- Avg CLV (%): {summary['avg_clv_pct']:.2f}%\n"
            f"\n## Baseline comparison\n"
            f"- Kelly-fraction PnL: {summary['pnl']:.2f}\n"
            f"- Flat-stake PnL: {summary['baseline_flat']['pnl']:.2f}\n"
            f"- Flat-stake ROI: {summary['baseline_flat']['roi_pct']:.2f}%\n"
            f"\n## By market type\n"
            + ("\n".join(
                [
                    f"  - {m['market_type']}: bets={m['bets']}, pnl={m['pnl']:.2f}, roi={m['roi_pct']:.2f}%, winrate={m['winrate_pct']:.2f}%, avg_edge={m['avg_edge_pct']:.2f}%"
                    for m in summary["by_market"]
                ]
            ) if summary["by_market"] else "- (no bets)")
            + "\n"
            f"\n## By source_quality\n"
            + ("\n".join(source_lines_weekly) if source_lines_weekly else "- (no bets)")
            + "\n"
        )
        weekly_path.write_text(weekly_md, encoding="utf-8")
    finally:
        conn.close()

    return daily_path, weekly_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate paper trading daily/weekly reports")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--sqlite", required=True)
    parser.add_argument("--out-dir", default="reports/v2")
    args = parser.parse_args()

    day = datetime.strptime(args.date, "%Y-%m-%d").date()
    daily, weekly = generate_reports(Path(args.sqlite), day, Path(args.out_dir))
    print(f"[OK] daily report: {daily}")
    print(f"[OK] weekly report: {weekly}")


if __name__ == "__main__":
    main()
