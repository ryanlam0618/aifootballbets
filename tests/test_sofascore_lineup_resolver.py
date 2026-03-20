import json
from pathlib import Path

from v2.ingest.sofascore_lineup import (
    EventIdCache,
    _best_event_by_fuzzy,
    fetch_lineup_and_injury,
    resolve_event,
)


class _FakeClient:
    def __init__(self, scheduled, lineups=None):
        self._scheduled = scheduled
        self._lineups = lineups or {}

    def scheduled_events(self, _date):
        return self._scheduled

    def lineups(self, event_id):
        return self._lineups[int(event_id)]


class _FakeClientWithRetry:
    def __init__(self):
        self.calls = 0

    def lineups(self, event_id):
        self.calls += 1
        assert event_id == 999
        return {
            "confirmed": True,
            "home": {"players": [], "missingPlayers": []},
            "away": {"players": [], "missingPlayers": []},
        }

    def close(self):
        return None


def test_best_event_prefers_kickoff_tolerance():
    events = [
        {
            "id": 1,
            "homeTeam": {"name": "Manchester United"},
            "awayTeam": {"name": "Liverpool"},
            "startTimestamp": 1700000000,
        },
        {
            "id": 2,
            "homeTeam": {"name": "Manchester Utd FC"},
            "awayTeam": {"name": "Liverpool FC"},
            "startTimestamp": 1700003600,
        },
    ]

    best = _best_event_by_fuzzy(
        "Man United",
        "Liverpool",
        events,
        kickoff_time_utc="2023-11-14T23:13:20Z",  # 1700003600
        kickoff_tolerance_minutes=120,
    )

    assert best is not None
    assert int(best.event["id"]) == 2
    assert best.confidence > 0.7


def test_resolve_event_returns_confidence_when_name_normalized():
    scheduled = {
        "events": [
            {
                "id": 1001,
                "homeTeam": {"name": "Sporting CP"},
                "awayTeam": {"name": "FC Porto"},
                "startTimestamp": 1710000000,
            }
        ]
    }
    client = _FakeClient(scheduled)

    resolved = resolve_event(
        "Sporting Clube de Portugal",
        "Porto",
        "2024-03-09",
        client=client,
        kickoff_time_utc="2024-03-09T16:00:00Z",
    )

    assert resolved is not None
    assert resolved.event_id == 1001
    assert resolved.confidence >= 0.62


def test_event_id_cache_roundtrip(tmp_path: Path):
    cache = EventIdCache(tmp_path / "cache.json")
    cache.set_event(
        match_id="m1",
        event_id=123,
        confidence=0.81,
        home_team="A",
        away_team="B",
        match_date="2024-01-01",
        kickoff_time_utc="2024-01-01T18:00:00Z",
    )

    assert cache.get_event_id("m1") == 123

    payload = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    assert payload["m1"]["confidence"] == 0.81


def test_fetch_uses_cached_event_id_without_scheduled_lookup(monkeypatch, tmp_path: Path):
    from v2.ingest import sofascore_lineup as mod

    cache_path = tmp_path / "sofa_cache.json"
    cache = EventIdCache(cache_path)
    cache.set_event(
        match_id="match-42",
        event_id=999,
        confidence=0.9,
        home_team="Home",
        away_team="Away",
        match_date="2024-01-01",
    )

    fake_client = _FakeClientWithRetry()

    class _ClientFactory:
        def __call__(self, *args, **kwargs):
            return fake_client

    monkeypatch.setattr(mod, "SofaScoreClient", _ClientFactory())

    out = fetch_lineup_and_injury(
        home_team="Home",
        away_team="Away",
        match_date="2024-01-01",
        match_id="match-42",
        event_cache_path=cache_path,
    )

    assert out["lineup"]["source"] == "sofascore"
    assert fake_client.calls == 1
