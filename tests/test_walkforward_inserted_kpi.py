import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from paper.run_7d import run_walkforward


class TestWalkforwardInsertedKpi(unittest.TestCase):
    @patch("paper.run_7d._window_inserted_kpi_aggregate")
    @patch("paper.run_7d.run_7d")
    def test_walkforward_emits_inserted_kpi_aggregate(self, mock_run_7d, mock_tags):
        mock_run_7d.side_effect = [
            {
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "days": [
                    {"selection": {"selected": 3, "inserted": 2}},
                    {"selection": {"selected": 1, "inserted": 1}},
                ],
                "summary": {
                    "bets": 5,
                    "pnl": 10.0,
                    "roi_pct": 2.0,
                    "max_drawdown_pct": 1.0,
                    "winrate_pct": 55.0,
                    "clv_sample_size": 2,
                    "avg_clv_pct": 0.5,
                },
            },
            {
                "start_date": "2026-03-08",
                "end_date": "2026-03-14",
                "days": [
                    {"selection": {"selected": 2, "inserted": 1}},
                ],
                "summary": {
                    "bets": 4,
                    "pnl": -5.0,
                    "roi_pct": -1.0,
                    "max_drawdown_pct": 3.0,
                    "winrate_pct": 45.0,
                    "clv_sample_size": 0,
                    "avg_clv_pct": 0.0,
                },
            },
        ]

        mock_tags.return_value = {
            "kpi_basis": "inserted",
            "rows": [
                {
                    "league": "EPL",
                    "strategy": "1X2",
                    "inserted_count": 2,
                    "stake": 200.0,
                    "pnl": 8.0,
                    "roi_pct": 4.0,
                    "wins": 1,
                    "losses": 1,
                    "pushes": 0,
                    "winrate_pct": 50.0,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td) / "reports"
            payload = run_walkforward(
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 8),
                db_path=Path(td) / "tracking.sqlite",
                snapshot_db=Path(td) / "snap.sqlite",
                run_prefix="wf_ut",
                out_dir=out_dir,
            )

            md_path = out_dir / "paper_walkforward_2026-03-01_2026-03-08.md"
            self.assertTrue(md_path.exists())
            md_text = md_path.read_text(encoding="utf-8")
            self.assertIn("# Paper Walkforward Summary", md_text)
            self.assertIn("## Aggregate", md_text)
            self.assertIn("KPI basis: inserted", md_text)
            self.assertIn("## By window league/strategy (inserted KPI)", md_text)

        self.assertEqual(payload["aggregate"]["kpi_basis"], "inserted")
        self.assertEqual(payload["aggregate"]["windows"], 2)
        self.assertEqual(payload["aggregate"]["total_selected_count"], 6)
        self.assertEqual(payload["aggregate"]["total_inserted_new_count"], 4)
        self.assertEqual(payload["aggregate"]["total_inserted_count"], 9)

        self.assertIn("by_window_league_strategy", payload)
        self.assertEqual(len(payload["by_window_league_strategy"]), 2)
        first_window = payload["by_window_league_strategy"][0]
        self.assertEqual(first_window["kpi_basis"], "inserted")
        self.assertGreaterEqual(first_window["inserted_count"], 0)


if __name__ == "__main__":
    unittest.main()
