#!/usr/bin/env python3
"""Layer-2 afb-T5 ⑤: odds coverage inventory (per competition).

Answers, per competition:
- how many finished matches have historical 1x2 odds (match_odds)
- odds coverage ratio
- whether CLV snapshots are possible (odds-bearing AND upcoming/finished
  matches still within snapshot reach — i.e. the competition has ANY odds)
- which competitions have NO odds coverage at all

Read-only; writes reports/odds_coverage_inventory.md (+ prints a summary).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Odds coverage inventory per competition")
    p.add_argument("--out", type=Path, default=REPO_ROOT / "reports" / "odds_coverage_inventory.md")
    args = p.parse_args()

    conn = afb_mysql_connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.name,
               COUNT(*) AS total_finished,
               SUM(CASE WHEN o.odds_id IS NOT NULL THEN 1 ELSE 0 END) AS with_odds
        FROM matches m
        JOIN competitions c ON c.competition_id = m.competition_id
        LEFT JOIN (
            SELECT DISTINCT match_id, MIN(odds_id) AS odds_id
            FROM match_odds
            WHERE odds_type = '1x2'
            GROUP BY match_id
        ) o ON o.match_id = m.match_id
        WHERE m.status = 'finished'
        GROUP BY c.name
        ORDER BY with_odds DESC, total_finished DESC
        """
    )
    rows = cur.fetchall()

    # snapshot feasibility: does match_odds contain ANY 1x2 price rows per comp
    # (matches with odds can be snapshotted going forward too — the market
    # feeds follow the competitions, so historical presence is the proxy)
    lines = [
        "# ODDS COVERAGE INVENTORY (afb-T5 ⑤)",
        f"generated: {datetime.utcnow().isoformat(timespec='seconds')}Z",
        "",
        "per competition (finished matches): total | with 1x2 odds | coverage | CLV snapshot possible",
        "",
    ]
    inventory = []
    for name, total, with_odds in rows:
        cov = float(with_odds or 0) / float(total) if total else 0.0
        clv = "YES" if with_odds and with_odds > 0 else "NO"
        lines.append(f"- {name}: {total} | {with_odds} | {cov:.1%} | {clv}")
        inventory.append(
            {"competition": name, "finished_matches": int(total), "with_1x2_odds": int(with_odds or 0),
             "coverage": round(cov, 4), "clv_snapshot_possible": clv == "YES"}
        )
    no_odds = [i for i in inventory if i["with_1x2_odds"] == 0]
    lines.append("")
    lines.append(f"## summary: {len(inventory)} competitions; {len(no_odds)} with ZERO odds coverage")
    for i in no_odds:
        lines.append(f"- NO COVERAGE: {i['competition']} ({i['finished_matches']} finished matches)")
    lines.append("")
    lines.append("## expansion candidates (0% coverage, most matches first)")
    for i in sorted(no_odds, key=lambda x: -x["finished_matches"]):
        lines.append(f"- {i['competition']}: {i['finished_matches']} matches — add a bookmaker feed covering this competition")

    out_md = Path(args.out)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_json = out_md.with_suffix(".json")
    out_json.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] wrote {out_md}")
    print(f"[done] wrote {out_json}")
    print(f"[summary] {len(inventory)} competitions, {len(no_odds)} with zero odds coverage")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
