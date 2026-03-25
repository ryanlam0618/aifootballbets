#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backfill 近 10 年：
- 五大聯賽 + 日職 + 韓職 + 澳職
- 以及這些聯賽常見參與的盃賽（歐戰 / 亞洲戰 / 各國國內盃）

資料來源：SofaScore 公開 API
輸出：
- <out_dir>/history_data_10y_leagues_cups.csv
- （可選）merge 到 data/history_data.csv

特性：
- 斷點續跑（state.json + sqlite）
- event_id 去重
- 只抓已完賽 (status.code == 100)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import pandas as pd


SCHEDULE_URL = "https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date}"
STATS_URL = "https://www.sofascore.com/api/v1/event/{event_id}/statistics"
LINEUPS_URL = "https://www.sofascore.com/api/v1/event/{event_id}/lineups"


OUTPUT_COLUMNS = [
    "league",
    "match_date",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "home_shots",
    "away_shots",
    "home_shots_on",
    "away_shots_on",
    "home_corners",
    "away_corners",
    "home_yellow",
    "away_yellow",
    "home_red",
    "away_red",
    "home_fouls",
    "away_fouls",
    "home_poss",
    "away_poss",
    "home_xg_total",
    "away_xg_total",
    "season",
]


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _contains_any(text: str, tokens: Iterable[str]) -> bool:
    t = _norm(text)
    return any(tok in t for tok in tokens)


def _is_excluded_comp(name: str, slug: str) -> bool:
    text = f"{_norm(name)} {_norm(slug)}"
    bad_tokens = [
        "women",
        "woman",
        "feminine",
        "youth",
        "u17",
        "u18",
        "u19",
        "u20",
        "u21",
        "u23",
        "reserve",
        "reserves",
        "primavera",
        "friendly",
        "club friendly",
    ]
    return any(tok in text for tok in bad_tokens)


def canonical_competition(event: Dict) -> Optional[str]:
    """判斷是否為目標聯賽/盃賽，若是返回標準名稱，否則 None。"""
    t = event.get("tournament") or {}
    ut = t.get("uniqueTournament") or {}

    name = ut.get("name") or t.get("name") or ""
    slug = ut.get("slug") or t.get("slug") or ""

    cat_obj = ut.get("category") or t.get("category") or {}
    category = cat_obj.get("name") or ""

    n = _norm(name)
    s = _norm(slug)
    c = _norm(category)
    text = f"{n} {s}"

    if _is_excluded_comp(name, slug):
        return None

    # ===== 8 大聯賽 =====
    if c == "england" and ("premier league" in n or s == "premier-league"):
        return "Premier League"
    if c == "spain" and (("laliga" in n) or s == "laliga"):
        return "La Liga"
    if c == "germany" and ("bundesliga" in n and s == "bundesliga"):
        return "Bundesliga"
    if c == "italy" and (n == "serie a" or s == "serie-a"):
        return "Serie A"
    if c == "france" and (("ligue 1" in n) or s == "ligue-1"):
        return "Ligue 1"

    # 日職（處理 J1 League / J1 League, East/West / slug 變體）
    if c == "japan" and (
        n.startswith("j1 league")
        or s.startswith("j1-league")
        or s == "jleague"
    ):
        return "J1 League"

    # 韓職
    if c == "south korea" and (
        "k league 1" in n or "k-league-1" in s or s == "k-league-1"
    ):
        return "K League 1"

    # 中超（Chinese Super League / CSL）
    if c == "china" and (
        "chinese super league" in n
        or "super league" in n
        or "csl" in n
        or s in {"super-league", "chinese-super-league"}
    ):
        return "Chinese Super League"

    # 澳職
    if c == "australia" and (
        "a-league men" in n or s == "a-league"
    ):
        return "A-League Men"

    # ===== 歐洲盃賽 =====
    if c == "europe":
        if "uefa champions league" in n or s.startswith("uefa-champions-league"):
            return "UEFA Champions League"
        if "uefa europa league" in n or s.startswith("uefa-europa-league"):
            return "UEFA Europa League"
        if (
            "uefa conference league" in n
            or "uefa europa conference league" in n
            or s.startswith("uefa-europa-conference-league")
        ):
            return "UEFA Europa Conference League"

    # ===== 亞洲盃賽 =====
    if c == "asia" or s.startswith("afc-") or "afc " in n:
        if (
            "afc champions league" in n
            or s.startswith("afc-champions-league")
            or s.startswith("afc-cup")  # ACL Two 有些 slug 會走 afc-cup-group-x
        ):
            return "AFC Champions League"

    # ===== 世界盃賽（俱樂部） =====
    if (
        "fifa club world cup" in text
        or s in {"fifa-club-world-cup", "club-world-cup"}
        or ("club world cup" in n and "fifa" in n)
    ):
        return "FIFA Club World Cup"

    if (
        "intercontinental cup" in text
        or s in {"intercontinental-cup", "fifa-intercontinental-cup"}
        or "fifa intercontinental cup" in text
    ):
        return "Intercontinental Cup"

    # ===== 國內盃賽（8 聯賽相關） =====
    if c == "england":
        if "fa cup" in n or s == "fa-cup":
            return "FA Cup"
        if (
            "efl cup" in n
            or "league cup" in n
            or "capital one cup" in n
            or s in {"efl-cup", "league-cup", "capital-one-cup", "carabao-cup"}
        ):
            return "EFL Cup"

    if c == "spain" and ("copa del rey" in n or s == "copa-del-rey"):
        return "Copa del Rey"

    if c == "italy" and ("coppa italia" in n or s == "coppa-italia"):
        return "Coppa Italia"

    if c == "germany" and ("dfb pokal" in n or s == "dfb-pokal"):
        return "DFB Pokal"

    if c == "france" and ("coupe de france" in n or s == "coupe-de-france"):
        return "Coupe de France"

    if c == "japan":
        if "emperor" in n and "cup" in n:
            return "Emperor's Cup"
        if (
            "j.league cup" in n
            or "j league cup" in n
            or "league cup" in n
            or s in {"j-league-cup", "league-cup", "levain-cup"}
        ):
            return "J.League Cup"

    if c == "south korea" and ("fa cup" in n or s == "fa-cup"):
        return "Korean FA Cup"

    if c == "china" and (
        "fa cup" in n
        or "china fa cup" in n
        or "chinese fa cup" in n
        or s in {"fa-cup", "china-fa-cup", "chinese-fa-cup"}
    ):
        return "Chinese FA Cup"

    if c == "australia":
        if (
            "australia cup" in n
            or ("fa cup" in n and c == "australia")
            or s in {"australia-cup", "fa-cup", "ffa-cup"}
        ):
            return "Australia Cup"

    return None


