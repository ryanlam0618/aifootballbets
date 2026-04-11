from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from openai import OpenAI

from config import settings_v2


def _safe_player_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or item.get("player") or "Unknown")
    return str(item)


def _format_lineup_block(lineup: dict | None, side_key: str) -> str:
    if not lineup:
        return "N/A"
    team = (lineup.get(side_key) or {})
    name = team.get("name", side_key)
    formation = team.get("formation", "Unknown")
    starters = team.get("starters", []) or []
    subs = team.get("substitutes", []) or []

    st_names = [f"{p.get('name', 'Unknown')}" for p in starters]
    sb_names = [f"{_safe_player_name(p)}" for p in subs]
    return (
        f"[{name}] Formation: {formation}\n"
        f"Starters: {', '.join(st_names) if st_names else 'N/A'}\n"
        f"Subs: {', '.join(sb_names) if sb_names else 'N/A'}"
    )


def collect_lineup_and_injury(
    home_team: str,
    away_team: str,
    match_date: str,
    *,
    match_id: str | None = None,
    kickoff_time_utc: str | None = None,
) -> Dict[str, Any]:
    """Collect lineup + injuries.

    Default OFF (no network) unless:
      SOFASCORE_ENABLED=1

    Schema must stay stable so downstream pipeline continues working.
    """

    # v2 standalone fallback (no v1 src dependencies)
    lineup = {
        "home_team": {"name": home_team, "formation": "Unknown", "starters": [], "substitutes": []},
        "away_team": {"name": away_team, "formation": "Unknown", "starters": [], "substitutes": []},
        "source": "v2-standalone-fallback",
    }
    injury = {
        "home": {"injuries": [], "suspensions": [], "total_impact": 0.0},
        "away": {"injuries": [], "suspensions": [], "total_impact": 0.0},
        "source": "v2-standalone-fallback",
    }

    try:
        from ingest.sofascore_lineup import fetch_lineup_and_injury, sofascore_enabled

        if sofascore_enabled():
            # Save raw JSON responses for audit/backtest replay.
            raw_dir = Path("data") / "v2" / "sofascore_raw"
            payload = fetch_lineup_and_injury(
                home_team=home_team,
                away_team=away_team,
                match_date=match_date,
                match_id=match_id,
                kickoff_time_utc=kickoff_time_utc,
                raw_dir=raw_dir,
                sleep_s=0.2,
            )
            if isinstance(payload, dict) and payload.get("lineup"):
                return payload
    except Exception:
        # never fail the main pipeline
        pass

    return {
        "lineup": lineup,
        "injury": injury,
        "sofascore_features": {
            "lineup_confirmed": None,
            "home": {"missing_count": 0, "doubtful_count": 0, "missing_by_position": {}},
            "away": {"missing_count": 0, "doubtful_count": 0, "missing_by_position": {}},
        },
    }


def grok_research(home_team: str, away_team: str, match_date: str) -> str:
    if not settings_v2.grok_api_key:
        return "[Grok disabled] GROK_API_KEY missing"

    prompt = f"""
Match: {home_team} vs {away_team}
Date: {match_date}
Task:
1) Search X/Twitter and trusted football reporters
2) Extract probable XI, confirmed XI (if any), and key injuries/suspensions
3) Include source links with UTC timestamp
4) Keep concise and factual
""".strip()

    try:
        client = OpenAI(base_url=settings_v2.network_api_url, api_key=settings_v2.grok_api_key)
        resp = client.chat.completions.create(
            model=settings_v2.model_grok,
            messages=[
                {"role": "system", "content": "You are a football news researcher. Return evidence-based notes."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip() if resp and resp.choices else "[Grok empty]"
    except Exception as e:
        return f"[Grok error] {e}"


def write_lineup_text(
    match_id: str,
    home_team: str,
    away_team: str,
    payload: Dict[str, Any],
    grok_text: str,
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    lineup = payload.get("lineup")
    injury = payload.get("injury") or {}

    home_inj = injury.get("home", {}).get("injuries", []) or []
    away_inj = injury.get("away", {}).get("injuries", []) or []

    text = [
        f"Match: {home_team} vs {away_team}",
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        "== Lineup ==",
        _format_lineup_block(lineup, "home_team"),
        "",
        _format_lineup_block(lineup, "away_team"),
        "",
        "== Injuries / Suspensions ==",
        f"Home ({len(home_inj)}): " + ", ".join([_safe_player_name(x) for x in home_inj]) if home_inj else "Home: none",
        f"Away ({len(away_inj)}): " + ", ".join([_safe_player_name(x) for x in away_inj]) if away_inj else "Away: none",
        "",
        "== Grok Research (X + web) ==",
        grok_text or "N/A",
        "",
    ]

    out_path = out_dir / f"{match_id}_lineup_text.txt"
    out_path.write_text("\n".join(text), encoding="utf-8")
    return out_path


def injury_rows(match_id: str, home_team: str, away_team: str, injury_report: Dict[str, Any]) -> List[dict]:
    rows: list[dict] = []
    source = injury_report.get("source", "unknown")

    for side_key, team_name in [("home", home_team), ("away", away_team)]:
        side = injury_report.get(side_key, {}) or {}
        for x in side.get("injuries", []) or []:
            rows.append(
                {
                    "match_id": match_id,
                    "team_side": side_key,
                    "team_name": team_name,
                    "player_name": _safe_player_name(x),
                    "status": x.get("type", "injury") if isinstance(x, dict) else "injury",
                    "detail": x.get("reason", x.get("description", "")) if isinstance(x, dict) else "",
                    "impact_score": x.get("impact_score") if isinstance(x, dict) else None,
                    "source": source,
                }
            )
        for x in side.get("suspensions", []) or []:
            rows.append(
                {
                    "match_id": match_id,
                    "team_side": side_key,
                    "team_name": team_name,
                    "player_name": _safe_player_name(x),
                    "status": "suspension",
                    "detail": x.get("reason", x.get("description", "")) if isinstance(x, dict) else "",
                    "impact_score": x.get("impact_score") if isinstance(x, dict) else None,
                    "source": source,
                }
            )
    return rows


def injuries_to_csv(rows: List[dict], out_csv: Path) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    return df
