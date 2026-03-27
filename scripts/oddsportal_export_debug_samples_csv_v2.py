#!/usr/bin/env python3
"""Export OddsPortal debug sample matches to readable CSV.

This version avoids Playwright (fast) and adds:
- home_team / away_team from the decrypted tournament archive page
- market label
- OU line_code + side_base fields (best-effort)

It fetches match-event-history directly for a fixed set of bookies.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Optional

import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


def iso_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def parse_match_id(match_url: str) -> str:
    seg = match_url.rstrip("/").split("/")[-1]
    return seg.split("-")[-1]


def decrypt_payload(enc: str, decrypt_js: str) -> dict[str, Any]:
    p = subprocess.run(["node", decrypt_js], input=enc, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "decrypt failed")
    return json.loads(p.stdout)


def fetch_archive_row(sample: dict[str, Any], decrypt_js: str) -> dict[str, Any]:
    """Refetch + decrypt the archive page and find the row for match_url."""
    base = sample["archive_base"].rstrip("/")
    page = int(sample["archive_page"])
    match_url = sample["match_url"]

    url = f"{base}/page/{page}/"
    r = requests.get(url, headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"}, timeout=30)
    r.raise_for_status()
    j = decrypt_payload(r.text.strip(), decrypt_js)

    target_path = match_url.replace("https://www.oddsportal.com", "")
    for row in j["d"]["rows"]:
        if row.get("url") == target_path:
            return row

    # fallback: match by match_id suffix
    mid = parse_match_id(match_url)
    for row in j["d"]["rows"]:
        if isinstance(row.get("url"), str) and row["url"].rstrip("/").endswith("-" + mid):
            return row

    raise RuntimeError(f"archive row not found for {match_url}")


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


@dataclass
class RawRow:
    match_date_utc: str
    home_team: str
    away_team: str
    match_url: str
    match_id: str
    market: str
    bookie_id: int
    selection_key: str
    ou_side_base: str
    ou_line_code: str
    ts: int
    ts_utc: str
    odds: float


def fetch_mehist(match_id: str, market_code: str, bookie_id: int, fetch_py: str) -> dict[str, Any]:
    # market_code is like '1-2' (1X2/AH snapshot) or '2-2' (OU)
    url = f"https://www.oddsportal.com/match-event-history/1-{match_id}-{market_code}-0-{bookie_id}/?geo=HK&lang=en"
    out = f"/home/openclaw/.openclaw/workspace/tmp/oddsportal_mehist_cache/{match_id}_{market_code}_{bookie_id}.json"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["python3", fetch_py, "--url", url, "--out-json", out], check=True, capture_output=True, text=True)
    return json.loads(Path(out).read_text("utf-8"))


def ou_key_parts(sel_key: str) -> tuple[str, str]:
    # OU selection_key often: <base>x<lineCode>x0
    parts = sel_key.split("x")
    if len(parts) == 3:
        return parts[0], parts[1]
    return "", ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-json", required=True)
    ap.add_argument("--out-raw", required=True)
    ap.add_argument("--out-agg", required=True)
    ap.add_argument("--decrypt-js", default="scripts/oddsportal_decrypt_match_event.js")
    ap.add_argument("--fetch-py", default="scripts/oddsportal_fetch_mehist.py")
    ap.add_argument("--bookies", default="16,27,43,44,417,500,550,575,609")
    args = ap.parse_args()

    samples = json.loads(Path(args.in_json).read_text("utf-8"))
    samples = [s for s in samples if s.get("ok_archive") and s.get("match_url")]

    bookies = [int(x.strip()) for x in args.bookies.split(",") if x.strip()]

    raw: list[RawRow] = []

    for s in samples:
        row = fetch_archive_row(s, args.decrypt_js)
        home = row.get("home-name", "")
        away = row.get("away-name", "")
        ts0 = int(row.get("date-start-timestamp", 0) or 0)
        match_date = datetime.fromtimestamp(ts0, tz=timezone.utc).strftime("%Y-%m-%d") if ts0 else s.get("match_date_utc", "")

        match_url = s["match_url"]
        mid = parse_match_id(match_url)

        # 1X2
        for b in bookies:
            d = fetch_mehist(mid, "1-2", b, args.fetch_py)
            back = d["d"]["history"]["back"]
            if not isinstance(back, dict):
                continue
            for sel_key, inner in back.items():
                for odd_str, _, ts in inner.get(str(b), []):
                    raw.append(
                        RawRow(
                            match_date_utc=match_date,
                            home_team=home,
                            away_team=away,
                            match_url=match_url,
                            match_id=mid,
                            market="1x2",
                            bookie_id=b,
                            selection_key=sel_key,
                            ou_side_base="",
                            ou_line_code="",
                            ts=int(ts),
                            ts_utc=iso_utc(int(ts)),
                            odds=float(odd_str),
                        )
                    )

        # OU (2-2)
        for b in bookies:
            d = fetch_mehist(mid, "2-2", b, args.fetch_py)
            back = d["d"]["history"]["back"]
            if not isinstance(back, dict):
                continue
            for sel_key, inner in back.items():
                side_base, line_code = ou_key_parts(sel_key)
                for odd_str, _, ts in inner.get(str(b), []):
                    raw.append(
                        RawRow(
                            match_date_utc=match_date,
                            home_team=home,
                            away_team=away,
                            match_url=match_url,
                            match_id=mid,
                            market="ou",
                            bookie_id=b,
                            selection_key=sel_key,
                            ou_side_base=side_base,
                            ou_line_code=line_code,
                            ts=int(ts),
                            ts_utc=iso_utc(int(ts)),
                            odds=float(odd_str),
                        )
                    )

    raw_rows = [r.__dict__ for r in raw]
    write_csv(raw_rows, Path(args.out_raw))

    # median aggregation
    # 1x2: group by selection_key
    # ou: group by (ou_side_base, ou_line_code)
    agg_vals: dict[tuple[str, str, str, str, int], list[float]] = defaultdict(list)
    meta: dict[tuple[str, str, str, str, int], dict[str, Any]] = {}

    for r in raw:
        if r.market == "1x2":
            outcome = r.selection_key
            line = ""
        else:
            outcome = r.ou_side_base or r.selection_key
            line = r.ou_line_code
        key = (r.match_id, r.market, outcome, line, r.ts)
        agg_vals[key].append(r.odds)
        meta[key] = {
            "match_date_utc": r.match_date_utc,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "match_url": r.match_url,
            "match_id": r.match_id,
            "market": r.market,
            "outcome_group": outcome,
            "line_code": line,
            "ts": r.ts,
            "ts_utc": r.ts_utc,
        }

    agg_rows: list[dict[str, Any]] = []
    for k, vals in agg_vals.items():
        m = meta[k]
        agg_rows.append({**m, "odds_median": float(median(vals)), "n_sources": len(vals)})

    agg_rows.sort(key=lambda x: (x["match_date_utc"], x["match_id"], x["market"], x["outcome_group"], x["line_code"], x["ts"]))
    write_csv(agg_rows, Path(args.out_agg))

    print(json.dumps({"raw_rows": len(raw_rows), "agg_rows": len(agg_rows), "out_raw": args.out_raw, "out_agg": args.out_agg}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
