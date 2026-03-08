import pandas as pd

from v2.models.predict import predict_markets
from v2.risk.allocator import allocate_stakes


def test_v2_predict_and_allocate_smoke():
    features = pd.DataFrame(
        [
            {
                "match_id": "m1",
                "league": "EPL",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "home_xg_avg_5": 1.8,
                "away_xg_avg_5": 1.1,
            }
        ]
    )
    odds_map = {
        ("m1", "1X2", "Home"): 1.90,
        ("m1", "1X2", "Draw"): 3.60,
        ("m1", "1X2", "Away"): 4.10,
        ("m1", "Over/Under 2.5", "Over"): 1.95,
        ("m1", "Over/Under 2.5", "Under"): 1.95,
        ("m1", "Asian Handicap -0.5", "Home"): 1.92,
        ("m1", "Asian Handicap -0.5", "Away"): 1.98,
    }

    pred = predict_markets(features, odds_map)
    assert not pred.empty
    assert {"market", "selection", "edge", "ev", "odds"}.issubset(set(pred.columns))

    out = allocate_stakes(pred, bankroll=1000)
    assert "suggested_stake" in out.columns
    assert "bankroll_pct" in out.columns
