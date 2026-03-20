import copy

from v2.ingest.sofascore_lineup import parse_lineups_to_schema


def test_parse_new_lineups_format_players_and_missing_players():
    raw = {
        "confirmed": True,
        "home": {
            "formation": "4-3-3",
            "players": [
                {
                    "player": {"id": 1, "name": "Home Starter", "position": "F"},
                    "shirtNumber": 9,
                    "position": "F",
                    "substitute": False,
                    "avgRating": 7.1,
                },
                {
                    "player": {"id": 2, "name": "Home Sub", "position": "M"},
                    "shirtNumber": 18,
                    "position": "M",
                    "substitute": True,
                    "avgRating": 6.8,
                },
            ],
            "missingPlayers": [
                {
                    "player": {"id": 10, "name": "Home Injured", "position": "D"},
                    "type": "missing",
                    "description": "Knee injury",
                    "expectedEndDate": "2024-01-10",
                },
                {
                    "player": {"id": 11, "name": "Home Suspended", "position": "M"},
                    "type": "missing",
                    "description": "Suspended",
                    "expectedEndDate": "2024-01-05",
                },
            ],
        },
        "away": {
            "formation": "4-4-2",
            "players": [
                {
                    "player": {"id": 3, "name": "Away Starter", "position": "G"},
                    "shirtNumber": 1,
                    "position": "G",
                    "substitute": False,
                    "avgRating": 6.5,
                }
            ],
            "missingPlayers": [],
        },
    }

    out = parse_lineups_to_schema(raw, home_team_name="Home FC", away_team_name="Away FC")

    assert out["lineup"]["home_team"]["formation"] == "4-3-3"
    assert out["lineup"]["away_team"]["formation"] == "4-4-2"

    assert len(out["lineup"]["home_team"]["starters"]) == 1
    assert len(out["lineup"]["home_team"]["substitutes"]) == 1

    assert out["lineup"]["home_team"]["starters"][0]["name"] == "Home Starter"
    assert out["lineup"]["home_team"]["substitutes"][0]["name"] == "Home Sub"

    # missingPlayers -> injury/suspension buckets
    assert len(out["injury"]["home"]["injuries"]) == 1
    assert len(out["injury"]["home"]["suspensions"]) == 1

    names_inj = [x["name"] for x in out["injury"]["home"]["injuries"]]
    names_sus = [x["name"] for x in out["injury"]["home"]["suspensions"]]
    assert "Home Injured" in names_inj
    assert "Home Suspended" in names_sus

    # feature payload for downstream join
    feats = out["sofascore_features"]
    assert feats["lineup_confirmed"] is True
    assert feats["home"]["missing_count"] == 2
    assert feats["home"]["doubtful_count"] == 0
    assert feats["home"]["missing_by_position"]["D"] == 1
    assert feats["home"]["missing_by_position"]["M"] == 1


def test_parse_old_lineups_format_starters_subs():
    raw = {
        "lineups": [
            {
                "isHome": True,
                "formation": {"name": "3-5-2"},
                "starters": [
                    {
                        "player": {"id": 21, "name": "Old Home Starter"},
                        "shirtNumber": 7,
                        "position": "F",
                        "rating": 7.0,
                    }
                ],
                "substitutes": [
                    {
                        "player": {"id": 22, "name": "Old Home Sub"},
                        "shirtNumber": 15,
                        "position": "M",
                        "rating": None,
                    }
                ],
                "missingPlayers": [
                    {
                        "player": {"id": 23, "name": "Old Home Missing"},
                        "type": "missing",
                        "description": "Injury",
                    }
                ],
            },
            {
                "isHome": False,
                "formation": {"name": "4-2-3-1"},
                "starters": [],
                "substitutes": [],
            },
        ]
    }

    out = parse_lineups_to_schema(raw, home_team_name="Home", away_team_name="Away")

    assert out["lineup"]["home_team"]["formation"] == "3-5-2"
    assert out["lineup"]["away_team"]["formation"] == "4-2-3-1"

    assert out["lineup"]["home_team"]["starters"][0]["name"] == "Old Home Starter"
    assert out["lineup"]["home_team"]["substitutes"][0]["name"] == "Old Home Sub"

    assert len(out["injury"]["home"]["injuries"]) == 1
    assert out["injury"]["home"]["injuries"][0]["name"] == "Old Home Missing"


def test_parse_handles_non_dict_input_gracefully():
    out = parse_lineups_to_schema(None, home_team_name="H", away_team_name="A")
    assert out["lineup"]["home_team"]["name"] == "H"
    assert out["lineup"]["away_team"]["name"] == "A"
    assert out["injury"]["source"]
