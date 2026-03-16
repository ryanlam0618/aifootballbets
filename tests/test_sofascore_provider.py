import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from v2.paper.constants import LEAGUE_UNIVERSE, SOFASCORE_LEAGUE_MAP
from v2.paper.providers import SofaScoreFixturesResultsProvider
from v2.paper.run_day import _build_odds_provider
from v2.paper.settle import _build_results_provider


class TestSofaScoreProvider(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = Path(__file__).parent / "fixtures" / "sofascore"

    def _fake_http_get_json(self, url, params=None, timeout=25):
        _ = (params, timeout)
        if "/sport/football/scheduled-events/" in url:
            day = url.rsplit("/", 1)[-1]
            p = self.fixtures_dir / f"scheduled-events-{day}.json"
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"events": []}
        if "/event/" in url:
            event_id = url.rsplit("/", 1)[-1]
            p = self.fixtures_dir / f"event-{event_id}.json"
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"event": {}}
        return {}

    def test_sofascore_map_covers_universe(self):
        for league_key in LEAGUE_UNIVERSE:
            self.assertIn(league_key, SOFASCORE_LEAGUE_MAP)

    @patch("v2.paper.providers._http_get_json")
    def test_fetch_matches_respects_timezone_window_and_aliases(self, mock_http_get_json):
        mock_http_get_json.side_effect = self._fake_http_get_json
        provider = SofaScoreFixturesResultsProvider()

        matches = provider.fetch_matches(day=date(2026, 3, 16), league_keys=LEAGUE_UNIVERSE)
        got_ids = {m.match_id for m in matches}

        # Included in 2026-03-16 Asia/Shanghai 09:00->09:00 window:
        # 1001,1002,1005,1006 and 1010(alias fallback). Excludes 1003,1007,1008(boundary),1011(unknown league)
        self.assertEqual(
            got_ids,
            {
                "soccer_epl:1001",
                "soccer_spain_la_liga:1002",
                "soccer_japan_j_league:1005",
                "soccer_south_korea_kleague1:1006",
                "soccer_australia_aleague:1010",
            },
        )

    @patch("v2.paper.providers._http_get_json")
    def test_fetch_ft_scores_with_ids_finished_only(self, mock_http_get_json):
        mock_http_get_json.side_effect = self._fake_http_get_json
        provider = SofaScoreFixturesResultsProvider()

        by_names, by_ids = provider.fetch_ft_scores_with_ids(day=date(2026, 3, 16), league_keys=LEAGUE_UNIVERSE)

        self.assertEqual(by_names.get("arsenal|chelsea"), (2, 1))
        self.assertEqual(by_ids.get("1001"), (2, 1))
        self.assertEqual(by_ids.get("soccer_epl:1001"), (2, 1))
        self.assertNotIn("barcelona|sevilla", by_names)  # not started

    def test_cli_provider_switch_builders(self):
        self.assertIsInstance(_build_odds_provider("sofascore", provider_json=""), SofaScoreFixturesResultsProvider)
        self.assertIsInstance(_build_results_provider("sofascore"), SofaScoreFixturesResultsProvider)


if __name__ == "__main__":
    unittest.main()
