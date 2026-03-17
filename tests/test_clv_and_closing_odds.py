import sqlite3
import tempfile
import unittest
from pathlib import Path

from v2.paper.closing_odds import load_tracker_closing_odds_by_bet_id
from v2.paper.clv import compute_clv


class TestClvAndClosingOdds(unittest.TestCase):
    def test_compute_clv(self):
        c_abs, c_pct = compute_clv(odds_bet=2.0, odds_close=2.1)
        self.assertAlmostEqual(c_abs, 0.1, places=9)
        self.assertAlmostEqual(c_pct, 5.0, places=9)

    def test_tracker_hook_maps_closing_odds_by_bet_id(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "odds_tracker.sqlite"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.executescript(
                    """
                    CREATE TABLE odds_match (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        match_url TEXT NOT NULL,
                        market TEXT NOT NULL DEFAULT '1X2',
                        label TEXT
                    );
                    CREATE TABLE odds_snapshot (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        match_id INTEGER NOT NULL,
                        snapshot_ts_utc TEXT NOT NULL,
                        success INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE TABLE odds_quote (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        snapshot_id INTEGER NOT NULL,
                        bookmaker TEXT NOT NULL,
                        market_type TEXT NOT NULL DEFAULT '1X2',
                        line REAL,
                        home REAL,
                        draw REAL,
                        away REAL
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO odds_match(id, match_url, market, label) VALUES (1, ?, '1X2', ?)",
                    (
                        "https://www.oddsportal.com/football/england/premier-league/arsenal-chelsea-abc123/",
                        "Arsenal vs Chelsea",
                    ),
                )
                conn.execute(
                    "INSERT INTO odds_snapshot(id, match_id, snapshot_ts_utc, success) VALUES (10, 1, '2026-03-16T11:00:00+00:00', 1)"
                )
                conn.execute(
                    "INSERT INTO odds_quote(snapshot_id, bookmaker, market_type, line, home, draw, away) VALUES (10, 'book', '1X2', NULL, 2.25, 3.20, 3.10)"
                )
                conn.commit()
            finally:
                conn.close()

            unsettled_rows = [
                {
                    "bet_id": "b1",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "market": "1X2",
                    "line": "",
                    "selection": "Home",
                    "kickoff_time_hkt": "2026-03-16T22:00:00+08:00",
                }
            ]

            mapped = load_tracker_closing_odds_by_bet_id(db_path, unsettled_rows)
            self.assertIn("b1", mapped)
            self.assertAlmostEqual(mapped["b1"], 2.25, places=9)


if __name__ == "__main__":
    unittest.main()
