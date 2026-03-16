from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def _print_table(headers, rows):
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


def report_for_match(conn: sqlite3.Connection, match_id: int, label: str) -> None:
    print(f"\n=== MATCH: {label} (id={match_id}) ===")

    totals = conn.execute(
        """
        SELECT
            COUNT(*) AS snapshots,
            SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS ok_snapshots,
            SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failed_snapshots,
            COALESCE(SUM(quote_count),0) AS total_quotes,
            MIN(snapshot_ts_utc) AS first_ts,
            MAX(snapshot_ts_utc) AS last_ts
        FROM odds_snapshot
        WHERE match_id = ?
        """,
        (match_id,),
    ).fetchone()
    print(
        f"snapshots={totals[0]} ok={totals[1]} failed={totals[2]} quotes={totals[3]} "
        f"window=[{totals[4]} -> {totals[5]}]"
    )

    print("\n-- odds movement per bookmaker (first -> last, delta) --")
    rows = conn.execute(
        """
        WITH ordered AS (
            SELECT
                q.bookmaker,
                s.snapshot_ts_utc,
                q.home,
                q.draw,
                q.away,
                ROW_NUMBER() OVER (PARTITION BY q.bookmaker ORDER BY s.snapshot_ts_utc ASC) AS rn_first,
                ROW_NUMBER() OVER (PARTITION BY q.bookmaker ORDER BY s.snapshot_ts_utc DESC) AS rn_last,
                COUNT(*) OVER (PARTITION BY q.bookmaker) AS n
            FROM odds_quote q
            JOIN odds_snapshot s ON s.id = q.snapshot_id
            WHERE s.match_id = ?
        ),
        first_last AS (
            SELECT
                f.bookmaker,
                f.home AS first_home,
                l.home AS last_home,
                f.draw AS first_draw,
                l.draw AS last_draw,
                f.away AS first_away,
                l.away AS last_away,
                l.n AS samples
            FROM ordered f
            JOIN ordered l
              ON l.bookmaker = f.bookmaker
             AND f.rn_first = 1
             AND l.rn_last = 1
        )
        SELECT
            bookmaker,
            samples,
            ROUND(first_home, 3), ROUND(last_home, 3), ROUND(last_home - first_home, 3),
            ROUND(first_draw, 3), ROUND(last_draw, 3), ROUND(last_draw - first_draw, 3),
            ROUND(first_away, 3), ROUND(last_away, 3), ROUND(last_away - first_away, 3)
        FROM first_last
        ORDER BY bookmaker
        """,
        (match_id,),
    ).fetchall()
    _print_table(
        [
            "bookmaker",
            "samples",
            "h_first",
            "h_last",
            "h_delta",
            "d_first",
            "d_last",
            "d_delta",
            "a_first",
            "a_last",
            "a_delta",
        ],
        rows,
    )

    print("\n-- best available odds over time --")
    best_rows = conn.execute(
        """
        SELECT
            s.snapshot_ts_utc,
            ROUND(MAX(q.home), 3) AS best_home,
            ROUND(MAX(q.draw), 3) AS best_draw,
            ROUND(MAX(q.away), 3) AS best_away,
            COUNT(q.bookmaker) AS bookmakers
        FROM odds_snapshot s
        LEFT JOIN odds_quote q ON q.snapshot_id = s.id
        WHERE s.match_id = ?
        GROUP BY s.id, s.snapshot_ts_utc
        ORDER BY s.snapshot_ts_utc
        """,
        (match_id,),
    ).fetchall()
    _print_table(["snapshot_ts_utc", "best_home", "best_draw", "best_away", "bookmakers"], best_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Report odds movement from odds_tracker sqlite")
    parser.add_argument("--sqlite", default="data/v2/tracking/odds_tracker.sqlite", help="Path to tracker sqlite")
    parser.add_argument("--match-id", type=int, default=0, help="Optional match id; 0 means all")
    args = parser.parse_args()

    db = Path(args.sqlite)
    if not db.exists():
        raise SystemExit(f"SQLite not found: {db}")

    conn = sqlite3.connect(str(db))
    try:
        if args.match_id:
            row = conn.execute("SELECT id, COALESCE(label, match_url), market FROM odds_match WHERE id = ?", (args.match_id,)).fetchone()
            if not row:
                raise SystemExit(f"No odds_match with id={args.match_id}")
            report_for_match(conn, row[0], f"{row[1]} [{row[2]}]")
            return

        matches = conn.execute(
            "SELECT id, COALESCE(label, match_url), market FROM odds_match ORDER BY id"
        ).fetchall()
        if not matches:
            print("No tracked matches found.")
            return

        for row in matches:
            report_for_match(conn, row[0], f"{row[1]} [{row[2]}]")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
