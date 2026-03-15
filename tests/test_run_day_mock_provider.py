import tempfile
import unittest
from datetime import date
from pathlib import Path

from v2.paper.db import ensure_tracking_schema
from v2.paper.ledger import open_unsettled_bets_for_day
from v2.paper.providers import JsonFileOddsProvider
from v2.paper.run_day import run_for_day


class TestRunDayWithMockProvider(unittest.TestCase):
    def test_run_day_inserts_deterministic_selection(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "tracking.sqlite"
            snap_path = Path(td) / "snap.sqlite"
            ensure_tracking_schema(db_path)

            fixture_json = Path(__file__).parent / "fixtures" / "mock_provider_day.json"
            provider = JsonFileOddsProvider(fixture_json)

            sim_day = date(2026, 3, 16)
            res = run_for_day(
                day=sim_day,
                db_path=db_path,
                snapshot_db=snap_path,
                initial_bankroll=2000.0,
                run_id="unit_test_run",
                provider=provider,
            )

            self.assertEqual(res["matches"], 1)
            self.assertGreaterEqual(res["candidates"], 1)
            self.assertEqual(res["selected"], 1)
            self.assertEqual(res["inserted"], 1)

            rows = open_unsettled_bets_for_day(db_path, sim_day)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["home"], "Alpha FC")
            self.assertEqual(row["away"], "Beta FC")
            self.assertEqual(row["market"], "1X2")
            self.assertEqual(row["selection"], "Home")
            self.assertIsNone(row["result"])


if __name__ == "__main__":
    unittest.main()
