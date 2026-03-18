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


if __name__ == "__main__":
    unittest.main()
