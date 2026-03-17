import unittest

from v2.paper.settle import _resolve_profit


def _row(market: str, selection: str, line, odds: float = 2.0, stake: float = 100.0):
    return {
        "market": market,
        "selection": selection,
        "line": line,
        "odds_bet": odds,
        "stake": stake,
    }


class TestQuarterLineSettlement(unittest.TestCase):
    def test_ou_over_2_25_half_loss(self):
        row = _row("Over/Under", "Over", 2.25)
        result, profit = _resolve_profit(row, (1, 1))  # total=2
        self.assertEqual(result, "half_loss")
        self.assertAlmostEqual(profit, -50.0, places=6)

    def test_ou_under_2_75_half_loss(self):
        row = _row("Over/Under", "Under", 2.75)
        result, profit = _resolve_profit(row, (2, 1))  # total=3
        self.assertEqual(result, "half_loss")
        self.assertAlmostEqual(profit, -50.0, places=6)

    def test_ou_over_2_75_half_win(self):
        row = _row("Over/Under", "Over", 2.75)
        result, profit = _resolve_profit(row, (2, 1))  # total=3
        self.assertEqual(result, "half_win")
        self.assertAlmostEqual(profit, 50.0, places=6)

    def test_ah_home_minus_0_25_half_loss_on_draw(self):
        row = _row("Asian Handicap", "Home", -0.25)
        result, profit = _resolve_profit(row, (1, 1))
        self.assertEqual(result, "half_loss")
        self.assertAlmostEqual(profit, -50.0, places=6)

    def test_ah_home_minus_0_75_half_win_on_one_goal_win(self):
        row = _row("Asian Handicap", "Home", -0.75)
        result, profit = _resolve_profit(row, (2, 1))
        self.assertEqual(result, "half_win")
        self.assertAlmostEqual(profit, 50.0, places=6)

    def test_ah_away_plus_0_25_half_win_on_draw(self):
        row = _row("Asian Handicap", "Away", 0.25)
        result, profit = _resolve_profit(row, (1, 1))
        self.assertEqual(result, "half_win")
        self.assertAlmostEqual(profit, 50.0, places=6)

    def test_ou_alias_market_and_selection_are_supported(self):
        row = _row("OU", "O", 2.25)
        result, profit = _resolve_profit(row, (1, 1))
        self.assertEqual(result, "half_loss")
        self.assertAlmostEqual(profit, -50.0, places=6)

    def test_ah_alias_market_and_selection_are_supported(self):
        row = _row("AH", "H", -0.25)
        result, profit = _resolve_profit(row, (1, 1))
        self.assertEqual(result, "half_loss")
        self.assertAlmostEqual(profit, -50.0, places=6)

    def test_market_aliases_with_hyphen_or_underscore_are_supported(self):
        row_ou = _row("over-under", "O", 2.25)
        result_ou, profit_ou = _resolve_profit(row_ou, (1, 1))
        self.assertEqual(result_ou, "half_loss")
        self.assertAlmostEqual(profit_ou, -50.0, places=6)

        row_ah = _row("asian_handicap", "A", 0.25)
        result_ah, profit_ah = _resolve_profit(row_ah, (1, 1))
        self.assertEqual(result_ah, "half_win")
        self.assertAlmostEqual(profit_ah, 50.0, places=6)

    def test_1x2_selection_alias_x_maps_to_draw(self):
        row = _row("1X2", "X", None)
        result, profit = _resolve_profit(row, (2, 2))
        self.assertEqual(result, "win")
        self.assertAlmostEqual(profit, 100.0, places=6)

    def test_verbose_selection_aliases_are_supported(self):
        row_ou = _row("ou", "Over 2.5", 2.25)
        result_ou, profit_ou = _resolve_profit(row_ou, (1, 1))
        self.assertEqual(result_ou, "half_loss")
        self.assertAlmostEqual(profit_ou, -50.0, places=6)

        row_ah = _row("asian handicap", "Away +0.25", 0.25)
        result_ah, profit_ah = _resolve_profit(row_ah, (1, 1))
        self.assertEqual(result_ah, "half_win")
        self.assertAlmostEqual(profit_ah, 50.0, places=6)

        row_1x2 = _row("moneyline", "Draw FT", None)
        result_1x2, profit_1x2 = _resolve_profit(row_1x2, (0, 0))
        self.assertEqual(result_1x2, "win")
        self.assertAlmostEqual(profit_1x2, 100.0, places=6)


if __name__ == "__main__":
    unittest.main()
