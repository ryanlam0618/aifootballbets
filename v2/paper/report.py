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
        stop_loss_triggered = profit <= (-0.20 * day_start_bankroll)

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
            f"- Stop-loss triggered (20%): {'YES' if stop_loss_triggered else 'NO'}\n"
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

        weekly_md = (
            f"# Paper Weekly Report ({start.isoformat()} -> {day.isoformat()})\n\n"
            f"- Bets: {int(w[0] or 0)}\n"
            f"- Stake: {w_stake:.2f}\n"
            f"- Profit: {w_profit:.2f}\n"
            f"- ROI: {w_roi * 100:.2f}%\n"
            f"- W/L/P: {int(w[3] or 0)}/{int(w[4] or 0)}/{int(w[5] or 0)}\n"
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
