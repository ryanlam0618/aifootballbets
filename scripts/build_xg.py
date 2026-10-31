#!/usr/bin/env python3
"""Layer-2 afb-T3: self-built shot xG pipeline (T3a-d).

T3a  Train self-built xG on shots WITH official xG (XGBoost main +
     LinearRegression control; features: distance/angle from x/y,
     shot_type, situation, body_part).
T3b  Isotonic calibration onto the official xG scale (chronological
     calibration slice — no leakage).
T3c  Fill shots with missing xG: calibrated value + xg_source column
     ('official' / 'calibrated'). Safety: afb_shotmap_xg_backup table +
     xg IS NULL guard (official values are never overwritten).
T3d  Rolling per-team xG windows (last-N as-of) -> afb_team_rolling_xg
     (coverage ~100% after the fill; strictly pre-match data — no leakage).

Outputs: reports/backtest_xg_report.json + .md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np

from afbdb.connection import afb_mysql_connect  # noqa: E402
from models.shot_xg import build_feature_matrix, calibrate_value, train_shot_xg  # noqa: E402
from config import settings_v2  # noqa: E402


def fetch_shots(conn, with_xg: bool) -> List[dict]:
    sql = """
        SELECT s.shot_id, s.match_id, m.match_date, s.player_x AS x, s.player_y AS y,
               s.shot_type, s.situation, s.body_part, s.xg, s.team_id
        FROM match_shotmap s
        JOIN matches m ON m.match_id = s.match_id
        WHERE m.status = 'finished' AND s.player_x IS NOT NULL AND s.player_y IS NOT NULL
    """
    sql += " AND s.xg IS NOT NULL" if with_xg else " AND s.xg IS NULL"
    sql += " ORDER BY m.match_date, s.shot_id"
    cur = conn.cursor()
    cur.execute(sql)
    rows = []
    for r in cur.fetchall():
        rows.append(
            {
                "shot_id": int(r[0]),
                "match_id": int(r[1]),
                "match_date": r[2],
                "x": float(r[3]),
                "y": float(r[4]),
                "shot_type": r[5],
                "situation": r[6],
                "body_part": r[7],
                "xg": (float(r[8]) if r[8] is not None else None),
                "team_id": int(r[9]) if r[9] is not None else None,
            }
        )
    return rows


def backup_and_add_column(conn) -> bool:
    """Backup current (shot_id, xg) and add xg_source if missing. Returns added."""
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS afb_shotmap_xg_backup AS "
        "SELECT shot_id, xg FROM match_shotmap"
    )
    conn.commit()
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema=DATABASE() AND table_name='match_shotmap' AND column_name='xg_source'"
    )
    if cur.fetchone()[0]:
        print("[T3c] xg_source column already exists")
        return False
    cur.execute("ALTER TABLE match_shotmap ADD COLUMN xg_source VARCHAR(16) NULL")
    conn.commit()
    print("[T3c] ALTER added xg_source column")
    return True


def mark_official(conn, batch: int = 50000) -> int:
    cur = conn.cursor()
    total = 0
    while True:
        cur.execute(
            "UPDATE match_shotmap SET xg_source='official' "
            "WHERE xg IS NOT NULL AND xg_source IS NULL LIMIT %s",
            (batch,),
        )
        n = cur.rowcount
        conn.commit()
        total += n
        if n == 0:
            break
    return total


def fill_calibrated(conn, preds: List[dict], batch: int = 5000) -> int:
    cur = conn.cursor()
    total = 0
    for i in range(0, len(preds), batch):
        part = preds[i : i + batch]
        cur.executemany(
            "UPDATE match_shotmap SET xg=%s, xg_source='calibrated' "
            "WHERE shot_id=%s AND xg IS NULL",
            [(float(p["xg_calibrated"]), int(p["shot_id"])) for p in part],
        )
        conn.commit()
        total += len(part)
    return total


def team_match_xg_totals(conn) -> List[Tuple[int, int, any, int, int, float, float]]:
    """(home_team_id, away_team_id, match_date, match_id, home_goals, away_goals)
    per finished match plus per-team xG totals: returns flat rows
    (match_id, match_date, team_id, opponent_id, xg_total)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.match_id, m.match_date, s.team_id, SUM(s.xg) AS xg_total
        FROM match_shotmap s
        JOIN matches m ON m.match_id = s.match_id
        WHERE m.status='finished' AND s.xg IS NOT NULL
        GROUP BY m.match_id, m.match_date, s.team_id
        ORDER BY s.team_id, m.match_date, m.match_id
        """
    )
    return [(int(r[0]), r[1], int(r[2]), float(r[3] or 0.0)) for r in cur.fetchall()]


def build_rolling(conn, window: int = 10, min_history: int = 5) -> dict:
    """Per (team, match) pre-match rolling xG for/against over last `window` matches.

    Strictly as-of: only matches BEFORE the reference match contribute.
    """
    rows = team_match_xg_totals(conn)
    # per match: team -> xg_total (to derive opponent values)
    match_team_xg: Dict[int, Dict[int, float]] = {}
    for match_id, _md, team_id, xg_total in rows:
        match_team_xg.setdefault(match_id, {})[team_id] = xg_total

    per_team: Dict[int, List[Tuple[int, float, float]]] = {}  # team -> [(match_id, own_xg, opp_xg)]
    for match_id, _md, team_id, xg_total in rows:
        opp_xg = 0.0
        for tid, xv in match_team_xg.get(match_id, {}).items():
            if tid != team_id:
                opp_xg = xv
        per_team.setdefault(team_id, []).append((match_id, xg_total, opp_xg))

    merged: Dict[Tuple[int, int], dict] = {}
    for team_id, seq in per_team.items():
        hist_for: List[float] = []
        hist_against: List[float] = []
        for match_id, own, opp in seq:
            if len(hist_for) >= min_history:
                wf = hist_for[-window:]
                wa = hist_against[-window:]
                merged[(team_id, match_id)] = {
                    "for": round(sum(wf) / len(wf), 6),
                    "against": round(sum(wa) / len(wa), 6),
                    "n": len(wf),
                }
            hist_for.append(own)
            hist_against.append(opp)

    cur = conn.cursor()
    # appdb_rw has no DROP privilege — rebuild via DELETE (if exists) or CREATE
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema=DATABASE() AND table_name='afb_team_rolling_xg'"
    )
    if cur.fetchone()[0]:
        cur.execute("DELETE FROM afb_team_rolling_xg")
    else:
        cur.execute(
            """
            CREATE TABLE afb_team_rolling_xg (
              team_id INT NOT NULL,
              match_id BIGINT NOT NULL,
              rolling_xg_for DECIMAL(10,6) NOT NULL,
              rolling_xg_against DECIMAL(10,6) NOT NULL,
              n_history INT NOT NULL,
              PRIMARY KEY (team_id, match_id),
              KEY idx_trx_match (match_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
    conn.commit()
    vals = [
        (tid, mid, v["for"], v["against"], v["n"])
        for (tid, mid), v in merged.items()
    ]
    for i in range(0, len(vals), 5000):
        cur.executemany(
            "INSERT INTO afb_team_rolling_xg (team_id, match_id, rolling_xg_for, rolling_xg_against, n_history) "
            "VALUES (%s,%s,%s,%s,%s)",
            vals[i : i + 5000],
        )
        conn.commit()
    return {"team_match_rows": len(vals), "teams": len(per_team), "window": window, "min_history": min_history}


def main() -> int:
    p = argparse.ArgumentParser(description="T3 self-built xG pipeline (a-d)")
    p.add_argument("--test-frac", type=float, default=0.15)
    p.add_argument("--calib-frac", type=float, default=0.15)
    p.add_argument("--window", type=int, default=10)
    p.add_argument("--skip-db-write", action="store_true", help="train + evaluate only (no ALTER/UPDATE)")
    p.add_argument("--out-prefix", type=str, default="reports/backtest_xg_report")
    args = p.parse_args()

    conn = afb_mysql_connect()

    # ---- T3a: training shots (official xG present) ----
    print("[T3a] loading shots with official xG ...")
    shots = fetch_shots(conn, with_xg=True)
    print(f"[T3a] {len(shots)} shots with official xG")
    result = train_shot_xg(shots, test_frac=args.test_frac, calib_frac=args.calib_frac)
    print(f"[T3a] train={result.n_train} calib={result.n_calib} test={result.n_test}")
    print(f"[T3a] metrics: {json.dumps(result.metrics, ensure_ascii=False)}")

    # ---- T3c: predictions for missing-xg shots ----
    print("[T3c] loading shots WITHOUT official xG ...")
    missing = fetch_shots(conn, with_xg=False)
    print(f"[T3c] {len(missing)} shots without official xG")
    preds: List[dict] = []
    if missing:
        dicts, names = build_feature_matrix(missing)
        # align feature columns to training names
        X = np.array([[d.get(n, 0.0) for n in result.feature_names] for d in dicts])
        raw = result.model.predict(X)
        for shot, raw_v in zip(missing, raw):
            preds.append(
                {
                    "shot_id": shot["shot_id"],
                    "xg_calibrated": calibrate_value(float(raw_v), result.calibrator),
                }
            )
        print(f"[T3c] {len(preds)} calibrated predictions ready")

    # ---- DB writes (T3c + T3d) ----
    added = marked = filled = None
    rolling_summary: Dict = {"skipped": True}
    if not args.skip_db_write:
        print("[T3c] backup + ALTER + mark official ...")
        added = backup_and_add_column(conn)
        marked = mark_official(conn)
        print(f"[T3c] xg_source added={added}; official marked={marked}")
        filled = fill_calibrated(conn, preds)
        print(f"[T3c] calibrated fills written: {filled}")
        print("[T3d] rolling windows ...")
        rolling_summary = build_rolling(conn, window=args.window)
        print(f"[T3d] rolling: {json.dumps(rolling_summary, ensure_ascii=False)}")
    else:
        print("[skip-db-write] DB writes skipped")

    # ---- verification ----
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(xg IS NOT NULL) FROM match_shotmap")
    total_shots, with_xg = cur.fetchone()
    coverage = with_xg / total_shots if total_shots else 0
    by_source: Dict[str, int] = {}
    if not args.skip_db_write:
        # xg_source only exists after the ALTER in the DB-write path
        cur.execute("SELECT xg_source, COUNT(*) FROM match_shotmap WHERE xg IS NOT NULL GROUP BY xg_source")
        by_source = {str(r[0] or "NULL"): int(r[1]) for r in cur.fetchall()}
    print(f"[verify] coverage: {with_xg}/{total_shots} = {coverage:.4f}; by source: {by_source}")

    report = {
        "meta": {
            "generated": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "test_frac": args.test_frac,
            "calib_frac": args.calib_frac,
            "window": args.window,
            "skip_db_write": bool(args.skip_db_write),
        },
        "T3a_training": {
            "n_train": result.n_train,
            "n_calib": result.n_calib,
            "n_test": result.n_test,
            "feature_names": result.feature_names,
        },
        "T3a_metrics": result.metrics,
        "T3b_isotonic_points": len(result.calibrator),
        "T3c_fill": {
            "predictions": len(preds),
            "written": bool(not args.skip_db_write),
            "marked_official": marked,
            "xg_source_added": added,
        },
        "T3d_rolling": rolling_summary,
        "coverage": {
            "total_shots": int(total_shots),
            "with_xg": int(with_xg),
            "ratio": round(coverage, 4),
            "by_source": by_source,
        },
    }

    out_json = Path(REPO_ROOT) / (args.out_prefix + ".json")
    out_md = Path(REPO_ROOT) / (args.out_prefix + ".md")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md = [
        "# SELF-BUILT xG PIPELINE REPORT (afb-T3)",
        f"meta: {json.dumps(report['meta'], ensure_ascii=False)}",
        "",
        f"T3a: train={result.n_train} calib={result.n_calib} test={result.n_test}",
        f"T3a metrics: {json.dumps(result.metrics, ensure_ascii=False)}",
        f"T3b: isotonic points={len(result.calibrator)}",
        f"T3c: predictions={len(preds)} written={not args.skip_db_write} official_marked={marked} filled={filled}",
        f"T3d: {json.dumps(rolling_summary, ensure_ascii=False)}",
        f"coverage: {coverage:.4f} ({with_xg}/{total_shots}); by_source={by_source}",
        "",
        "leakage note: rolling windows use only matches strictly BEFORE the reference match;",
        "isotonic calibrator fitted on a chronological calibration slice, evaluated on a later slice.",
    ]
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"[done] wrote {out_json}")
    print(f"[done] wrote {out_md}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
