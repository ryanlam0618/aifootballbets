import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from v2.config import settings_v2
from v2.paper.db import ensure_tracking_schema
from v2.paper.report import generate_reports
from v2.paper.models import MatchInfo
from v2.paper.providers import OddsProvider
from v2.paper.run_day import run_for_day


class MultiMatchProvider(OddsProvider):
    def fetch_matches(self, day: date, league_keys):
        _ = (day, league_keys)
        return [
            MatchInfo(
                match_id="epl:1",
                league_key="soccer_epl",
                league_name="EPL",
                kickoff_utc="2026-03-16T12:00:00+00:00",
                home_team="A1",
                away_team="B1",
            ),
            MatchInfo(
                match_id="epl:2",
                league_key="soccer_epl",
                league_name="EPL",
                kickoff_utc="2026-03-16T13:00:00+00:00",
                home_team="A2",
                away_team="B2",
            ),
            MatchInfo(
                match_id="esp:1",
                league_key="soccer_spain_la_liga",
                league_name="LaLiga",
                kickoff_utc="2026-03-16T14:00:00+00:00",
                home_team="A3",
                away_team="B3",
            ),
            MatchInfo(
                match_id="ita:1",
                league_key="soccer_italy_serie_a",
                league_name="Serie A",
                kickoff_utc="2026-03-16T15:00:00+00:00",
                home_team="A4",
                away_team="B4",
            ),
        ]

    def fetch_market_odds_with_meta(self, day: date, league_keys, matches):
        _ = (day, league_keys)
        odds = {}
        meta = {}
        for m in matches:
            k = (m.match_id, "1X2", "Home")
            odds[k] = 4.0
            meta[k] = {"source": "unit_test", "is_real": True}
        return odds, meta

    def fetch_market_odds(self, day: date, league_keys, matches):
        odds, _ = self.fetch_market_odds_with_meta(day=day, league_keys=league_keys, matches=matches)
        return odds


class NoOddsProvider(MultiMatchProvider):
    def fetch_market_odds_with_meta(self, day: date, league_keys, matches):
        _ = (day, league_keys, matches)
        return {}, {}


class PartialOddsProvider(MultiMatchProvider):
    def fetch_market_odds_with_meta(self, day: date, league_keys, matches):
        _ = (day, league_keys)
        # Only first match has real odds; others are missing and should be patched
        # by synthetic fallback when allow_synthetic_odds=True.
        if not matches:
            return {}, {}
        m = matches[0]
        key = (m.match_id, "1X2", "Home")
        return {key: 3.6}, {key: {"source": "unit_test_partial", "is_real": True}}


