#!/usr/bin/env python3
"""Generate OddsPortal 25-competition run plan (competition x seasons).

This reads data/oddsportal_competitions_25.yml and appdb SofaScore season availability
and prints a JSON plan that can drive matchlist scraping + backfill.

We intentionally align target seasons to SofaScore, so OddsPortal date sync can be done.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any

import pymysql
import yaml


@dataclass
class MysqlCfg:
    host: str
    port: int
    user: str
    password: str
    database: str


def parse_mysql_url(url: str) -> MysqlCfg:
    # minimal parser for mysql://user:pass@host:port/db
    if not url.startswith("mysql://"):
        raise SystemExit("--mysql-url must start with mysql://")
    rest = url[len("mysql://") :]
    cred, rest = rest.split("@", 1)
    user, password = cred.split(":", 1)
    hostport, db = rest.split("/", 1)
    if ":" in hostport:
        host, port_s = hostport.split(":", 1)
        port = int(port_s)
    else:
        host, port = hostport, 3306
    return MysqlCfg(host=host, port=port, user=user, password=password, database=db)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="data/oddsportal_competitions_25.yml")
    ap.add_argument(
        "--appdb-mysql-url",
        default="mysql://A100:hksfl1512@192.168.0.182:3306/appdb",
        help="SofaScore appdb mysql url",
    )
    ap.add_argument("--format", choices=["json"], default="json")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.cfg, "r", encoding="utf-8"))
    comps = cfg["competitions"]

    mcfg = parse_mysql_url(args.appdb_mysql_url)
    conn = pymysql.connect(
        host=mcfg.host,
        port=mcfg.port,
        user=mcfg.user,
        password=mcfg.password,
        database=mcfg.database,
        connect_timeout=10,
        read_timeout=60,
        write_timeout=60,
    )

    cur = conn.cursor()

    plan: list[dict[str, Any]] = []
    for c in comps:
        league = c["sofascore"]["league"]
        cur.execute(
            "SELECT DISTINCT season FROM sofascore_matches_10y WHERE league=%s ORDER BY season",
            (league,),
        )
        seasons = [r[0] for r in cur.fetchall()]
        plan.append(
            {
                "key": c["key"],
                "canonical_name": c["canonical_name"],
                "sofascore_league": league,
                "seasons": seasons,
                "oddsportal_url_templates": c["oddsportal"].get("url_templates") or [],
            }
        )

    cur.close()
    conn.close()

    print(json.dumps({"version": 1, "competitions": plan}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
