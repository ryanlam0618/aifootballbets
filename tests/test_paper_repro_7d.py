import tempfile
import unittest
from datetime import date
from pathlib import Path

from v2.paper.report import summarize_window_metrics
from v2.paper.run_7d import run_7d


class TestPaperRepro7D(unittest.TestCase):
    def test_reproducible_7d_with_provider_json(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            db_path = tdp / "tracking.sqlite"
            fixture = Path(__file__).parent / "fixtures" / "paper7d_provider.json"

            run_7d(
                start_date=date(2026, 3, 10),
                db_path=db_path,
                snapshot_db=tdp / "snap.sqlite",
                run_prefix="ut7d",
                odds_provider_name="espn",
                results_provider_name="espn",
                provider_json=str(fixture),
                allow_synthetic_odds=False,
                decision_log_dir=tdp / "decisions",
            )

            summary = summarize_window_metrics(
                db_path=db_path,
                start=date(2026, 3, 10),
                end=date(2026, 3, 16),
                initial_bankroll=2000.0,
            )

            self.assertGreaterEqual(summary["bets"], 1)
            self.assertIn("baseline_flat", summary)
            self.assertIn("by_market", summary)


if __name__ == "__main__":
    unittest.main()
