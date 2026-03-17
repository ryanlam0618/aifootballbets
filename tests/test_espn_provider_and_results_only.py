import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from v2.paper.db import ensure_tracking_schema
from v2.paper.ledger import open_unsettled_bets_for_day
from v2.paper.models import MatchInfo
from v2.paper.providers import EspnResultsProvider, OddsProvider, match_key
from v2.paper.run_day import run_for_day
from v2.paper.settle import run_settlement


class EmptyOddsRealFixtureProvider(OddsProvider):
    """Real fixture shape, but no odds -> should trigger results-only synthetic odds."""

    def fetch_matches(self, day: date, league_keys):
        return [
            MatchInfo(
                match_id="soccer_epl:740887",
                league_key="soccer_epl",
                league_name="EPL",
                kickoff_utc="2026-03-16T10:00:00+00:00",
                home_team="Brentford",
                away_team="Wolverhampton Wanderers",
            )
        ]

    def fetch_market_odds(self, day: date, league_keys, matches):
        return {}


class StaticResultsProvider(EspnResultsProvider):
    def fetch_ft_scores_with_ids(self, day, league_keys):
        # Brentford 1-2 Wolves
        by_names = {"brentford|wolverhampton wanderers": (1, 2)}
        by_ids = {"740887": (1, 2), "soccer_epl:740887": (1, 2)}
        return by_names, by_ids


class NamesOnlyResultsProvider(EspnResultsProvider):
    def fetch_ft_scores_with_ids(self, day, league_keys):
        # Explicitly exercise names-only fallback path (no match-id map available).
        return {"brentford|wolverhampton wanderers": (1, 2)}, {}


class TestEspnProviderAndResultsOnly(unittest.TestCase):
    def test_results_only_mode_generates_selection(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "tracking.sqlite"
            ensure_tracking_schema(db_path)

            res = run_for_day(
                day=date(2026, 3, 16),
                db_path=db_path,
                snapshot_db=Path(td) / "snap.sqlite",
                initial_bankroll=2000.0,
                run_id="results_only_ut",
                provider=EmptyOddsRealFixtureProvider(),
                allow_synthetic_odds=True,
            )

            self.assertEqual(res["matches"], 1)
            self.assertTrue(res["results_only_mode"])
            self.assertGreaterEqual(res["candidates"], 1)
            self.assertGreaterEqual(res["selected"], 1)
            self.assertEqual(res["inserted"], res["selected"])

            rows = open_unsettled_bets_for_day(db_path, date(2026, 3, 16))
            self.assertEqual(len(rows), res["selected"])

    def test_settlement_uses_match_id_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "tracking.sqlite"
            ensure_tracking_schema(db_path)

            run_for_day(
                day=date(2026, 3, 16),
                db_path=db_path,
                snapshot_db=Path(td) / "snap.sqlite",
                initial_bankroll=2000.0,
                run_id="settle_by_id_ut",
                provider=EmptyOddsRealFixtureProvider(),
                allow_synthetic_odds=True,
            )

            settled = run_settlement(
                db_path=db_path,
                day=date(2026, 3, 16),
                provider=StaticResultsProvider(),
            )
            self.assertGreaterEqual(settled, 1)

    def test_settlement_falls_back_to_name_mapping_when_match_id_missing(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "tracking.sqlite"
            ensure_tracking_schema(db_path)

            run_for_day(
                day=date(2026, 3, 16),
                db_path=db_path,
                snapshot_db=Path(td) / "snap.sqlite",
                initial_bankroll=2000.0,
                run_id="settle_by_name_ut",
                provider=EmptyOddsRealFixtureProvider(),
                allow_synthetic_odds=True,
            )

            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute(
                    "SELECT notes, home, away, market, line, selection, stake, odds_bet FROM bet_log LIMIT 1"
                ).fetchone()
                self.assertIsNotNone(row)
                notes, home, away, market, line, selection, stake, odds_bet = row
                self.assertIn("match_id=", str(notes))

                conn.execute(
                    "UPDATE bet_log SET notes = REPLACE(notes, ?, '')",
                    ("match_id=soccer_epl:740887",),
                )
                conn.commit()
            finally:
                conn.close()

            calls = {"seen": 0}
            expected_k = match_key("Brentford", "Wolverhampton Wanderers")

            def _spy_resolve_profit(bet_row, score):
                calls["seen"] += 1
                # Settlement should still succeed by team-name key after match_id removal.
                self.assertEqual(match_key(str(bet_row["home"]), str(bet_row["away"])), expected_k)
                self.assertEqual(score, (1, 2))
                # Keep deterministic profit to avoid coupling to strategy internals.
                return "loss", -float(bet_row["stake"])

            with patch("v2.paper.settle._resolve_profit", side_effect=_spy_resolve_profit):
                settled = run_settlement(
                    db_path=db_path,
                    day=date(2026, 3, 16),
                    provider=NamesOnlyResultsProvider(),
                )

            self.assertGreaterEqual(calls["seen"], 1)
            self.assertGreaterEqual(settled, 1)


if __name__ == "__main__":
    unittest.main()
