#!/usr/bin/env python3
"""Layer-1 smoke test: fixtures from DB -> goal model -> pricing -> DB round-trip.

Steps:
1. Connect to MySQL (afb_* schema ensured)
2. Load history index from DB (matches + shotmap xG)
3. Pick one recent finished match from a repo-universe league; as-of that
   match's date, build the goal model for its two teams
4. Price 1X2 + O/U 2.5 + AH 0.5 via Poisson matrix (same math as paper/strategy)
5. Write a snapshot + prediction row (run_id prefixed SMOKE_), read them back,
   then DELETE the smoke rows (DELETE privilege granted; no DROP needed)
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from afbdb.connection import afb_mysql_connect  # noqa: E402
from afbdb.history import build_history_index, fetch_history_rows  # noqa: E402
from paper.providers import normalize_team  # noqa: E402
from paper.team_strength import estimate_match_goal_model  # noqa: E402
from paper.strategy import _prob_1x2, _prob_over, _prob_home_ah, _score_matrix  # noqa: E402

RUN_ID = f"SMOKE_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
LEAGUE = "Premier League"


def main() -> int:
    conn = afb_mysql_connect()
    print(f"[1] connected; afb_* schema ensured (run_id={RUN_ID})")

    rows = fetch_history_rows(conn, min_date=str(__import__("config").settings_v2.afb_history_min_date))
    index = build_history_index(rows, normalize_team)
    print(f"[2] history index from DB: {len(rows)} finished matches, {len(index['team_rows'])} teams")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.match_id, m.match_date, th.name, ta.name
            FROM matches m
            JOIN competitions c ON c.competition_id = m.competition_id
            JOIN teams th ON th.team_id = m.home_team_id
            JOIN teams ta ON ta.team_id = m.away_team_id
            WHERE c.name = %s AND m.status = 'finished'
            ORDER BY m.match_date DESC LIMIT 1
            """,
            (LEAGUE,),
        )
        mid, mdate, home, away = cur.fetchone()
    print(f"[3] sample match: {home} vs {away} ({mdate}, match_id={mid})")

    ref_day = mdate if isinstance(mdate, date) else date.fromisoformat(str(mdate))
    model = estimate_match_goal_model("soccer_epl", LEAGUE, home, away, ref_day)
    print(f"[3] goal model: mu_h={model.mu_home:.3f} mu_a={model.mu_away:.3f} "
          f"(home att {model.home_strength.attack:.3f} / away def {model.away_strength.defense:.3f})")

    mat = _score_matrix(model.mu_home, model.mu_away, max_goals=10)
    p1x2 = _prob_1x2(mat)
    p_over = _prob_over(mat, 2.5)
    p_ah = _prob_home_ah(mat, 0.5)
    print(f"[4] pricing: 1X2 H/D/A = {p1x2['Home']:.3f}/{p1x2['Draw']:.3f}/{p1x2['Away']:.3f} | "
          f"O2.5={p_over:.3f} | AH0.5 Home={p_ah:.3f}")

    # --- round-trip: snapshot + prediction write/read/delete ---
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO afb_odds_snapshots
              (match_id, source, league_key, league_name, home_team, away_team,
               market_key, selection, odds, captured_at_utc, run_id)
            VALUES (%s,'smoke',%s,%s,%s,%s,'Over/Under 2.5','Over',%s,NOW(),%s)
            """,
            (str(mid), "soccer_epl", LEAGUE, home, away, 1.90, RUN_ID),
        )
        cur.execute(
            """
            INSERT INTO afb_predictions
              (run_id, run_date, match_id, league, home_team, away_team,
               market, line, selection, model_probability, model_name)
            VALUES (%s,%s,%s,%s,%s,%s,'Over/Under','2.5','Over',%s,'smoke')
            """,
            (RUN_ID, ref_day.isoformat(), str(mid), LEAGUE, home, away, round(p_over, 6)),
        )
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM afb_odds_snapshots WHERE run_id=%s", (RUN_ID,))
        n_snap = cur.fetchone()[0]
        cur.execute("SELECT model_probability FROM afb_predictions WHERE run_id=%s", (RUN_ID,))
        pred_back = float(cur.fetchone()[0])
    print(f"[5] round-trip: snapshot rows={n_snap}, prediction model_prob readback={pred_back:.6f}")
    assert n_snap == 1 and abs(pred_back - p_over) < 1e-5, "round-trip mismatch"

    with conn.cursor() as cur:
        cur.execute("DELETE FROM afb_odds_snapshots WHERE run_id=%s", (RUN_ID,))
        cur.execute("DELETE FROM afb_predictions WHERE run_id=%s", (RUN_ID,))
        deleted = cur.rowcount
    conn.commit()
    conn.close()
    print(f"[6] cleanup: smoke rows deleted ({deleted} prediction row)")
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
