import json
from pathlib import Path

import pytest

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


class _FakeClientFallback404:
    def __init__(self):
        self.lineup_calls: list[int] = []

    def scheduled_events(self, _date):
        return {
            "events": [
                {
                    "id": 111,
                    "homeTeam": {"name": "Club Necaxa"},
                    "awayTeam": {"name": "Club Tijuana"},
                    "startTimestamp": 1774054800,
                },
                {
                    "id": 222,
                    "homeTeam": {"name": "Club Necaxa"},
                    "awayTeam": {"name": "Club Tijuana"},
                    "startTimestamp": 1774058400,
                },
            ]
        }

    def lineups(self, event_id):
        self.lineup_calls.append(int(event_id))
        if int(event_id) == 111:
            raise Exception("404 Not Found")
        assert int(event_id) == 222
        return {
            "confirmed": True,
            "home": {"players": [{"player": {"id": 1, "name": "H1"}, "substitute": False}], "missingPlayers": []},
            "away": {"players": [{"player": {"id": 2, "name": "A1"}, "substitute": False}], "missingPlayers": []},
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


def test_resolve_event_handles_accented_names_with_ascii_query():
    scheduled = {
        "events": [
            {
                "id": 2002,
                "homeTeam": {"name": "Atlético Tucumán"},
                "awayTeam": {"name": "Gimnasia y Esgrima"},
                "startTimestamp": 1774051200,
            }
        ]
    }
    client = _FakeClient(scheduled)

    resolved = resolve_event(
        "Atletico Tucuman",
        "Gimnasia y Esgrima",
        "2026-03-20",
        client=client,
        kickoff_time_utc="2026-03-21T00:00:00Z",
    )

    assert resolved is not None
    assert resolved.event_id == 2002
    assert resolved.confidence >= 0.7


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


def test_fetch_fallbacks_when_best_event_lineups_404(monkeypatch):
    from v2.ingest import sofascore_lineup as mod

    fake_client = _FakeClientFallback404()

    class _ClientFactory:
        def __call__(self, *args, **kwargs):
            return fake_client

    monkeypatch.setattr(mod, "SofaScoreClient", _ClientFactory())

    out = fetch_lineup_and_injury(
        home_team="Club Necaxa",
        away_team="Club Tijuana",
        match_date="2026-03-20",
        kickoff_time_utc="2026-03-21T01:00:00Z",
    )

    assert out["lineup"]["source"] == "sofascore"
    assert len(out["lineup"]["home_team"]["starters"]) == 1
    assert len(out["lineup"]["away_team"]["starters"]) == 1
    assert fake_client.lineup_calls == [111, 222]


def test_client_retries_429_then_succeeds(monkeypatch, tmp_path: Path):
    from v2.ingest import sofascore_lineup as mod

    class _Resp:
        def __init__(self, status_code: int, payload: dict, headers=None):
            self.status_code = status_code
            self._payload = payload
            self.headers = headers or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise _HTTPStatusError(self)

        def json(self):
            return self._payload

    class _HTTPStatusError(Exception):
        def __init__(self, response):
            super().__init__(f"HTTP {response.status_code}")
            self.response = response

    class _RequestError(Exception):
        pass

    class _Client:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        def get(self, _url):
            self.calls += 1
            if self.calls == 1:
                return _Resp(429, {}, headers={"Retry-After": "0"})
            return _Resp(200, {"events": [{"id": 1}]})

        def close(self):
            return None

    class _Timeout:
        def __init__(self, _v):
            pass

    class _FakeHttpx:
        Client = _Client
        Timeout = _Timeout
        HTTPStatusError = _HTTPStatusError
        RequestError = _RequestError

    sleeps: list[float] = []
    monkeypatch.setattr(mod, "httpx", _FakeHttpx)
    monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(float(s)))

    c = mod.SofaScoreClient(raw_dir=tmp_path, sleep_s=0.0, max_retries=2, retry_backoff_s=0.01)
    out = c.scheduled_events("2026-03-21")
    c.close()

    assert out["events"][0]["id"] == 1
    assert any(s >= 0.01 for s in sleeps)
    assert (tmp_path / "scheduled-events_2026-03-21.json").exists()


def test_client_non_retryable_404_raises(monkeypatch):
    from v2.ingest import sofascore_lineup as mod

    class _Resp:
        def __init__(self, status_code: int):
            self.status_code = status_code
            self.headers = {}

        def raise_for_status(self):
            raise _HTTPStatusError(self)

    class _HTTPStatusError(Exception):
        def __init__(self, response):
            super().__init__(f"HTTP {response.status_code}")
            self.response = response

    class _RequestError(Exception):
        pass

    class _Client:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        def get(self, _url):
            self.calls += 1
            return _Resp(404)

        def close(self):
            return None

    class _Timeout:
        def __init__(self, _v):
            pass

    class _FakeHttpx:
        Client = _Client
        Timeout = _Timeout
        HTTPStatusError = _HTTPStatusError
        RequestError = _RequestError

    monkeypatch.setattr(mod, "httpx", _FakeHttpx)
    c = mod.SofaScoreClient(sleep_s=0.0, max_retries=3, retry_backoff_s=0.01)
    with pytest.raises(_HTTPStatusError):
        c.scheduled_events("2026-03-21")
    c.close()
