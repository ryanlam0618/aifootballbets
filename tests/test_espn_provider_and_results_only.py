import tempfile
import unittest
from datetime import date
from pathlib import Path

from v2.paper.db import ensure_tracking_schema
from v2.paper.ledger import open_unsettled_bets_for_day
from v2.paper.models import MatchInfo
from v2.paper.providers import EspnResultsProvider, OddsProvider
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


if __name__ == "__main__":
    unittest.main()
