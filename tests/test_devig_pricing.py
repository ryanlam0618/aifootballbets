import math
import unittest

from v2.paper.pricing import build_devig_implied_map


class TestDevigPricing(unittest.TestCase):
    def test_devig_for_1x2_and_two_way_markets(self):
        odds_map = {
            ("m1", "1X2", "Home"): 2.50,
            ("m1", "1X2", "Draw"): 3.20,
            ("m1", "1X2", "Away"): 2.80,
            ("m1", "Over/Under 2.5", "Over"): 1.95,
            ("m1", "Over/Under 2.5", "Under"): 1.95,
            ("m1", "Asian Handicap -0.5", "Home"): 2.02,
            ("m1", "Asian Handicap -0.5", "Away"): 1.90,
        }

        implied = build_devig_implied_map(odds_map)

        self.assertAlmostEqual(
            implied[("m1", "1X2", "Home")] + implied[("m1", "1X2", "Draw")] + implied[("m1", "1X2", "Away")],
            1.0,
            places=9,
        )
        self.assertAlmostEqual(
            implied[("m1", "Over/Under 2.5", "Over")] + implied[("m1", "Over/Under 2.5", "Under")],
            1.0,
            places=9,
        )
        self.assertAlmostEqual(
            implied[("m1", "Asian Handicap -0.5", "Home")] + implied[("m1", "Asian Handicap -0.5", "Away")],
            1.0,
            places=9,
        )

    def test_incomplete_group_falls_back_to_raw_implied(self):
        odds_map = {
            ("m2", "1X2", "Home"): 2.0,
            ("m2", "1X2", "Away"): 3.0,  # draw missing
        }
        implied = build_devig_implied_map(odds_map)
        self.assertAlmostEqual(implied[("m2", "1X2", "Home")], 0.5, places=9)
        self.assertAlmostEqual(implied[("m2", "1X2", "Away")], 1 / 3, places=9)

    def test_invalid_price_in_group_does_not_pollute_other_selections(self):
        odds_map = {
            ("m3", "1X2", "Home"): 2.50,
            ("m3", "1X2", "Draw"): 3.20,
            ("m3", "1X2", "Away"): 1.00,  # invalid -> nan raw implied
            ("m4", "Over/Under 2.5", "Over"): 1.95,
            ("m4", "Over/Under 2.5", "Under"): 0.00,  # invalid -> nan raw implied
        }

        implied = build_devig_implied_map(odds_map)

        self.assertAlmostEqual(implied[("m3", "1X2", "Home")], 1 / 2.5, places=9)
        self.assertAlmostEqual(implied[("m3", "1X2", "Draw")], 1 / 3.2, places=9)
        self.assertTrue(math.isnan(implied[("m3", "1X2", "Away")]))

        self.assertAlmostEqual(implied[("m4", "Over/Under 2.5", "Over")], 1 / 1.95, places=9)
        self.assertTrue(math.isnan(implied[("m4", "Over/Under 2.5", "Under")]))

    def test_asian_handicap_pairs_home_minus_with_away_plus_same_line(self):
        odds_map = {
            ("m5", "Asian Handicap -0.5", "Home"): 2.02,
            ("m5", "Asian Handicap 0.5", "Away"): 1.90,
        }

        implied = build_devig_implied_map(odds_map)

        # Should de-vig as one 2-way market instead of falling back to raw implieds
        self.assertAlmostEqual(
            implied[("m5", "Asian Handicap -0.5", "Home")] + implied[("m5", "Asian Handicap 0.5", "Away")],
            1.0,
            places=9,
        )

    def test_over_under_groups_equivalent_numeric_lines(self):
        odds_map = {
            ("m6", "Over/Under 2.5", "Over"): 1.95,
            ("m6", "Over/Under 2.50", "Under"): 1.95,
        }

        implied = build_devig_implied_map(odds_map)

        self.assertAlmostEqual(implied[("m6", "Over/Under 2.5", "Over")], 0.5, places=9)
        self.assertAlmostEqual(implied[("m6", "Over/Under 2.50", "Under")], 0.5, places=9)

    def test_selection_aliases_are_canonicalized_before_grouping(self):
        odds_map = {
            ("m7", "1X2", "h"): 2.50,
            ("m7", "1X2", "x"): 3.20,
            ("m7", "1X2", "a"): 2.80,
            ("m8", "Over/Under 2.5", "o"): 1.95,
            ("m8", "Over/Under 2.5", "u"): 1.95,
            ("m9", "Asian Handicap -0.5", "h"): 2.02,
            ("m9", "Asian Handicap 0.5", "a"): 1.90,
        }

        implied = build_devig_implied_map(odds_map)

        self.assertAlmostEqual(
            implied[("m7", "1X2", "h")] + implied[("m7", "1X2", "x")] + implied[("m7", "1X2", "a")],
            1.0,
            places=9,
        )
        self.assertAlmostEqual(
            implied[("m8", "Over/Under 2.5", "o")] + implied[("m8", "Over/Under 2.5", "u")],
            1.0,
            places=9,
        )
        self.assertAlmostEqual(
            implied[("m9", "Asian Handicap -0.5", "h")] + implied[("m9", "Asian Handicap 0.5", "a")],
            1.0,
            places=9,
        )

    def test_market_aliases_are_canonicalized_before_grouping(self):
        odds_map = {
            ("m10", "match odds", "1"): 2.50,
            ("m10", "h2h", "x"): 3.20,
            ("m10", "moneyline", "2"): 2.80,
            ("m11", "OU 2.5", "Over"): 1.95,
            ("m11", "Totals 2.50", "Under"): 1.95,
            ("m12", "AH -0.5", "Home"): 2.02,
            ("m12", "spreads 0.5", "Away"): 1.90,
        }

        implied = build_devig_implied_map(odds_map)

        self.assertAlmostEqual(
            implied[("m10", "match odds", "1")]
            + implied[("m10", "h2h", "x")]
            + implied[("m10", "moneyline", "2")],
            1.0,
            places=9,
        )
        self.assertAlmostEqual(
            implied[("m11", "OU 2.5", "Over")] + implied[("m11", "Totals 2.50", "Under")],
            1.0,
            places=9,
        )
        self.assertAlmostEqual(
            implied[("m12", "AH -0.5", "Home")] + implied[("m12", "spreads 0.5", "Away")],
            1.0,
            places=9,
        )


if __name__ == "__main__":
    unittest.main()
