from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from v2.ingest.oddsportal_tracker import load_latest_quotes


def _mk_tracker_sqlite(p: Path) -> None:
    con = sqlite3.connect(str(p))
    try:
        con.executescript(
            """
            create table odds_match (
              id integer primary key,
              match_url text,
              market text,
              label text
            );
            create table odds_snapshot (
              id integer primary key,
              match_id integer,
              snapshot_ts_utc text,
              success integer,
              quote_count integer,
              error text
            );
            create table odds_quote (
              id integer primary key,
              snapshot_id integer,
              bookmaker text,
              market_type text,
              line real,
              home real,
              draw real,
              away real
            );
            """
        )
        con.execute("insert into odds_match(id, match_url, market, label) values (1, ?, '1X2', 'EPL')", ("https://www.oddsportal.com/football/england/premier-league/bournemouth-man-united-abc/",))
        con.execute("insert into odds_snapshot(id, match_id, snapshot_ts_utc, success, quote_count, error) values (10, 1, '2026-03-20T10:00:00+00:00', 1, 2, '')")
        # two bookmakers
        con.execute(
            "insert into odds_quote(snapshot_id, bookmaker, market_type, line, home, draw, away) values (10,'bk1','1X2',null, 3.0, 3.4, 2.2)"
        )
        con.execute(
            "insert into odds_quote(snapshot_id, bookmaker, market_type, line, home, draw, away) values (10,'bk2','1X2',null, 3.2, 3.6, 2.1)"
        )
        con.commit()
    finally:
        con.close()


def test_load_latest_quotes_basic(tmp_path: Path) -> None:
    db = tmp_path / "tracker.sqlite"
    _mk_tracker_sqlite(db)

    fixtures_df = pd.DataFrame(
        [
            {
                "match_id": "m1",
                "home_team": "Bournemouth",
                "away_team": "Manchester United",
                "league_key": "soccer_epl",
            }
        ]
    )

    out = load_latest_quotes(db, fixtures_df)
    assert out[("m1", "1X2", "Home")] == (3.0 + 3.2) / 2
    assert out[("m1", "1X2", "Draw")] == (3.4 + 3.6) / 2
    assert out[("m1", "1X2", "Away")] == (2.2 + 2.1) / 2