class TestSelectionConstraintsAndReports(unittest.TestCase):
    def test_daily_stop_loss_pct_is_configurable(self):
        old_day = settings_v2.paper_max_bets_per_day
        old_league = settings_v2.paper_max_bets_per_league_per_day
        old_edge = settings_v2.min_edge
        old_stop = settings_v2.paper_daily_stop_loss_pct
        try:
            settings_v2.paper_max_bets_per_day = 4
            settings_v2.paper_max_bets_per_league_per_day = 2
            settings_v2.min_edge = 0.0
            settings_v2.paper_daily_stop_loss_pct = 0.05

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
                          source_book, source_file, run_id, source_quality, odds_source
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            "preloss_ut",
                            "2026-03-16T09:00:00+08:00",
                            "EPL",
                            "PX",
                            "PY",
                            "1X2",
                            "1X2",
                            "",
                            "Home",
                            2.0,
                            0.50,
                            0.0,
                            0.01,
                            100.0,
                            "loss",
                            -120.0,
                            1880.0,
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

                res = run_for_day(
                    day=date(2026, 3, 16),
                    db_path=db_path,
                    snapshot_db=Path(td) / "snap.sqlite",
                    initial_bankroll=2000.0,
                    run_id="daily_stop_loss_ut",
                    provider=MultiMatchProvider(),
                )

                self.assertTrue(res["risk_stop"])
                self.assertEqual(res["paper_daily_stop_loss_pct"], 0.05)
                self.assertEqual(res["selected"], 0)
                self.assertEqual(res["inserted"], 0)
        finally:
            settings_v2.paper_max_bets_per_day = old_day
            settings_v2.paper_max_bets_per_league_per_day = old_league
            settings_v2.min_edge = old_edge
            settings_v2.paper_daily_stop_loss_pct = old_stop

    def test_max_stake_fraction_cap_applies(self):
        old_cap = settings_v2.paper_max_stake_fraction_per_bet
        old_edge = settings_v2.min_edge
        old_day = settings_v2.paper_max_bets_per_day
        old_league = settings_v2.paper_max_bets_per_league_per_day
        try:
            settings_v2.paper_max_stake_fraction_per_bet = 0.01
            settings_v2.min_edge = 0.0
            settings_v2.paper_max_bets_per_day = 1
            settings_v2.paper_max_bets_per_league_per_day = 1

            with tempfile.TemporaryDirectory() as td:
                db_path = Path(td) / "tracking.sqlite"
                ensure_tracking_schema(db_path)

                run_for_day(
                    day=date(2026, 3, 16),
                    db_path=db_path,
                    snapshot_db=Path(td) / "snap.sqlite",
                    initial_bankroll=2000.0,
                    run_id="stake_cap_ut",
                    provider=MultiMatchProvider(),
                )

                conn = sqlite3.connect(str(db_path))
                try:
                    row = conn.execute("SELECT stake FROM bet_log LIMIT 1").fetchone()
                finally:
                    conn.close()

                self.assertIsNotNone(row)
                self.assertLessEqual(float(row[0]), 20.0 + 1e-6)
        finally:
            settings_v2.paper_max_stake_fraction_per_bet = old_cap
            settings_v2.min_edge = old_edge
            settings_v2.paper_max_bets_per_day = old_day
            settings_v2.paper_max_bets_per_league_per_day = old_league

    def test_selection_constraints_day_and_league_caps(self):
        old_day = settings_v2.paper_max_bets_per_day
        old_league = settings_v2.paper_max_bets_per_league_per_day
        old_edge = settings_v2.min_edge
        old_stop = settings_v2.paper_daily_stop_loss_pct
        try:
            settings_v2.paper_max_bets_per_day = 2
            settings_v2.paper_max_bets_per_league_per_day = 1
            settings_v2.min_edge = 0.0
            settings_v2.paper_daily_stop_loss_pct = 0.20

            with tempfile.TemporaryDirectory() as td:
                db_path = Path(td) / "tracking.sqlite"
                ensure_tracking_schema(db_path)

                res = run_for_day(
                    day=date(2026, 3, 16),
                    db_path=db_path,
                    snapshot_db=Path(td) / "snap.sqlite",
                    initial_bankroll=2000.0,
                    run_id="constraints_ut",
                    provider=MultiMatchProvider(),
                )

                self.assertEqual(res["selected"], 2)
                self.assertEqual(res["inserted"], 2)

                conn = sqlite3.connect(str(db_path))
                try:
                    rows = conn.execute(
                        "SELECT league, COUNT(*) FROM bet_log GROUP BY league ORDER BY league"
                    ).fetchall()
                finally:
                    conn.close()

                # league cap = 1 means no league can appear more than once
                self.assertTrue(all(int(c) <= 1 for _l, c in rows))
        finally:
            settings_v2.paper_max_bets_per_day = old_day
            settings_v2.paper_max_bets_per_league_per_day = old_league
            settings_v2.min_edge = old_edge
            settings_v2.paper_daily_stop_loss_pct = old_stop

    def test_report_separates_source_quality(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "tracking.sqlite"
            out_dir = Path(td) / "reports"
            ensure_tracking_schema(db_path)

            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    """
                    INSERT INTO bet_log (
                      bet_id, kickoff_time_hkt, league, home, away, market, market_type, line, selection,
                      odds_bet, model_prob, ev, kelly_pct, stake, result, profit, bankroll,
                      source_book, source_file, run_id, source_quality, odds_source
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "r1",
                        "2026-03-16T12:00:00+08:00",
                        "EPL",
                        "A",
                        "B",
                        "1X2",
                        "1X2",
                        "",
                        "Home",
                        2.1,
                        0.52,
                        0.02,
                        0.01,
                        100.0,
                        "win",
                        110.0,
                        2110.0,
                        "paper_sim",
                        "ut",
                        "ut",
                        "real_odds",
                        "espn",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO bet_log (
                      bet_id, kickoff_time_hkt, league, home, away, market, market_type, line, selection,
                      odds_bet, model_prob, ev, kelly_pct, stake, result, profit, bankroll,
                      source_book, source_file, run_id, source_quality, odds_source
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "s1",
                        "2026-03-16T13:00:00+08:00",
                        "LaLiga",
                        "C",
                        "D",
                        "1X2",
                        "1X2",
                        "",
                        "Away",
                        2.0,
                        0.49,
                        -0.01,
                        0.01,
                        100.0,
                        "loss",
                        -100.0,
                        2010.0,
                        "paper_sim",
                        "ut",
                        "ut",
                        "synthetic_odds",
                        "synthetic",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            _daily, weekly = generate_reports(db_path=db_path, day=date(2026, 3, 16), out_dir=out_dir)
            text = weekly.read_text(encoding="utf-8")
            self.assertIn("## By source_quality", text)
            self.assertIn("real_odds", text)
            self.assertIn("synthetic_odds", text)

    def test_results_only_mode_is_selected_and_reported(self):
        old_day = settings_v2.paper_max_bets_per_day
        old_league = settings_v2.paper_max_bets_per_league_per_day
        old_edge = settings_v2.min_edge
        try:
            settings_v2.paper_max_bets_per_day = 2
            settings_v2.paper_max_bets_per_league_per_day = 1
            settings_v2.min_edge = 0.0

            with tempfile.TemporaryDirectory() as td:
                db_path = Path(td) / "tracking.sqlite"
                ensure_tracking_schema(db_path)

                res = run_for_day(
                    day=date(2026, 3, 16),
                    db_path=db_path,
                    snapshot_db=Path(td) / "snap.sqlite",
                    initial_bankroll=2000.0,
                    run_id="results_only_ut",
                    provider=NoOddsProvider(),
                    allow_synthetic_odds=True,
                )

                self.assertTrue(res["results_only_mode"])
                self.assertEqual(res["selected"], 2)
                self.assertEqual(res["selected_real_odds"], 0)
                self.assertEqual(res["selected_synthetic_odds"], 2)

                out_dir = Path(td) / "reports"
                _daily, weekly = generate_reports(db_path=db_path, day=date(2026, 3, 16), out_dir=out_dir)
                text = weekly.read_text(encoding="utf-8")
                self.assertIn("synthetic_odds", text)
                self.assertNotIn("real_odds", text)
        finally:
            settings_v2.paper_max_bets_per_day = old_day
            settings_v2.paper_max_bets_per_league_per_day = old_league
            settings_v2.min_edge = old_edge

    def test_partial_missing_odds_are_patched_by_synthetic_when_enabled(self):
        old_day = settings_v2.paper_max_bets_per_day
        old_league = settings_v2.paper_max_bets_per_league_per_day
        old_edge = settings_v2.min_edge
        try:
            settings_v2.paper_max_bets_per_day = 4
            settings_v2.paper_max_bets_per_league_per_day = 2
            settings_v2.min_edge = 0.0

            with tempfile.TemporaryDirectory() as td:
                db_path = Path(td) / "tracking.sqlite"
                ensure_tracking_schema(db_path)

                res = run_for_day(
                    day=date(2026, 3, 16),
                    db_path=db_path,
                    snapshot_db=Path(td) / "snap.sqlite",
                    initial_bankroll=2000.0,
                    run_id="partial_odds_ut",
                    provider=PartialOddsProvider(),
                    allow_synthetic_odds=True,
                )

                self.assertFalse(res["results_only_mode"])
                self.assertGreaterEqual(res["selected"], 1)
                self.assertGreaterEqual(res["selected_real_odds"], 1)
                self.assertGreaterEqual(res["selected_synthetic_odds"], 1)
                self.assertGreaterEqual(res["synthetic_added_markets"], 1)

                conn = sqlite3.connect(str(db_path))
                try:
                    rows = conn.execute(
                        "SELECT source_quality, COUNT(*) FROM bet_log GROUP BY source_quality"
                    ).fetchall()
                finally:
                    conn.close()

                counts = {str(k): int(v) for k, v in rows}
                self.assertIn("real_odds", counts)
                self.assertIn("synthetic_odds", counts)
                self.assertGreaterEqual(counts["real_odds"], 1)
                self.assertGreaterEqual(counts["synthetic_odds"], 1)
        finally:
            settings_v2.paper_max_bets_per_day = old_day
            settings_v2.paper_max_bets_per_league_per_day = old_league
            settings_v2.min_edge = old_edge


if __name__ == "__main__":
    unittest.main()
