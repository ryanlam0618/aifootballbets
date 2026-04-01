#!/usr/bin/env python3
"""Run OddsPortal backfill for the SofaScore-aligned 25 competitions.

Pipeline per (competition, season):
  1) Generate matchlist jsonl using v2/tracking/oddsportal_season_matchlist.py
  2) Backfill odds into MySQL using scripts/oddsportal_backfill_season_to_mysql.py

Notes:
- Concurrency is implemented as N parallel subprocesses (default 2), each working on
  one (competition, season) at a time.
- We include 2025-2026 if present in SofaScore for that league.
- match_date_utc is now captured from OddsPortal archive and inserted into matches.

This script does NOT yet implement automated resume from a manifest; it appends logs
and will skip completed tasks if the output log indicates done=true.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def sh(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> int:
    p = subprocess.run(cmd, cwd=str(cwd), env=env)
    return int(p.returncode)


def load_cfg(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def expand_season_template(url_template: str, season: str) -> str:
    return url_template.replace("{season}", season)


def season_year_bounds(season: str) -> tuple[int, int] | None:
    """Parse 'YYYY-YYYY' -> (YYYY, YYYY). Returns None if not parseable."""
    try:
        a, b = season.split("-", 1)
        y1, y2 = int(a), int(b)
        if 1900 <= y1 <= 2100 and 1900 <= y2 <= 2100 and y2 >= y1:
            return (y1, y2)
    except Exception:
        pass
    return None


def jsonl_date_range_ok(jsonl_path: Path, season: str) -> bool:
    """Sanity-check match_date_utc in generated matchlist.

    Guards against using a non-season-specific '/results/' page which returns the
    latest season but gets labeled as an older season.

    We accept dates where YEAR(match_date_utc) is within [start_year, end_year].
    If there are no dates present, treat as invalid.
    """
    bounds = season_year_bounds(season)
    if not bounds:
        return True  # don't block unknown season formats
    y1, y2 = bounds

    seen = 0
    bad = 0
    # sample up to N lines for speed
    N = 200
    with jsonl_path.open("r", encoding="utf-8") as f:
        for i, ln in enumerate(f):
            if i >= N:
                break
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            md = (d.get("match_date_utc") or "").strip()
            if not md or len(md) < 4:
                continue
            seen += 1
            try:
                yy = int(md[:4])
            except Exception:
                continue
            if yy < y1 or yy > y2:
                bad += 1

    if seen == 0:
        return False
    # If more than a small fraction are out of range, reject.
    return (bad / max(1, seen)) <= 0.05


def task_id(comp_key: str, season: str) -> str:
    return f"{comp_key}__{season}".replace("/", "-")


def is_done(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    try:
        # check last ~30 lines for a done json
        tail = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-50:]
        for line in reversed(tail):
            line = line.strip()
            if not line:
                continue
            if line.startswith("{") and '"done"' in line:
                j = json.loads(line)
                return bool(j.get("done"))
    except Exception:
        return False
    return False


def run_one(
    *,
    comp: dict[str, Any],
    season: str,
    out_root: Path,
    mysql_url: str,
    workers: int,
    sleep_ms: int,
    bookies: str,
    markets: str,
) -> tuple[str, int]:
    comp_key = comp["key"]
    comp_name = comp["canonical_name"]

    tid = task_id(comp_key, season)
    out_dir = out_root / tid
    out_dir.mkdir(parents=True, exist_ok=True)

    matchlist_out_dir = out_dir / "matchlist"
    matchlist_out_dir.mkdir(parents=True, exist_ok=True)

    backfill_log = out_dir / "backfill.log"

    if is_done(backfill_log):
        return (tid, 0)

    # 1) matchlist
    url_templates = comp["oddsportal"].get("url_templates") or []
    if not url_templates:
        return (tid, 2)

    # try templates in order until we get enough urls
    matchlist_jsonl = None
    for ut in url_templates:
        url = expand_season_template(ut, season)

        # Safety: for historical seasons, do NOT accept the generic '/results/' template.
        # It often returns the latest season and would poison the season labeling.
        if "{season}" not in ut and season_year_bounds(season):
            continue

        ml_base = f"{comp_key.lower()}_{season.replace('-', '_')}"
        cmd = [
            sys.executable,
            str(REPO_ROOT / "v2" / "tracking" / "oddsportal_season_matchlist.py"),
            "--url-template",
            url,
            "--season",
            season,
            "--competition",
            comp_key,
            "--headless",
            "--max-pages",
            "80",
            "--min-match-urls",
            "1",
            "--out-dir",
            str(matchlist_out_dir),
        ]
        # append run output to a small log
        ml_log = out_dir / "matchlist.log"
        with ml_log.open("a", encoding="utf-8") as f:
            f.write("\n# URL: " + url + "\n")

        rc = subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode
        if rc == 0:
            # meta tells us the exact output path
            meta = matchlist_out_dir / "match_lists" / f"{ml_base}.meta.json"
            if meta.exists():
                j = json.loads(meta.read_text(encoding="utf-8"))
                candidate = Path(j["output"])
                if candidate.exists() and jsonl_date_range_ok(candidate, season):
                    matchlist_jsonl = candidate
                    break
            # Fallback: find any meta for this comp/season (slugify differences).
            for m in (matchlist_out_dir / "match_lists").glob("*.meta.json"):
                try:
                    jj = json.loads(m.read_text(encoding="utf-8"))
                    if jj.get("competition") == comp_key and jj.get("season") == season and jj.get("count_ok"):
                        candidate = Path(jj["output"])
                        if candidate.exists() and jsonl_date_range_ok(candidate, season):
                            matchlist_jsonl = candidate
                            break
                except Exception:
                    pass
            if matchlist_jsonl:
                break

    if not matchlist_jsonl or not matchlist_jsonl.exists():
        return (tid, 3)

    # 2) backfill
    cmd2 = [
        str(REPO_ROOT / ".venv312" / "bin" / "python"),
        "-u",
        str(REPO_ROOT / "scripts" / "oddsportal_backfill_season_to_mysql.py"),
        "--match-list",
        str(matchlist_jsonl),
        "--mysql-url",
        mysql_url,
        "--competition",
        comp_key,
        "--season",
        season,
        "--bookies",
        bookies,
        "--markets",
        markets,
        "--limit-matches",
        "0",
        "--progress-every",
        "20",
        "--sleep-ms",
        str(sleep_ms),
        "--workers",
        str(workers),
        "--max-retries",
        "2",
        "--backoff-base-ms",
        "800",
        "--req-jitter-ms",
        "50",
    ]

    with backfill_log.open("a", encoding="utf-8") as f:
        f.write(f"\n# {comp_key} {comp_name} {season}\n")
        f.flush()
        p = subprocess.Popen(cmd2, cwd=str(REPO_ROOT), stdout=f, stderr=subprocess.STDOUT)
        rc2 = p.wait()

    return (tid, int(rc2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="data/oddsportal_competitions_25.yml")
    ap.add_argument(
        "--mysql-url",
        default="mysql://A100:hksfl1512@192.168.0.182:3306/oddsportal_10y",
    )
    ap.add_argument("--out-root", default="/home/openclaw/.openclaw/workspace/tmp/oddsportal_run_25")
    ap.add_argument("--parallel", type=int, default=2)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--sleep-ms", type=int, default=120)
    ap.add_argument("--bookies", default="16,27,43,44,417,500,550,575,609")
    ap.add_argument("--markets", default="1x2,ou,ah")
    ap.add_argument("--only", default="", help="Comma-separated comp keys to run (optional)")
    args = ap.parse_args()

    cfg = load_cfg(REPO_ROOT / args.cfg)
    comps = cfg["competitions"]

    only = [s.strip() for s in (args.only or "").split(",") if s.strip()]
    if only:
        comps = [c for c in comps if c["key"] in set(only)]

    # seasons: align to SofaScore season set per competition (as present in cfg file).
    # For now, use a fixed season range; later we can query appdb here too.
    # We'll derive seasons from url templates: default 2016-2017..2025-2026, plus special cases.

    # better: use plan generator output
    plan = json.loads(subprocess.check_output([sys.executable, str(REPO_ROOT / "scripts" / "oddsportal_plan_25.py")], cwd=str(REPO_ROOT), text=True))
    seasons_by_key = {c["key"]: c["seasons"] for c in plan["competitions"]}

    tasks = []
    for c in comps:
        key = c["key"]
        seasons = seasons_by_key.get(key) or []
        for season in seasons:
            tasks.append((c, season))

    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"tasks={len(tasks)} comps={len(comps)} parallel={args.parallel} workers={args.workers}")

    results: list[tuple[str, int]] = []
    with ThreadPoolExecutor(max_workers=max(1, int(args.parallel))) as ex:
        futs = [
            ex.submit(
                run_one,
                comp=c,
                season=season,
                out_root=out_root,
                mysql_url=args.mysql_url,
                workers=int(args.workers),
                sleep_ms=int(args.sleep_ms),
                bookies=str(args.bookies),
                markets=str(args.markets),
            )
            for (c, season) in tasks
        ]
        for fut in as_completed(futs):
            tid, rc = fut.result()
            results.append((tid, rc))
            print(f"DONE {tid} rc={rc}")

    bad = [r for r in results if r[1] != 0]
    print(f"finished ok={len(results)-len(bad)} bad={len(bad)}")
    if bad:
        print("bad examples:", bad[:10])
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
