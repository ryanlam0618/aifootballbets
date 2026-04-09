#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_summary(summary_json: dict) -> dict:
    s = summary_json.get("summary") or {}
    return {
        "bets": int(s.get("bets", 0) or 0),
        "pnl": float(s.get("pnl", 0.0) or 0.0),
        "roi_pct": float(s.get("roi_pct", 0.0) or 0.0),
        "max_drawdown_pct": float(s.get("max_drawdown_pct", 0.0) or 0.0),
        "winrate_pct": float(s.get("winrate_pct", 0.0) or 0.0),
        "avg_edge_pct": float(s.get("avg_edge_pct", 0.0) or 0.0),
        "avg_clv_pct": float(s.get("avg_clv_pct", 0.0) or 0.0),
        "ending_bankroll": float(s.get("ending_bankroll", 0.0) or 0.0),
        "starting_bankroll": float(s.get("starting_bankroll", 0.0) or 0.0),
        "baseline_flat": s.get("baseline_flat") or {},
        "by_market": s.get("by_market") or [],
    }


def _collect_bet_rows(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
              substr(kickoff_time_hkt, 1, 10) AS day,
              COALESCE(home, '') AS home,
              COALESCE(away, '') AS away,
              COALESCE(market_type, '') AS market_type,
              COALESCE(line, '') AS line,
              COALESCE(selection, '') AS selection,
              COALESCE(odds_bet, 0) AS odds_bet,
              COALESCE(model_prob, 0) AS model_prob,
              COALESCE(profit, 0) AS profit,
              COALESCE(result, '') AS result
            FROM bet_log
            ORDER BY day ASC, home ASC, away ASC, market_type ASC, line ASC, selection ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _run_model(label: str, model_name: str, args, out_root: Path) -> dict:
    out_dir = out_root / label
    db_path = out_root / f"{label}.sqlite"
    snapshot_db = out_root / f"{label}_snap.sqlite"

    env = os.environ.copy()
    env["PAPER_MODEL_NAME"] = model_name

    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "paper_run_7d.py"),
        "--start-date",
        args.start_date,
        "--sqlite",
        str(db_path),
        "--snapshot-db",
        str(snapshot_db),
        "--run-prefix",
        f"compare7d_{label}",
        "--odds-provider",
        args.odds_provider,
        "--results-provider",
        args.results_provider,
        "--out-dir",
        str(out_dir),
        "--bankroll",
        str(args.bankroll),
    ]

    if args.provider_json:
        cmd.extend(["--provider-json", args.provider_json])
    if args.allow_synthetic_odds:
        cmd.append("--allow-synthetic-odds")
    if args.closing_odds_tracker_sqlite:
        cmd.extend(["--closing-odds-tracker-sqlite", args.closing_odds_tracker_sqlite])

    subprocess.run(cmd, check=True, env=env, cwd=str(REPO_ROOT))

    end_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    from datetime import timedelta

    end_date = end_date + timedelta(days=6)
    summary_path = out_dir / f"paper_7d_summary_{end_date.isoformat()}.json"
    summary_json = _load_json(summary_path)

    return {
        "label": label,
        "model_name": model_name,
        "db_path": str(db_path),
        "out_dir": str(out_dir),
        "summary_path": str(summary_path),
        "summary": _extract_summary(summary_json),
        "bets": _collect_bet_rows(db_path),
    }


def _pair_key(row: dict) -> tuple:
    return (
        str(row.get("day", "")),
        str(row.get("home", "")),
        str(row.get("away", "")),
        str(row.get("market_type", "")),
        str(row.get("line", "")),
    )


def _bet_signature(row: dict) -> str:
    return f"{row.get('selection','')} @ {float(row.get('odds_bet', 0) or 0):.2f}"


def _build_diff(old_rows: list[dict], new_rows: list[dict]) -> dict:
    old_map = {_pair_key(r): r for r in old_rows}
    new_map = {_pair_key(r): r for r in new_rows}
    keys = sorted(set(old_map.keys()) | set(new_map.keys()))

    changed = []
    old_only = []
    new_only = []
    same = 0

    for k in keys:
        a = old_map.get(k)
        b = new_map.get(k)
        if a and b:
            same_pick = (
                str(a.get("selection", "")) == str(b.get("selection", ""))
                and abs(float(a.get("odds_bet", 0) or 0) - float(b.get("odds_bet", 0) or 0)) < 1e-9
            )
            if same_pick:
                same += 1
            else:
                changed.append(
                    {
                        "day": k[0],
                        "match": f"{k[1]} vs {k[2]}",
                        "market_type": k[3],
                        "line": k[4],
                        "old": {
                            "selection": a.get("selection", ""),
                            "odds_bet": float(a.get("odds_bet", 0) or 0),
                            "model_prob": float(a.get("model_prob", 0) or 0),
                            "profit": float(a.get("profit", 0) or 0),
                            "result": a.get("result", ""),
                        },
                        "new": {
                            "selection": b.get("selection", ""),
                            "odds_bet": float(b.get("odds_bet", 0) or 0),
                            "model_prob": float(b.get("model_prob", 0) or 0),
                            "profit": float(b.get("profit", 0) or 0),
                            "result": b.get("result", ""),
                        },
                    }
                )
        elif a and not b:
            old_only.append(
                {
                    "day": k[0],
                    "match": f"{k[1]} vs {k[2]}",
                    "market_type": k[3],
                    "line": k[4],
                    "old": _bet_signature(a),
                }
            )
        elif b and not a:
            new_only.append(
                {
                    "day": k[0],
                    "match": f"{k[1]} vs {k[2]}",
                    "market_type": k[3],
                    "line": k[4],
                    "new": _bet_signature(b),
                }
            )

    return {
        "same_pick_count": same,
        "changed_pick_count": len(changed),
        "old_only_count": len(old_only),
        "new_only_count": len(new_only),
        "changed": changed,
        "old_only": old_only,
        "new_only": new_only,
    }


