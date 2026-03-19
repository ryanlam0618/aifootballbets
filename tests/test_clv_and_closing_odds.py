import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from v2.paper.closing_odds import load_tracker_closing_odds_by_bet_id
from v2.paper.clv import compute_clv
from v2.paper.db import ensure_tracking_schema
from v2.paper.providers import EspnResultsProvider
from v2.paper.report import summarize_window_metrics
from v2.paper.settle import run_settlement


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

    def test_settlement_marks_tracker_close_odds_source_when_tracker_available(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "tracking.sqlite"
            tracker_db = Path(td) / "odds_tracker.sqlite"
            ensure_tracking_schema(db_path)

            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    """
                    INSERT INTO bet_log (
                      bet_id, kickoff_time_hkt, league, home, away, market, market_type, line, selection,
                      odds_bet, model_prob, ev, kelly_pct, stake, result, profit, bankroll,
                      notes, source_book, source_file, run_id, source_quality, odds_source
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "b_tracker",
                        "2026-03-16T22:00:00+08:00",
                        "EPL",
                        "Arsenal",
                        "Chelsea",
                        "1X2",
                        "1X2",
                        "",
                        "Home",
                        2.0,
                        0.55,
                        0.05,
                        0.02,
                        100.0,
                        None,
                        None,
                        2000.0,
                        "paper:2026-03-16 match_id=soccer_epl:1",
                        "paper_sim",
                        "ut",
                        "ut",
                        "real_odds",
                        "espn",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            tconn = sqlite3.connect(str(tracker_db))
            try:
                tconn.executescript(
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
                tconn.execute(
                    "INSERT INTO odds_match(id, match_url, market, label) VALUES (1, ?, '1X2', ?)",
                    (
                        "https://www.oddsportal.com/football/england/premier-league/arsenal-chelsea-abc123/",
                        "Arsenal vs Chelsea",
                    ),
                )
                tconn.execute(
                    "INSERT INTO odds_snapshot(id, match_id, snapshot_ts_utc, success) VALUES (10, 1, '2026-03-16T11:00:00+00:00', 1)"
                )
                tconn.execute(
                    "INSERT INTO odds_quote(snapshot_id, bookmaker, market_type, line, home, draw, away) VALUES (10, 'book', '1X2', NULL, 2.20, 3.20, 3.10)"
                )
                tconn.commit()
            finally:
                tconn.close()

            with patch("v2.paper.settle._scores_with_ids", return_value=({}, {"soccer_epl:1": (1, 0)})), patch(
                "v2.paper.settle._fetch_closing_odds_map",
                return_value={("soccer_epl:1", "1X2", "Home"): 2.40},
            ):
                settled = run_settlement(
                    db_path=db_path,
                    day=date(2026, 3, 16),
                    provider=EspnResultsProvider(),
                    closing_odds_tracker_sqlite=tracker_db,
                )

            self.assertEqual(settled, 1)
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("SELECT odds_close, close_odds_source FROM bet_log WHERE bet_id='b_tracker'").fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)
            self.assertAlmostEqual(float(row[0]), 2.20, places=9)
            self.assertEqual(str(row[1]), "tracker")

    def test_settlement_marks_provider_close_odds_source_when_tracker_missing(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "tracking.sqlite"
            ensure_tracking_schema(db_path)

            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    """
                    INSERT INTO bet_log (
                      bet_id, kickoff_time_hkt, league, home, away, market, market_type, line, selection,
                      odds_bet, model_prob, ev, kelly_pct, stake, result, profit, bankroll,
                      notes, source_book, source_file, run_id, source_quality, odds_source
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "b_provider",
                        "2026-03-16T22:00:00+08:00",
                        "EPL",
                        "Arsenal",
                        "Chelsea",
                        "1X2",
                        "1X2",
                        "",
                        "Home",
                        2.0,
                        0.55,
                        0.05,
                        0.02,
                        100.0,
                        None,
                        None,
                        2000.0,
                        "paper:2026-03-16 match_id=soccer_epl:2",
                        "paper_sim",
                        "ut",
                        "ut",
                        "real_odds",
                        "espn",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            with patch("v2.paper.settle._scores_with_ids", return_value=({}, {"soccer_epl:2": (1, 0)})), patch(
                "v2.paper.settle._fetch_closing_odds_map",
                return_value={("soccer_epl:2", "1X2", "Home"): 2.40},
            ):
                settled = run_settlement(
                    db_path=db_path,
                    day=date(2026, 3, 16),
                    provider=EspnResultsProvider(),
                    closing_odds_tracker_sqlite=None,
                )

            self.assertEqual(settled, 1)
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("SELECT odds_close, close_odds_source FROM bet_log WHERE bet_id='b_provider'").fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)
            self.assertAlmostEqual(float(row[0]), 2.40, places=9)
            self.assertEqual(str(row[1]), "provider")

    def test_summary_emits_closing_odds_fallback_diagnostics(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "tracking.sqlite"
            ensure_tracking_schema(db_path)

            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    """
                    INSERT INTO bet_log (
                      bet_id, kickoff_time_hkt, league, home, away, market, market_type, line, selection,
                      odds_bet, model_prob, ev, kelly_pct, stake, result, profit, bankroll,
                      source_book, source_file, run_id, source_quality, odds_source,
                      odds_close, clv_abs, clv_pct, close_odds_source
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "b_t",
                        "2026-03-16T10:00:00+08:00",
                        "EPL",
                        "A",
                        "B",
                        "1X2",
                        "1X2",
                        "",
                        "Home",
                        2.0,
                        0.55,
                        0.05,
                        0.02,
                        100.0,
                        "win",
                        100.0,
                        2100.0,
                        "paper_sim",
                        "ut",
                        "ut",
                        "real_odds",
                        "espn",
                        2.1,
                        0.1,
                        5.0,
                        "tracker",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO bet_log (
                      bet_id, kickoff_time_hkt, league, home, away, market, market_type, line, selection,
                      odds_bet, model_prob, ev, kelly_pct, stake, result, profit, bankroll,
                      source_book, source_file, run_id, source_quality, odds_source,
                      odds_close, clv_abs, clv_pct, close_odds_source
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "b_p",
                        "2026-03-16T11:00:00+08:00",
                        "EPL",
                        "C",
                        "D",
                        "1X2",
                        "1X2",
                        "",
                        "Away",
                        2.0,
                        0.55,
                        0.05,
                        0.02,
                        100.0,
                        "loss",
                        -100.0,
                        2000.0,
                        "paper_sim",
                        "ut",
                        "ut",
                        "real_odds",
                        "espn",
                        2.2,
                        0.2,
                        10.0,
                        "provider",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO bet_log (
                      bet_id, kickoff_time_hkt, league, home, away, market, market_type, line, selection,
                      odds_bet, model_prob, ev, kelly_pct, stake, result, profit, bankroll,
                      source_book, source_file, run_id, source_quality, odds_source,
                      odds_close, clv_abs, clv_pct, close_odds_source
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "b_n",
                        "2026-03-16T12:00:00+08:00",
                        "EPL",
                        "E",
                        "F",
                        "1X2",
                        "1X2",
                        "",
                        "Home",
                        2.0,
                        0.55,
                        0.05,
                        0.02,
                        100.0,
                        "push",
                        0.0,
                        2000.0,
                        "paper_sim",
                        "ut",
                        "ut",
                        "real_odds",
                        "espn",
                        None,
                        None,
                        None,
                        None,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            summary = summarize_window_metrics(
                db_path=db_path,
                start=date(2026, 3, 16),
                end=date(2026, 3, 16),
                initial_bankroll=2000.0,
            )
            fb = summary.get("close_odds_fallback", {})
            self.assertEqual(int(fb.get("tracker_clv_sample_size", 0) or 0), 1)
            self.assertEqual(int(fb.get("provider_fallback_clv_sample_size", 0) or 0), 1)
            self.assertEqual(int(fb.get("uncovered_bets", 0) or 0), 1)
            self.assertAlmostEqual(float(fb.get("provider_fallback_share_pct_of_bets", 0.0) or 0.0), 33.3333333333, places=6)
            self.assertAlmostEqual(float(fb.get("provider_fallback_share_pct_of_clv_samples", 0.0) or 0.0), 50.0, places=9)
            self.assertAlmostEqual(float(fb.get("uncovered_pct", 0.0) or 0.0), 33.3333333333, places=6)


if __name__ == "__main__":
    unittest.main()
