from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pymysql

from paper.constants import LEAGUE_UNIVERSE, SOFASCORE_LEAGUE_MAP
from paper.models import MatchInfo
from paper.providers import OddsProvider, ResultsProvider, match_key, normalize_team


class HistoricalBackfillProvider(OddsProvider, ResultsProvider):
    def __init__(
        self,
        matches_sqlite: Path,
        odds_sqlite: Path,
        use_open_odds: bool = True,
    ) -> None:
        self.matches_sqlite = Path(matches_sqlite)
        self.odds_sqlite = Path(odds_sqlite)
        self.use_open_odds = bool(use_open_odds)

    @staticmethod
    def _league_key_from_name(league_name: str, league_keys: List[str]) -> str | None:
        tgt = normalize_team(league_name)
        for lk in league_keys:
            cfg = SOFASCORE_LEAGUE_MAP.get(lk) or {}
            names = []
            if cfg.get("league_name"):
                names.append(str(cfg.get("league_name")))
            names.extend(str(x) for x in (cfg.get("tournament_aliases") or []))
            for n in names:
                if normalize_team(n) == tgt:
                    return lk
        return None

    @staticmethod
    def _market_name(raw_market: str, raw_line: str) -> str | None:
        market = str(raw_market or "").strip().lower()
        line = str(raw_line or "").strip()
        if market == "1x2":
            return "1X2"
        if market == "over_under":
            return f"Over/Under {line}".strip()
        if market == "asian_handicap":
            return f"Asian Handicap {line}".strip()
        return None

    @staticmethod
    def _selection_name(raw_market: str, raw_sel: str) -> str:
        market = str(raw_market or "").strip().lower()
        sel = str(raw_sel or "").strip().lower()
        if market == "1x2":
            if sel in {"home", "1"}:
                return "Home"
            if sel in {"draw", "x"}:
                return "Draw"
            if sel in {"away", "2"}:
                return "Away"
        if market == "over_under":
            if sel.startswith("over"):
                return "Over"
            if sel.startswith("under"):
                return "Under"
        if market == "asian_handicap":
            if sel in {"home", "1"}:
                return "Home"
            if sel in {"away", "2"}:
                return "Away"
        return str(raw_sel or "")

    def fetch_matches(self, day: date, league_keys: List[str]) -> List[MatchInfo]:
        conn = sqlite3.connect(str(self.matches_sqlite))
        try:
            rows = conn.execute(
                """
                SELECT event_id, league, match_date, home_team, away_team
                FROM matches
                WHERE match_date = ?
                ORDER BY league, home_team, away_team
                """,
                (day.isoformat(),),
            ).fetchall()
        finally:
            conn.close()

        out: List[MatchInfo] = []
        for event_id, league, match_date, home_team, away_team in rows:
            league_key = self._league_key_from_name(str(league or ""), league_keys)
            if not league_key:
                continue
            out.append(
                MatchInfo(
                    match_id=f"{league_key}:{int(event_id)}",
                    league_key=league_key,
                    league_name=str(league or league_key),
                    kickoff_utc=f"{match_date}T12:00:00+00:00",
                    home_team=str(home_team or ""),
                    away_team=str(away_team or ""),
                )
            )
        return out

    def fetch_market_odds(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Dict[Tuple[str, str, str], float]:
        odds, _meta = self.fetch_market_odds_with_meta(day=day, league_keys=league_keys, matches=matches)
        return odds

    def fetch_market_odds_with_meta(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Tuple[Dict[Tuple[str, str, str], float], Dict[Tuple[str, str, str], Dict[str, Any]]]:
        event_ids = []
        for m in matches:
            try:
                event_ids.append(int(str(m.match_id).split(":", 1)[1]))
            except Exception:
                continue
        if not event_ids:
            return {}, {}

        placeholders = ",".join("?" for _ in event_ids)
        conn = sqlite3.connect(str(self.odds_sqlite))
        try:
            rows = conn.execute(
                f"""
                SELECT event_id, market, line, selection, open_decimal, current_decimal
                FROM event_odds_10y_multi
                WHERE match_date = ? AND event_id IN ({placeholders})
                ORDER BY event_id, market, line, selection
                """,
                [day.isoformat(), *event_ids],
            ).fetchall()
        finally:
            conn.close()

        odds: Dict[Tuple[str, str, str], float] = {}
        meta: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        by_event = {int(str(m.match_id).split(":", 1)[1]): m.match_id for m in matches if ":" in m.match_id}

        for event_id, market, line, selection, open_decimal, current_decimal in rows:
            market_name = self._market_name(str(market or ""), str(line or ""))
            if not market_name:
                continue
            sel_name = self._selection_name(str(market or ""), str(selection or ""))
            odd = open_decimal if self.use_open_odds else current_decimal
            try:
                odd_f = float(odd or 0.0)
            except Exception:
                odd_f = 0.0
            if odd_f <= 1.0:
                continue
            match_id = by_event.get(int(event_id))
            if not match_id:
                continue
            key = (match_id, market_name, sel_name)
            odds[key] = odd_f
            meta[key] = {
                "source": "historical_open" if self.use_open_odds else "historical_close",
                "is_real": True,
            }
        return odds, meta

    def fetch_ft_scores(self, day: date, league_keys: List[str]) -> Dict[str, Tuple[int, int]]:
        names, _ids = self.fetch_ft_scores_with_ids(day=day, league_keys=league_keys)
        return names

    def fetch_ft_scores_with_ids(self, day: date, league_keys: List[str]) -> Tuple[dict, dict]:
        conn = sqlite3.connect(str(self.matches_sqlite))
        try:
            rows = conn.execute(
                """
                SELECT event_id, league, home_team, away_team, home_goals, away_goals
                FROM matches
                WHERE match_date = ?
                """,
                (day.isoformat(),),
            ).fetchall()
        finally:
            conn.close()

        by_name: Dict[str, Tuple[int, int]] = {}
        by_id: Dict[str, Tuple[int, int]] = {}
        for event_id, league, home_team, away_team, home_goals, away_goals in rows:
            league_key = self._league_key_from_name(str(league or ""), league_keys)
            if not league_key:
                continue
            score = (int(home_goals or 0), int(away_goals or 0))
            by_name[match_key(str(home_team or ""), str(away_team or ""))] = score
            by_id[f"{league_key}:{int(event_id)}"] = score
        return by_name, by_id

class HistoricalMySQLProvider(OddsProvider, ResultsProvider):
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "appdb",
        use_open_odds: bool = True,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.user = user
        self.password = password
        self.database = database
        self.use_open_odds = bool(use_open_odds)

    def _connect(self):
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
        )

    @staticmethod
    def _league_key_from_name(league_name: str, league_keys: List[str]) -> str | None:
        return HistoricalBackfillProvider._league_key_from_name(league_name, league_keys)

    @staticmethod
    def _market_name(raw_market: str, raw_line: str) -> str | None:
        return HistoricalBackfillProvider._market_name(raw_market, raw_line)

    @staticmethod
    def _selection_name(raw_market: str, raw_sel: str) -> str:
        return HistoricalBackfillProvider._selection_name(raw_market, raw_sel)

    def fetch_matches(self, day: date, league_keys: List[str]) -> List[MatchInfo]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_id, league, match_date, home_team, away_team
                    FROM sofascore_matches_10y
                    WHERE match_date = %s
                    ORDER BY league, home_team, away_team
                    """,
                    (day.isoformat(),),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        out: List[MatchInfo] = []
        for event_id, league, match_date, home_team, away_team in rows:
            league_key = self._league_key_from_name(str(league or ""), league_keys)
            if not league_key:
                continue
            out.append(
                MatchInfo(
                    match_id=f"{league_key}:{int(event_id)}",
                    league_key=league_key,
                    league_name=str(league or league_key),
                    kickoff_utc=f"{match_date}T12:00:00+00:00",
                    home_team=str(home_team or ""),
                    away_team=str(away_team or ""),
                )
            )
        return out

    def fetch_market_odds(self, day: date, league_keys: List[str], matches: List[MatchInfo]) -> Dict[Tuple[str, str, str], float]:
        odds, _meta = self.fetch_market_odds_with_meta(day=day, league_keys=league_keys, matches=matches)
        return odds

    def fetch_market_odds_with_meta(
        self,
        day: date,
        league_keys: List[str],
        matches: List[MatchInfo],
    ) -> Tuple[Dict[Tuple[str, str, str], float], Dict[Tuple[str, str, str], Dict[str, Any]]]:
        event_ids = []
        for m in matches:
            try:
                event_ids.append(int(str(m.match_id).split(":", 1)[1]))
            except Exception:
                continue
        if not event_ids:
            return {}, {}

        conn = self._connect()
        try:
            with conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(event_ids))
                cur.execute(
                    f"""
                    SELECT event_id, market, line, selection, open_decimal, current_decimal
                    FROM sofascore_event_odds_10y_multi
                    WHERE match_date = %s AND event_id IN ({placeholders})
                    ORDER BY event_id, market, line, selection, source_id
                    """,
                    [day.isoformat(), *event_ids],
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        odds: Dict[Tuple[str, str, str], float] = {}
        meta: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        by_event = {int(str(m.match_id).split(":", 1)[1]): m.match_id for m in matches if ":" in m.match_id}
        for event_id, market, line, selection, open_decimal, current_decimal in rows:
            market_name = self._market_name(str(market or ""), str(line or ""))
            if not market_name:
                continue
            sel_name = self._selection_name(str(market or ""), str(selection or ""))
            odd = open_decimal if self.use_open_odds else current_decimal
            try:
                odd_f = float(odd or 0.0)
            except Exception:
                odd_f = 0.0
            if odd_f <= 1.0:
                continue
            match_id = by_event.get(int(event_id))
            if not match_id:
                continue
            key = (match_id, market_name, sel_name)
            odds[key] = odd_f
            meta[key] = {
                "source": "historical_open_mysql" if self.use_open_odds else "historical_close_mysql",
                "is_real": True,
            }
        return odds, meta

    def fetch_ft_scores(self, day: date, league_keys: List[str]) -> Dict[str, Tuple[int, int]]:
        names, _ids = self.fetch_ft_scores_with_ids(day=day, league_keys=league_keys)
        return names

    def fetch_ft_scores_with_ids(self, day: date, league_keys: List[str]) -> Tuple[dict, dict]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_id, league, home_team, away_team, home_goals, away_goals
                    FROM sofascore_matches_10y
                    WHERE match_date = %s
                    """,
                    (day.isoformat(),),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        by_name: Dict[str, Tuple[int, int]] = {}
        by_id: Dict[str, Tuple[int, int]] = {}
        for event_id, league, home_team, away_team, home_goals, away_goals in rows:
            league_key = self._league_key_from_name(str(league or ""), league_keys)
            if not league_key:
                continue
            score = (int(home_goals or 0), int(away_goals or 0))
            by_name[match_key(str(home_team or ""), str(away_team or ""))] = score
            by_id[f"{league_key}:{int(event_id)}"] = score
        return by_name, by_id
