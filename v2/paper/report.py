from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path


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


def generate_reports(db_path: Path, day: date, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    daily_path = out_dir / f"paper_daily_{day.isoformat()}.md"
    weekly_path = out_dir / f"paper_weekly_{day.isoformat()}.md"

    conn = sqlite3.connect(str(db_path))
    try:
        d = _query_daily(conn, day)
        stake = _to_float(d[1])
        profit = _to_float(d[2])
        roi = (profit / stake) if stake > 0 else 0.0

        daily_md = (
            f"# Paper Daily Report ({day.isoformat()})\n\n"
            f"- Bets: {int(d[0] or 0)}\n"
            f"- Stake: {stake:.2f}\n"
            f"- Profit: {profit:.2f}\n"
            f"- ROI: {roi * 100:.2f}%\n"
            f"- W/L/P: {int(d[3] or 0)}/{int(d[4] or 0)}/{int(d[5] or 0)}\n"
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

        weekly_md = (
            f"# Paper Weekly Report ({start.isoformat()} -> {day.isoformat()})\n\n"
            f"- Bets: {int(w[0] or 0)}\n"
            f"- Stake: {w_stake:.2f}\n"
            f"- Profit: {w_profit:.2f}\n"
            f"- ROI: {w_roi * 100:.2f}%\n"
            f"- W/L/P: {int(w[3] or 0)}/{int(w[4] or 0)}/{int(w[5] or 0)}\n"
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