def _render_markdown(report: dict) -> str:
    old = report["old_model"]
    new = report["new_model"]
    diff = report["diff"]

    lines = [
        f"# Paper 7D Old-vs-New Comparison ({report['start_date']} -> {report['end_date']})",
        "",
        f"- Old model: `{old['model_name']}`",
        f"- New model: `{new['model_name']}`",
        f"- Provider JSON: `{report['provider_json']}`" if report.get("provider_json") else "- Provider JSON: (live/provider mode)",
        f"- Bankroll: {report['bankroll']:.2f}",
        "",
        "## Summary",
        "",
        "### Old model",
        f"- Bets: {old['summary']['bets']}",
        f"- PnL: {old['summary']['pnl']:.2f}",
        f"- ROI: {old['summary']['roi_pct']:.2f}%",
        f"- Winrate: {old['summary']['winrate_pct']:.2f}%",
        f"- Avg edge: {old['summary']['avg_edge_pct']:.2f}%",
        f"- Ending bankroll: {old['summary']['ending_bankroll']:.2f}",
        "",
        "### New model",
        f"- Bets: {new['summary']['bets']}",
        f"- PnL: {new['summary']['pnl']:.2f}",
        f"- ROI: {new['summary']['roi_pct']:.2f}%",
        f"- Winrate: {new['summary']['winrate_pct']:.2f}%",
        f"- Avg edge: {new['summary']['avg_edge_pct']:.2f}%",
        f"- Ending bankroll: {new['summary']['ending_bankroll']:.2f}",
        "",
        "### Delta (new - old)",
        f"- Bets delta: {new['summary']['bets'] - old['summary']['bets']}",
        f"- PnL delta: {new['summary']['pnl'] - old['summary']['pnl']:.2f}",
        f"- ROI delta: {new['summary']['roi_pct'] - old['summary']['roi_pct']:.2f}%",
        f"- Winrate delta: {new['summary']['winrate_pct'] - old['summary']['winrate_pct']:.2f}%",
        f"- Avg edge delta: {new['summary']['avg_edge_pct'] - old['summary']['avg_edge_pct']:.2f}%",
        "",
        "## Pick diff",
        f"- Same picks: {diff['same_pick_count']}",
        f"- Changed picks: {diff['changed_pick_count']}",
        f"- Old-only picks: {diff['old_only_count']}",
        f"- New-only picks: {diff['new_only_count']}",
    ]

    if diff["changed"]:
        lines.extend(["", "## Changed picks"])
        for row in diff["changed"]:
            lines.extend(
                [
                    f"- {row['day']} | {row['match']} | {row['market_type']} {row['line']}",
                    f"  - old: {row['old']['selection']} @ {row['old']['odds_bet']:.2f} | p={row['old']['model_prob']:.4f} | result={row['old']['result']} | profit={row['old']['profit']:.2f}",
                    f"  - new: {row['new']['selection']} @ {row['new']['odds_bet']:.2f} | p={row['new']['model_prob']:.4f} | result={row['new']['result']} | profit={row['new']['profit']:.2f}",
                ]
            )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full old-vs-new 7-day paper comparison")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--provider-json", default="", help="deterministic fixtures+odds+results JSON")
    parser.add_argument("--odds-provider", choices=["sofascore"], default="sofascore")
    parser.add_argument("--results-provider", choices=["sofascore"], default="sofascore")
    parser.add_argument("--allow-synthetic-odds", action="store_true")
    parser.add_argument("--bankroll", type=float, default=2000.0)
    parser.add_argument("--out-dir", default="reports/v2/compare")
    parser.add_argument("--old-model", default="baseline")
    parser.add_argument("--new-model", default="team_strength")
    parser.add_argument("--closing-odds-tracker-sqlite", default="")
    args = parser.parse_args()

    start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    from datetime import timedelta

    end = start + timedelta(days=6)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory() as td:
        tmp = Path(td)
        old_payload = _run_model("old", args.old_model, args, tmp)
        new_payload = _run_model("new", args.new_model, args, tmp)

        report = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "provider_json": args.provider_json,
            "bankroll": float(args.bankroll),
            "old_model": old_payload,
            "new_model": new_payload,
            "diff": _build_diff(old_payload["bets"], new_payload["bets"]),
        }

        json_path = out_dir / f"paper_model_compare_7d_{end.isoformat()}.json"
        md_path = out_dir / f"paper_model_compare_7d_{end.isoformat()}.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(_render_markdown(report), encoding="utf-8")

        print(f"[COMPARE 7D] json={json_path} md={md_path}")
        print(
            "[COMPARE 7D] "
            f"old_pnl={old_payload['summary']['pnl']:.2f} new_pnl={new_payload['summary']['pnl']:.2f} "
            f"delta={new_payload['summary']['pnl'] - old_payload['summary']['pnl']:.2f} "
            f"changed_picks={report['diff']['changed_pick_count']}"
        )


if __name__ == "__main__":
    main()
