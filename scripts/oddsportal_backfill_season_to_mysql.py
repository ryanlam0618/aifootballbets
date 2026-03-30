#!/usr/bin/env python3
"""Backfill OddsPortal season (match list) into MySQL (oddsportal_10y).

This script is intended for historical backfill (e.g., EPL 2015-2016).
It uses the encrypted OddsPortal `match-event-history` endpoint directly:
  https://www.oddsportal.com/match-event-history/1-<matchId>-<marketCode>-0-<bookieId>/?geo=HK&lang=en

Market codes (observed):
- 1X2: 1-2
- OU : 2-2
- AH : 5-2

It decrypts the response using the same constants as `scripts/oddsportal_decrypt_match_event.js`.

Writes to MySQL tables:
- matches (upsert by UNIQUE(competition, season, match_id))
- odds    (insert ignore by UNIQUE(match_id, market, bookie_id, selection_key, ts))

Usage:
  python3 scripts/oddsportal_backfill_season_to_mysql.py \
    --match-list /path/to/epl_2015_2016.jsonl \
    --mysql-url 'mysql://A100:PASS@192.168.0.182:3306/oddsportal_10y' \
    --competition EPL --season 2015-2016 \
    --bookies 16,27,43,44,417,500,550,575,609 \
    --markets 1x2,ou,ah \
    --limit-matches 0

Notes:
- Idempotent: safe to rerun.
- Best-effort: continues on per-match errors.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

import mysql.connector
import requests
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import PBKDF2

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# From app bundle (see scripts/oddsportal_decrypt_match_event.js)
_PASSWORD = "J*8sQ!p$7aD_fR2yW@gHn*3bVp#sAdLd_k"
_SALT = "5b9a8f2c3e6d1a4b7c8e9d0f1a2b3c4d"
_ITER = 1000
_KEYLEN = 32  # 256-bit

MARKET_TO_CODE = {
    "1x2": "1-2",
    "ou": "2-2",
    "ah": "5-2",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_match_id(match_url: str) -> str:
    seg = (match_url or "").rstrip("/").split("/")[-1]
    return seg.split("-")[-1]


@dataclass
class MySQLConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


def parse_mysql_url(mysql_url: str) -> MySQLConfig:
    u = urlparse(mysql_url)
    if u.scheme != "mysql":
        raise ValueError("mysql-url must start with mysql://")
    host = u.hostname or "localhost"
    port = int(u.port or 3306)
    user = unquote(u.username or "")
    password = unquote(u.password or "")
    database = (u.path or "/").lstrip("/")
    if not user or not database:
        raise ValueError("mysql-url must include user and database")
    return MySQLConfig(host=host, port=port, user=user, password=password, database=database)


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict):
                    yield obj
            except Exception:
                continue


def _derive_key() -> bytes:
    return PBKDF2(_PASSWORD.encode("utf-8"), _SALT.encode("utf-8"), dkLen=_KEYLEN, count=_ITER, hmac_hash_module=SHA256)


_KEY = _derive_key()


def decrypt_oddsportal(enc: str) -> dict[str, Any]:
    # enc is base64 of "<cipher_b64>:<iv_hex>" bytes
    dec = base64.b64decode(enc.strip()).decode("latin1")
    parts = dec.split(":")
    if len(parts) != 2:
        raise ValueError("encrypted payload does not decode to <b64>:<ivhex>")
    cipher_b64, iv_hex = parts
    iv = bytes.fromhex(iv_hex.strip())
    cipher_bytes = base64.b64decode(cipher_b64.strip())
    cipher = AES.new(_KEY, AES.MODE_CBC, iv)
    plain = cipher.decrypt(cipher_bytes)
    # PKCS7 unpad
    pad = plain[-1]
    if pad <= 0 or pad > 16:
        raise ValueError("bad padding")
    plain = plain[:-pad]
    txt = plain.decode("utf-8")
    return json.loads(txt)


# ----- HTTP (thread-friendly) -----

def _jitter_sleep(base_s: float, jitter_s: float) -> None:
    if base_s <= 0:
        return
    time.sleep(base_s + random.random() * max(0.0, jitter_s))


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Accept-Encoding": "identity",
        }
    )
    return s


def fetch_mehist(session: requests.Session, match_id: str, market_code: str, bookie_id: int, geo: str, lang: str, timeout: int = 30) -> dict[str, Any]:
    url = f"https://www.oddsportal.com/match-event-history/1-{match_id}-{market_code}-0-{bookie_id}/?geo={geo}&lang={lang}"
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    return decrypt_oddsportal(r.text.strip())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill OddsPortal season matchlist into MySQL oddsportal_10y")
    p.add_argument("--match-list", required=True, help="jsonl generated by v2/tracking/oddsportal_season_matchlist.py")
    p.add_argument("--mysql-url", required=True)
    p.add_argument("--competition", required=True)
    p.add_argument("--season", required=True)
    p.add_argument("--markets", default="1x2,ou,ah")
    p.add_argument("--bookies", default="16,27,43,44,417,500,550,575,609")
    p.add_argument("--geo", default="HK")
    p.add_argument("--lang", default="en")
    p.add_argument("--limit-matches", type=int, default=0)

    # Conservative parallelism controls (HTTP is I/O bound).
    p.add_argument("--workers", type=int, default=1, help="Parallel HTTP workers per match (default 1; conservative 2)")
    p.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds (default 30)")
    p.add_argument("--sleep-ms", type=int, default=0, help="Sleep after each match commit (ms)")
    p.add_argument("--req-sleep-ms", type=int, default=0, help="Base sleep before each HTTP request (ms)")
    p.add_argument("--req-jitter-ms", type=int, default=50, help="Extra random jitter added to req sleep (ms)")
    p.add_argument("--max-retries", type=int, default=2, help="Retries for 429/5xx per request (default 2)")
    p.add_argument("--backoff-base-ms", type=int, default=800, help="Base backoff for retries (ms)")

    p.add_argument("--progress-every", type=int, default=10)
    return p.parse_args()


def _should_retry_http(e: Exception) -> bool:
    resp = getattr(e, "response", None)
    code = getattr(resp, "status_code", None)
    if code in (429, 500, 502, 503, 504):
        return True
    # requests exceptions without status_code: treat as retryable once/twice
    return isinstance(e, (requests.Timeout, requests.ConnectionError))


def _fetch_with_retry(
    session: requests.Session,
    match_id: str,
    market_code: str,
    bookie_id: int,
    geo: str,
    lang: str,
    timeout: int,
    req_sleep_s: float,
    req_jitter_s: float,
    max_retries: int,
    backoff_base_s: float,
) -> dict[str, Any] | None:
    for attempt in range(max_retries + 1):
        try:
            if req_sleep_s > 0:
                _jitter_sleep(req_sleep_s, req_jitter_s)
            return fetch_mehist(session, match_id, market_code, bookie_id, geo=geo, lang=lang, timeout=timeout)
        except Exception as e:
            if attempt >= max_retries or not _should_retry_http(e):
                return None
            _jitter_sleep(backoff_base_s * (2**attempt), 0.25)
    return None


def main() -> int:
    args = parse_args()

    markets = [m.strip().lower() for m in args.markets.split(",") if m.strip()]
    for m in markets:
        if m not in MARKET_TO_CODE:
            raise SystemExit(f"unknown market: {m}")

    bookies = [int(x.strip()) for x in args.bookies.split(",") if x.strip()]
    if not bookies:
        raise SystemExit("no bookies")

    rows = list(iter_jsonl(Path(args.match_list)))
    if args.limit_matches and args.limit_matches > 0:
        rows = rows[: args.limit_matches]

    workers = max(1, int(args.workers or 1))
    if workers > 4:
        # hard safety cap: OddsPortal is easy to rate-limit; keep conservative.
        workers = 4

    req_sleep_s = max(0.0, float(args.req_sleep_ms or 0) / 1000.0)
    req_jitter_s = max(0.0, float(args.req_jitter_ms or 0) / 1000.0)
    backoff_base_s = max(0.05, float(args.backoff_base_ms or 800) / 1000.0)

    cfg = parse_mysql_url(args.mysql_url)
    cn = mysql.connector.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        autocommit=False,
    )
    cur = cn.cursor()

    started = utc_now()
    ok_matches = 0
    err_matches = 0
    inserted_odds = 0

    # shared session per worker thread
    _tls = threading.local()

    def _get_session() -> requests.Session:
        s = getattr(_tls, "session", None)
        if s is None:
            s = make_session()
            _tls.session = s
        return s

    def _fetch_one(market: str, b: int, mid: str) -> tuple[str, int, dict[str, Any] | None]:
        session = _get_session()
        market_code = MARKET_TO_CODE[market]
        d = _fetch_with_retry(
            session,
            mid,
            market_code,
            b,
            geo=args.geo,
            lang=args.lang,
            timeout=int(args.timeout or 30),
            req_sleep_s=req_sleep_s,
            req_jitter_s=req_jitter_s,
            max_retries=int(args.max_retries or 0),
            backoff_base_s=backoff_base_s,
        )
        return (market, b, d)

    for i, row in enumerate(rows, start=1):
        match_url = str(row.get("match_url") or "")
        if not match_url:
            continue
        mid = parse_match_id(match_url)
        if not mid:
            continue

        try:
            # upsert match
            cur.execute(
                """
                INSERT INTO matches(competition, season, match_id, match_url, match_date_utc, home_team, away_team, scraped_at_utc)
                VALUES(%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP())
                ON DUPLICATE KEY UPDATE
                  match_url=VALUES(match_url),
                  match_date_utc=COALESCE(VALUES(match_date_utc), match_date_utc),
                  home_team=COALESCE(VALUES(home_team), home_team),
                  away_team=COALESCE(VALUES(away_team), away_team),
                  scraped_at_utc=VALUES(scraped_at_utc)
                """,
                (
                    args.competition,
                    args.season,
                    mid,
                    match_url,
                    (row.get("match_date_utc") or None),
                    (row.get("home_team") or None),
                    (row.get("away_team") or None),
                ),
            )

            # odds fetch (parallel) -> write (single-thread)
            tasks: list[tuple[str, int]] = [(m, b) for m in markets for b in bookies]
            results: list[tuple[str, int, dict[str, Any] | None]] = []

            if workers == 1 or len(tasks) <= 1:
                for m, b in tasks:
                    results.append(_fetch_one(m, b, mid))
            else:
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futs = [ex.submit(_fetch_one, m, b, mid) for (m, b) in tasks]
                    for fut in as_completed(futs):
                        try:
                            results.append(fut.result())
                        except Exception:
                            # ignore a single failed request
                            continue

            for market, b, d in results:
                if not d:
                    continue

                back = (((d.get("d") or {}).get("history") or {}).get("back"))
                if not isinstance(back, dict):
                    continue

                for sel_key, inner in back.items():
                    if not isinstance(inner, dict):
                        continue
                    arr = inner.get(str(b))
                    if not isinstance(arr, list):
                        continue

                    ou_side_base = None
                    ou_line_code = None
                    if market == "ou":
                        parts = str(sel_key).split("x")
                        if len(parts) == 3:
                            ou_side_base, ou_line_code = parts[0], parts[1]

                    for trip in arr:
                        try:
                            odd_str, _zero, ts = trip
                            ts = int(ts)
                            odd = float(str(odd_str))
                        except Exception:
                            continue
                        cur.execute(
                            """
                            INSERT IGNORE INTO odds(
                              competition, season, match_date_utc, home_team, away_team, match_url,
                              match_id, market, bookie_id, selection_key,
                              ou_side_base, ou_line_code,
                              ts, ts_utc, odds
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            (
                                args.competition,
                                args.season,
                                None,
                                (row.get("home_team") or None),
                                (row.get("away_team") or None),
                                match_url,
                                mid,
                                market,
                                b,
                                str(sel_key),
                                ou_side_base,
                                ou_line_code,
                                ts,
                                iso_utc(ts),
                                odd,
                            ),
                        )
                        inserted_odds += cur.rowcount

            cn.commit()
            ok_matches += 1
        except Exception:
            cn.rollback()
            err_matches += 1

        if args.sleep_ms and args.sleep_ms > 0:
            time.sleep(args.sleep_ms / 1000.0)

        if args.progress_every and (i % int(args.progress_every) == 0):
            elapsed = (utc_now() - started).total_seconds()
            print(
                json.dumps(
                    {
                        "processed": i,
                        "total": len(rows),
                        "ok_matches": ok_matches,
                        "err_matches": err_matches,
                        "inserted_odds": inserted_odds,
                        "elapsed_sec": round(elapsed, 1),
                        "last_match_id": mid,
                        "workers": workers,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    elapsed = (utc_now() - started).total_seconds()
    print(
        json.dumps(
            {
                "done": True,
                "processed": len(rows),
                "ok_matches": ok_matches,
                "err_matches": err_matches,
                "inserted_odds": inserted_odds,
                "elapsed_sec": round(elapsed, 1),
                "workers": workers,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    cur.close()
    cn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