def season_from_date(date_str: str) -> str:
    d = dt.datetime.strptime(date_str, "%Y-%m-%d")
    # 歐洲常見跨年賽季：8 月起
    if d.month >= 8:
        y1 = d.year
        y2 = d.year + 1
    else:
        y1 = d.year - 1
        y2 = d.year
    return f"{y1}-{y2}"


def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def to_num(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def to_int(v, default: int = 0) -> int:
    n = to_num(v)
    if n is None:
        return default
    return int(round(n))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _node_fetch_cmd(url: str, timeout: int) -> list[str]:
    script = _project_root() / "scripts" / "sofascore_fetch.js"
    return ["node", str(script), "--url", url, "--timeout-ms", str(int(max(1000, timeout * 1000)))]


def fetch_json(url: str, retries: int = 3, timeout: int = 25) -> Optional[Dict]:
    for i in range(retries):
        try:
            proc = subprocess.run(
                _node_fetch_cmd(url, timeout),
                check=False,
                capture_output=True,
                text=True,
                timeout=max(5, int(timeout + 5)),
            )
            if proc.returncode != 0:
                err = (proc.stderr or "").lower()
                if "http 404" in err:
                    return None
                raise RuntimeError(proc.stderr.strip() or f"fetch failed for {url}")
            return json.loads(proc.stdout) if proc.stdout else {}
        except Exception:
            if i == retries - 1:
                return None
            time.sleep(1.5 * (i + 1))
    return None


def extract_stats_map(stats_json: Dict) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    out: Dict[str, Tuple[Optional[float], Optional[float]]] = {}

    periods = stats_json.get("statistics") or []
    all_period = None
    for p in periods:
        if p.get("period") == "ALL":
            all_period = p
            break

    if not all_period:
        return out

    for g in all_period.get("groups", []):
        for item in g.get("statisticsItems", []):
            key = _norm(item.get("key") or "")
            name = _norm(item.get("name") or "")

            hv = item.get("homeValue", item.get("home"))
            av = item.get("awayValue", item.get("away"))

            hv_num = to_num(hv)
            av_num = to_num(av)

            if key:
                out[f"key:{key}"] = (hv_num, av_num)
            if name:
                out[f"name:{name}"] = (hv_num, av_num)

    return out


def pick_stat(
    stats_map: Dict[str, Tuple[Optional[float], Optional[float]]],
    keys: Iterable[str],
    names: Iterable[str],
) -> Tuple[Optional[float], Optional[float]]:
    for k in keys:
        v = stats_map.get(f"key:{_norm(k)}")
        if v is not None:
            return v
    for n in names:
        v = stats_map.get(f"name:{_norm(n)}")
        if v is not None:
            return v
    return (None, None)


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS matches (
            event_id INTEGER PRIMARY KEY,
            league TEXT,
            match_date TEXT,
            home_team TEXT,
            away_team TEXT,
            home_goals INTEGER,
            away_goals INTEGER,
            home_shots INTEGER,
            away_shots INTEGER,
            home_shots_on INTEGER,
            away_shots_on INTEGER,
            home_corners INTEGER,
            away_corners INTEGER,
            home_yellow INTEGER,
            away_yellow INTEGER,
            home_red INTEGER,
            away_red INTEGER,
            home_fouls INTEGER,
            away_fouls INTEGER,
            home_poss INTEGER,
            away_poss INTEGER,
            home_xg_total REAL,
            away_xg_total REAL,
            season TEXT,
            source_tournament TEXT,
            source_category TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date)")
    conn.commit()
    return conn


def upsert_match(conn: sqlite3.Connection, row: Dict):
    conn.execute(
        """
        INSERT OR REPLACE INTO matches (
            event_id, league, match_date, home_team, away_team,
            home_goals, away_goals,
            home_shots, away_shots, home_shots_on, away_shots_on,
            home_corners, away_corners,
            home_yellow, away_yellow, home_red, away_red,
            home_fouls, away_fouls, home_poss, away_poss,
            home_xg_total, away_xg_total, season,
            source_tournament, source_category, updated_at
        ) VALUES (
            :event_id, :league, :match_date, :home_team, :away_team,
            :home_goals, :away_goals,
            :home_shots, :away_shots, :home_shots_on, :away_shots_on,
            :home_corners, :away_corners,
            :home_yellow, :away_yellow, :home_red, :away_red,
            :home_fouls, :away_fouls, :home_poss, :away_poss,
            :home_xg_total, :away_xg_total, :season,
            :source_tournament, :source_category, :updated_at
        )
        """,
        row,
    )


def load_existing_event_ids(conn: sqlite3.Connection) -> set[int]:
    cur = conn.execute("SELECT event_id FROM matches")
    return {int(r[0]) for r in cur.fetchall() if r[0] is not None}


def save_state(state_path: Path, state: Dict):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state(state_path: Path) -> Optional[Dict]:
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def export_csv(conn: sqlite3.Connection, out_csv: Path):
    q = "SELECT league,match_date,home_team,away_team,home_goals,away_goals,home_shots,away_shots,home_shots_on,away_shots_on,home_corners,away_corners,home_yellow,away_yellow,home_red,away_red,home_fouls,away_fouls,home_poss,away_poss,home_xg_total,away_xg_total,season FROM matches ORDER BY match_date"
    df = pd.read_sql_query(q, conn)

    for c in OUTPUT_COLUMNS:
        if c not in df.columns:
            df[c] = 0

    df = df[OUTPUT_COLUMNS]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    return len(df)


def merge_history(history_csv: Path, new_csv: Path):
    new_df = pd.read_csv(new_csv)
    if history_csv.exists():
        base_df = pd.read_csv(history_csv)
    else:
        base_df = pd.DataFrame(columns=new_df.columns)

    merged = pd.concat([base_df, new_df], ignore_index=True)

    dedup_cols = ["match_date", "home_team", "away_team", "league"]
    for c in dedup_cols:
        if c not in merged.columns:
            merged[c] = ""

    merged = merged.drop_duplicates(subset=dedup_cols, keep="last")
    merged = merged.sort_values("match_date")
    merged.to_csv(history_csv, index=False, encoding="utf-8-sig")
    return len(merged)


def main():
    parser = argparse.ArgumentParser(description="Backfill 10y leagues+cups from SofaScore")
    parser.add_argument("--start-date", help="YYYY-MM-DD, default: today-10y")
    parser.add_argument("--end-date", help="YYYY-MM-DD, default: today")
    parser.add_argument("--out-dir", default="data/backfill_sofascore_10y", help="output directory")
    parser.add_argument("--db", default="", help="sqlite db path")
    parser.add_argument("--state", default="", help="state json path")
    parser.add_argument("--history-csv", default="data/history_data.csv", help="history csv path")
    parser.add_argument("--merge-history", action="store_true", help="merge final csv into history_data.csv")
    parser.add_argument("--sleep", type=float, default=0.03, help="sleep seconds between event stats requests")
    parser.add_argument("--commit-every", type=int, default=50, help="DB commit interval")
    parser.add_argument("--fresh", action="store_true", help="ignore previous state and start from start-date")
    parser.add_argument("--dump-raw-scheduled", action="store_true", default=True, help="dump raw scheduled-events json by day (default: on)")
    parser.add_argument("--no-dump-raw-scheduled", action="store_false", dest="dump_raw_scheduled", help="disable raw scheduled-events dumping")
    parser.add_argument("--dump-raw-lineups", action="store_true", default=True, help="fetch+dump raw lineups json by event_id (default: on)")
    parser.add_argument("--no-dump-raw-lineups", action="store_false", dest="dump_raw_lineups", help="disable raw lineups dumping")
    args = parser.parse_args()

    today = dt.date.today()
    default_start = today - dt.timedelta(days=3652)  # 約 10 年

    start_date = dt.datetime.strptime(args.start_date, "%Y-%m-%d").date() if args.start_date else default_start
    end_date = dt.datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else today

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_sched_dir = out_dir / "raw" / "scheduled-events"
    raw_lineups_dir = out_dir / "raw" / "lineups"
    if args.dump_raw_scheduled:
        raw_sched_dir.mkdir(parents=True, exist_ok=True)
    if args.dump_raw_lineups:
        raw_lineups_dir.mkdir(parents=True, exist_ok=True)

    db_path = Path(args.db) if args.db else out_dir / "backfill_10y.sqlite"
    state_path = Path(args.state) if args.state else out_dir / "state.json"
    history_csv = Path(args.history_csv)

    # 斷點續跑
    state = load_state(state_path)
    effective_start = start_date

    if state and not args.fresh:
        last_date_str = state.get("last_date")
        if last_date_str:
            try:
                last_date = dt.datetime.strptime(last_date_str, "%Y-%m-%d").date()
                if start_date <= last_date < end_date:
                    effective_start = last_date + dt.timedelta(days=1)
            except Exception:
                pass

    print("=" * 70)
    print("SofaScore 10y backfill started")
    print(f"range: {start_date} ~ {end_date}")
    print(f"effective start: {effective_start}")
    print(f"out_dir: {out_dir}")
    print(f"db: {db_path}")
    print(f"state: {state_path}")
    print("=" * 70)

    conn = init_db(db_path)
    existing_ids = load_existing_event_ids(conn)

    days_total = (end_date - effective_start).days + 1
    if days_total <= 0:
        print("Nothing to do (already up-to-date for requested range).")
    else:
        inserted = 0
        skipped_existing = 0
        skipped_not_target = 0
        skipped_not_finished = 0
        no_stats = 0

        pending_commit = 0

        for day_idx, d in enumerate(daterange(effective_start, end_date), start=1):
            ds = d.strftime("%Y-%m-%d")
            sched = fetch_json(SCHEDULE_URL.format(date=ds), retries=3, timeout=30)
            if sched and args.dump_raw_scheduled:
                save_json(raw_sched_dir / f"{ds}.json", sched)
            if not sched:
                print(f"[WARN] schedule fetch failed: {ds}")
                save_state(
                    state_path,
                    {
                        "start_date": str(start_date),
                        "end_date": str(end_date),
                        "last_date": ds,
                        "inserted": inserted,
                        "updated_at": dt.datetime.utcnow().isoformat() + "Z",
                    },
                )
                continue

            events = sched.get("events") or []
            target_events = 0

            for ev in events:
                comp = canonical_competition(ev)
                if not comp:
                    skipped_not_target += 1
                    continue

                status = ev.get("status") or {}
                if status.get("code") != 100:
                    skipped_not_finished += 1
                    continue

                target_events += 1

                event_id = ev.get("id")
                if event_id is None:
                    continue
                try:
                    event_id = int(event_id)
                except Exception:
                    continue

                if args.dump_raw_lineups:
                    lineup_path = raw_lineups_dir / f"{event_id}.json"
                    if not lineup_path.exists():
                        try:
                            lineup_json = fetch_json(LINEUPS_URL.format(event_id=event_id), retries=2, timeout=20)
                            if lineup_json is not None:
                                save_json(lineup_path, lineup_json)
                        except Exception:
                            pass

                if event_id in existing_ids:
                    skipped_existing += 1
                    continue

                home_team = (ev.get("homeTeam") or {}).get("name")
                away_team = (ev.get("awayTeam") or {}).get("name")
                hs = (ev.get("homeScore") or {}).get("current")
                aw = (ev.get("awayScore") or {}).get("current")

                if not home_team or not away_team or hs is None or aw is None:
                    continue

                stats_json = fetch_json(STATS_URL.format(event_id=event_id), retries=3, timeout=25)
                stats_map = extract_stats_map(stats_json or {}) if stats_json else {}
                if not stats_map:
                    no_stats += 1

                # 逐項取值（有就用，無就預設）
                shots_h, shots_a = pick_stat(
                    stats_map,
                    keys=["totalShotsOnGoal", "totalShots"],
                    names=["Total shots"],
                )
                on_h, on_a = pick_stat(
                    stats_map,
                    keys=["shotsOnGoal"],
                    names=["Shots on target"],
                )
                cor_h, cor_a = pick_stat(
                    stats_map,
                    keys=["cornerKicks"],
                    names=["Corner kicks"],
                )
                yc_h, yc_a = pick_stat(
                    stats_map,
                    keys=["yellowCards"],
                    names=["Yellow cards"],
                )
                rc_h, rc_a = pick_stat(
                    stats_map,
                    keys=["redCards"],
                    names=["Red cards"],
                )
                foul_h, foul_a = pick_stat(
                    stats_map,
                    keys=["fouls"],
                    names=["Fouls"],
                )
                poss_h, poss_a = pick_stat(
                    stats_map,
                    keys=["ballPossession"],
                    names=["Ball possession"],
                )
                xg_h, xg_a = pick_stat(
                    stats_map,
                    keys=["expectedGoals"],
                    names=["Expected goals"],
                )

                t = ev.get("tournament") or {}
                ut = t.get("uniqueTournament") or {}
                source_name = ut.get("name") or t.get("name") or ""
                source_cat = ((ut.get("category") or t.get("category") or {}).get("name") or "")

                row = {
                    "event_id": event_id,
                    "league": comp,
                    "match_date": ds,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_goals": int(hs),
                    "away_goals": int(aw),
                    "home_shots": to_int(shots_h, 0),
                    "away_shots": to_int(shots_a, 0),
                    "home_shots_on": to_int(on_h, 0),
                    "away_shots_on": to_int(on_a, 0),
                    "home_corners": to_int(cor_h, 0),
                    "away_corners": to_int(cor_a, 0),
                    "home_yellow": to_int(yc_h, 0),
                    "away_yellow": to_int(yc_a, 0),
                    "home_red": to_int(rc_h, 0),
                    "away_red": to_int(rc_a, 0),
                    "home_fouls": to_int(foul_h, 0),
                    "away_fouls": to_int(foul_a, 0),
                    "home_poss": to_int(poss_h, 50),
                    "away_poss": to_int(poss_a, 50),
                    "home_xg_total": round(float(xg_h), 2) if xg_h is not None else 0.0,
                    "away_xg_total": round(float(xg_a), 2) if xg_a is not None else 0.0,
                    "season": season_from_date(ds),
                    "source_tournament": source_name,
                    "source_category": source_cat,
                    "updated_at": dt.datetime.utcnow().isoformat() + "Z",
                }

                upsert_match(conn, row)
                existing_ids.add(event_id)
                inserted += 1
                pending_commit += 1

                if pending_commit >= args.commit_every:
                    conn.commit()
                    pending_commit = 0

                if args.sleep > 0:
                    time.sleep(args.sleep)

            if pending_commit > 0:
                conn.commit()
                pending_commit = 0

            save_state(
                state_path,
                {
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "last_date": ds,
                    "inserted": inserted,
                    "updated_at": dt.datetime.utcnow().isoformat() + "Z",
                },
            )

            if day_idx % 20 == 0 or target_events > 0:
                print(
                    f"[DAY {day_idx}/{days_total}] {ds} "
                    f"target_events={target_events} inserted_total={inserted}"
                )

        print(
            f"[DONE] inserted={inserted}, skipped_existing={skipped_existing}, "
            f"skipped_not_target={skipped_not_target}, skipped_not_finished={skipped_not_finished}, "
            f"no_stats={no_stats}"
        )

    out_csv = out_dir / "history_data_10y_leagues_cups.csv"
    total_rows = export_csv(conn, out_csv)
    print(f"[EXPORT] {out_csv} rows={total_rows}")

    if args.merge_history:
        merged_rows = merge_history(history_csv, out_csv)
        print(f"[MERGE] {history_csv} rows={merged_rows}")

    conn.close()


if __name__ == "__main__":
    main()
