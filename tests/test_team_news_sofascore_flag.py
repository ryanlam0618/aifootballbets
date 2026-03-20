from v2.ingest import sofascore_lineup as sofa
from v2.ingest import team_news


def test_collect_lineup_default_off_does_not_call_sofascore(monkeypatch):
    monkeypatch.delenv("SOFASCORE_ENABLED", raising=False)

    called = {"n": 0}

    def _should_not_be_called(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("fetch_lineup_and_injury should not run when SOFASCORE_ENABLED is unset")

    monkeypatch.setattr(sofa, "fetch_lineup_and_injury", _should_not_be_called)

    out = team_news.collect_lineup_and_injury("Home", "Away", "2026-03-20")

    assert called["n"] == 0
    assert out["lineup"]["source"] == "v2-standalone-fallback"
    assert out["injury"]["source"] == "v2-standalone-fallback"


def test_collect_lineup_enabled_calls_sofascore(monkeypatch):
    monkeypatch.setenv("SOFASCORE_ENABLED", "1")

    called = {"n": 0}

    def _fake_fetch(*args, **kwargs):
        called["n"] += 1
        return {
            "lineup": {
                "home_team": {"name": "Home", "formation": "4-3-3", "starters": [], "substitutes": []},
                "away_team": {"name": "Away", "formation": "4-4-2", "starters": [], "substitutes": []},
                "source": "sofascore",
            },
            "injury": {
                "home": {"injuries": [], "suspensions": [], "total_impact": 0.0},
                "away": {"injuries": [], "suspensions": [], "total_impact": 0.0},
                "source": "sofascore",
            },
            "sofascore_features": {
                "lineup_confirmed": False,
                "home": {"missing_count": 0, "doubtful_count": 0, "missing_by_position": {}},
                "away": {"missing_count": 0, "doubtful_count": 0, "missing_by_position": {}},
            },
        }

    monkeypatch.setattr(sofa, "fetch_lineup_and_injury", _fake_fetch)

    out = team_news.collect_lineup_and_injury("Home", "Away", "2026-03-20")

    assert called["n"] == 1
    assert out["lineup"]["source"] == "sofascore"
