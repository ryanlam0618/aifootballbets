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

    def test_numeric_line_parsing_tolerates_decimal_comma_and_unicode_minus(self):
        odds_map = {
            ("m13", "Over/Under 2,5", "Over"): 1.95,
            ("m13", "OU 2.50", "Under"): 1.95,
            ("m14", "AH −0,5", "Home"): 2.02,
            ("m14", "Asian Handicap 0.5", "Away"): 1.90,
        }

        implied = build_devig_implied_map(odds_map)

        self.assertAlmostEqual(
            implied[("m13", "Over/Under 2,5", "Over")] + implied[("m13", "OU 2.50", "Under")],
            1.0,
            places=9,
        )
        self.assertAlmostEqual(
            implied[("m14", "AH −0,5", "Home")] + implied[("m14", "Asian Handicap 0.5", "Away")],
            1.0,
            places=9,
        )

    def test_selection_labels_with_embedded_lines_are_canonicalized(self):
        odds_map = {
            ("m15", "OU 2.5", "Over 2.5"): 1.91,
            ("m15", "Over/Under 2.50", "Under 2,5"): 1.99,
            ("m16", "AH -0.5", "Home -0.5"): 2.05,
            ("m16", "Asian Handicap 0.5", "Away +0.5"): 1.87,
        }

        implied = build_devig_implied_map(odds_map)

        self.assertAlmostEqual(
            implied[("m15", "OU 2.5", "Over 2.5")] + implied[("m15", "Over/Under 2.50", "Under 2,5")],
            1.0,
            places=9,
        )
        self.assertAlmostEqual(
            implied[("m16", "AH -0.5", "Home -0.5")] + implied[("m16", "Asian Handicap 0.5", "Away +0.5")],
            1.0,
            places=9,
        )

    def test_fallback_to_selection_line_when_market_line_is_missing(self):
        odds_map = {
            ("m17", "OU", "Over 2.5"): 1.93,
            ("m17", "Over/Under", "Under 2,50"): 1.97,
            ("m18", "AH", "Home -0.25"): 1.98,
            ("m18", "Asian Handicap", "Away +0,25"): 1.94,
        }

        implied = build_devig_implied_map(odds_map)

        self.assertAlmostEqual(
            implied[("m17", "OU", "Over 2.5")] + implied[("m17", "Over/Under", "Under 2,50")],
            1.0,
            places=9,
        )
        self.assertAlmostEqual(
            implied[("m18", "AH", "Home -0.25")] + implied[("m18", "Asian Handicap", "Away +0,25")],
            1.0,
            places=9,
        )

    def test_vulgar_fraction_lines_are_grouped_correctly(self):
        odds_map = {
            ("m19", "OU", "Over 2½"): 1.91,
            ("m19", "Over/Under", "Under 2.5"): 1.99,
            ("m20", "AH", "Home -0¼"): 2.03,
            ("m20", "Asian Handicap", "Away +0.25"): 1.89,
            ("m21", "AH", "Home -½"): 1.95,
            ("m21", "Asian Handicap", "Away +0.5"): 1.95,
        }

        implied = build_devig_implied_map(odds_map)

        self.assertAlmostEqual(
            implied[("m19", "OU", "Over 2½")] + implied[("m19", "Over/Under", "Under 2.5")],
            1.0,
            places=9,
        )
        self.assertAlmostEqual(
            implied[("m20", "AH", "Home -0¼")] + implied[("m20", "Asian Handicap", "Away +0.25")],
            1.0,
            places=9,
        )
        self.assertAlmostEqual(
            implied[("m21", "AH", "Home -½")] + implied[("m21", "Asian Handicap", "Away +0.5")],
            1.0,
            places=9,
        )


if __name__ == "__main__":
    unittest.main()
