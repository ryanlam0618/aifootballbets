"""Hermetic tests for the afb-T5 v1 pipeline (no DB required)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from v1_pipeline import PipelineResult, build_snapshot_rows  # noqa: E402


import unittest  # noqa: E402


class TestPipelineResultJson(unittest.TestCase):
    def test_roundtrip(self):
        r = PipelineResult(day="2026-10-31", stages={"pick_day": {"n": 3}, "odds_snapshot": {"n_rows": 9}})
        parsed = json.loads(r.to_json())
        self.assertEqual(parsed["day"], "2026-10-31")
        self.assertEqual(parsed["stages"]["pick_day"]["n"], 3)
        self.assertEqual(parsed["stages"]["odds_snapshot"]["n_rows"], 9)


class TestBuildSnapshotRows(unittest.TestCase):
    def _fixtures(self):
        return [
            {
                "match_id": "111",
                "league": "Premier League",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
            },
            {
                "match_id": "222",
                "league": "Serie A",
                "home_team": "Inter",
                "away_team": "Milan",
            },
        ]

    def test_three_rows_per_odds_match(self):
        odds = {"111": {"Home": 2.0, "Draw": 3.4, "Away": 3.8}}  # 222 has no odds
        rows = build_snapshot_rows(self._fixtures(), odds, datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(len(rows), 3)  # only the odds-bearing fixture
        self.assertTrue(all(r["match_id"] == "111" for r in rows))
        self.assertEqual({r["selection"] for r in rows}, {"Home", "Draw", "Away"})
        self.assertTrue(all(r["market_key"] == "1X2" for r in rows))
        self.assertTrue(all(r["bookmaker"] == "avg" for r in rows))

    def test_empty_odds(self):
        rows = build_snapshot_rows(self._fixtures(), {}, datetime(2026, 10, 31, 12, 0, 0))
        self.assertEqual(rows, [])

    def test_captured_at_microsecond_stripped(self):
        odds = {"222": {"Home": 1.9, "Draw": 3.2, "Away": 4.1}}
        rows = build_snapshot_rows(self._fixtures(), odds, datetime(2026, 10, 31, 12, 0, 0, 123456, tzinfo=timezone.utc))
        self.assertTrue(all(r["captured_at_utc"].microsecond == 0 for r in rows))


if __name__ == "__main__":
    unittest.main()
