#!/usr/bin/env python3
"""Append labeled Asian Handicap (AH) match-event-history rows to an existing labeled CSV.

Inputs:
- in_csv: existing CSV (e.g., oddsportal_debug_raw_v6_labeled.csv) containing match_url/match_id

Outputs:
- out_csv: same rows + appended AH rows (market='ah') with labels:
    - outcome_ah: Home/Away
    - ah_handicap_home: handicap line relative to home team (float)
    - ah_handicap: handicap line for the *selection* (home uses home line; away uses negated home line)
    - line_label: e.g. 'AH -0.25' / 'AH +0.25'

How it works:
- match-event-history does NOT include handicapValue, only selection_key + odds history.
- We fetch match-event payload(s) for bettingTypeId=5 (AH) and scopeId in {3,4}
  to map selection_key -> handicapValue + Home/Away.
- We then fetch match-event-history with market_code '5-2' for each bookie and join labels.

Notes:
- The OddsPortal UI fragment '#asian-handicap;2' often does not actually load AH in headless.
  This script bypasses UI by calling match-event endpoints directly.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--in-csv", required=True)
    p.add_argument("--out-csv", required=True)
    p.add_argument("--decrypt-js", default="projects/aifootballbets/scripts/oddsportal_decrypt_match_event.js")
    p.add_argument("--fetch-mehist", default="projects/aifootballbets/scripts/oddsportal_fetch_mehist.py")
    p.add_argument("--capture-me", default="projects/aifootballbets/scripts/oddsportal_capture_match_event_urls.py")
    p.add_argument("--geo", default="HK")
    p.add_argument("--lang", default="en")
    p.add_argument("--bookies", default="")
    p.add_argument(
        "--scopes",
        default="2,3,4",
        help="AH scopes to try in match-event mapping (default 2,3,4). Scope=2 often matches match-event-history keys.",
    )
    p.add_argument("--market-code", default="5-2", help="match-event-history market_code for AH (default 5-2)")
    p.add_argument("--cache-dir", default="/home/openclaw/.openclaw/workspace/tmp/oddsportal_mehist_cache")
    return p.parse_args()


def iso_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def parse_match_id(match_url: str) -> str:
    seg = match_url.rstrip("/").split("/")[-1]
    return seg.split("-")[-1]


def decrypt_payload(enc: str, decrypt_js: str) -> dict[str, Any]:
    """Decrypt encrypted payload.

    Important: match-event payloads can be large, so avoid passing them as a CLI arg
    (can hit OS ARG_MAX). We pipe via stdin.
    """
    p = subprocess.run(["node", decrypt_js], input=enc, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "decrypt failed")
    return json.loads(p.stdout)


def capture_token(match_url: str, capture_me: str, geo: str, lang: str) -> str:
    """Use Playwright helper to capture at least one match-event URL and extract token/hash."""
    # We only need the token; 1X2 is enough.
    out = subprocess.check_output(
        [
            "python3",
            capture_me,
            "--match-url",
            match_url,
            "--fragment",
            "/#1x2;2",
            "--max-clicks",
            "12",
        ],
        text=True,
    )
    j = json.loads(out)
    urls = j.get("urls") or []
    # prefer bt=1 sc=2
    pick = ""
    for u in urls:
        if "/match-event/" in u and "-1-2-" in u and f"geo={geo}&lang={lang}" in u:
            pick = u
            break
    if not pick and urls:
        pick = urls[0]
    if not pick:
        return ""
    # /match-event/1-1-<matchId>-<bt>-<sc>-<token>.dat?... ; token is last dash segment
    try:
        stem = pick.split("/match-event/")[1].split(".dat")[0]
        parts = stem.split("-")
        return parts[-1]
    except Exception:
        return ""


def fetch_match_event(
    match_id: str,
    bt: int,
    sc: int,
    token: str,
    geo: str,
    lang: str,
    decrypt_js: str,
    tries: int = 3,
) -> dict[str, Any]:
    url = f"https://www.oddsportal.com/match-event/1-1-{match_id}-{bt}-{sc}-{token}.dat?geo={geo}&lang={lang}"

    last_err: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/json, text/plain, */*",
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept-Encoding": "identity",
                },
                timeout=30,
            )
            r.raise_for_status()
            j = decrypt_payload(r.text.strip(), decrypt_js)
            # Sometimes OP returns an empty d; treat as retryable
            d = j.get("d") or {}
            if bt == 5 and ("oddsdata" not in d):
                raise RuntimeError("match-event missing oddsdata")
            return j
        except Exception as e:
            last_err = e
            if attempt < tries:
                import time

                time.sleep(0.8 * attempt)
                continue
            raise

    # unreachable
    raise last_err or RuntimeError("match-event failed")


@dataclass
class AhSelInfo:
    outcome_ah: str  # Home/Away
    ah_handicap_home: float
    ah_handicap: float
    line_label: str
    scope: int


def _coerce_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def _canon_ah_key(selection_key: str) -> str:
    """Canonicalize AH selection_key for joining.

    We canonicalize to: <seg0>x<code>x<outcomeToken> (drop seg1 entirely).

    - match-event keys usually: seg0 x seg1 x code x outcomeToken
    - match-event-history keys sometimes: seg0 x seg1 x (code+outcomeToken)

    For the 3-part variant, prefer using `_canon_ah_key_with_tokens` so we can split
    (code+token) robustly.
    """
    parts = (selection_key or "").split("x")
    if len(parts) == 4:
        return f"{parts[0]}x{parts[2]}x{parts[3]}"
    # fallback heuristic only
    if len(parts) == 3:
        seg0 = parts[0]
        last = parts[2]
        if isinstance(last, str) and len(last) > 5:
            return f"{seg0}x{last[:-5]}x{last[-5:]}"
    return selection_key or ""


def _canon_ah_key_with_tokens(selection_key: str, known_tokens: set[str]) -> str:
    """Canonicalize selection_key using known outcomeToken suffixes.

    This fixes cases where token length != 5.
    """
    parts = (selection_key or "").split("x")
    if len(parts) == 4:
        return _canon_ah_key(selection_key)
    if len(parts) == 3:
        seg0 = parts[0]
        last = parts[2]
        if not isinstance(last, str):
            return _canon_ah_key(selection_key)
        # choose the longest matching token suffix
        best_tok = ""
        for tok in known_tokens:
            if tok and last.endswith(tok) and len(tok) > len(best_tok):
                best_tok = tok
        if best_tok and len(last) > len(best_tok):
            code = last[: -len(best_tok)]
            return f"{seg0}x{code}x{best_tok}"
        return _canon_ah_key(selection_key)
    return _canon_ah_key(selection_key)


def _canon_ah_key_compat(selection_key: str, seg1: str, known_tokens: set[str]) -> str:
    """Rebuild a selection_key with a different seg1, then canonicalize (token-aware)."""
    parts = (selection_key or "").split("x")
    if len(parts) == 4:
        rebuilt = f"{parts[0]}x{seg1}x{parts[2]}x{parts[3]}"
        return _canon_ah_key(rebuilt)
    if len(parts) == 3:
        rebuilt = f"{parts[0]}x{seg1}x{parts[2]}"
        return _canon_ah_key_with_tokens(rebuilt, known_tokens)
    return _canon_ah_key_with_tokens(selection_key, known_tokens)


def build_ah_selection_map(me_json: dict[str, Any], scope: int) -> dict[str, AhSelInfo]:
    out: dict[str, AhSelInfo] = {}
    d = me_json.get("d") or {}
    od = d.get("oddsdata") or {}
    back = od.get("back")
    if not isinstance(back, dict):
        return out

    # Extract the seg1 used by match-event for this scope (e.g., '4pg6k' or '4ppv4')
    seg1_set = set()
    for _, m in back.items():
        if not isinstance(m, dict):
            continue
        if int(m.get("bettingTypeId") or 0) != 5:
            continue
        if int(m.get("scopeId") or 0) != int(scope):
            continue
        oid = m.get("outcomeId")
        sels: list[str] = []
        if isinstance(oid, dict):
            sels = [x for x in [oid.get("0"), oid.get("1")] if isinstance(x, str)]
        elif isinstance(oid, list):
            sels = [x for x in oid if isinstance(x, str)]
        for s in sels:
            parts = s.split("x")
            if len(parts) == 4:
                seg1_set.add(parts[1])

    seg1_used = next(iter(seg1_set), "")

    for mk, m in back.items():
        if not isinstance(m, dict):
            continue
        if int(m.get("bettingTypeId") or 0) != 5:
            continue
        if int(m.get("scopeId") or 0) != int(scope):
            continue
        hv = _coerce_float(m.get("handicapValue"))
        if hv is None:
            continue

        outcome_id = m.get("outcomeId")
        sel_home = sel_away = None

        # outcomeId can be dict {'0': sel_home, '1': sel_away} OR list [sel_home, sel_away]
        if isinstance(outcome_id, dict):
            sel_home = outcome_id.get("0")
            sel_away = outcome_id.get("1")
        elif isinstance(outcome_id, list) and len(outcome_id) >= 2:
            sel_home = outcome_id[0]
            sel_away = outcome_id[1]

        if isinstance(sel_home, str) and sel_home:
            out[_canon_ah_key(sel_home)] = AhSelInfo(
                outcome_ah="Home",
                ah_handicap_home=float(hv),
                ah_handicap=float(hv),
                line_label=f"AH {float(hv):+g}",
                scope=int(scope),
            )
        if isinstance(sel_away, str) and sel_away:
            out[_canon_ah_key(sel_away)] = AhSelInfo(
                outcome_ah="Away",
                ah_handicap_home=float(hv),
                ah_handicap=float(-hv),
                line_label=f"AH {float(-hv):+g}",
                scope=int(scope),
            )

    # Stash seg1 used by match-event for this scope (for join-time rewriting).
    # (This is a meta-entry; we pop it out later.)
    out["__seg1_used__"] = AhSelInfo("", 0.0, 0.0, seg1_used, int(scope))

    return out


def _looks_valid_mehist(j: dict[str, Any]) -> bool:
    try:
        back = j.get("d", {}).get("history", {}).get("back", {})
        return isinstance(back, dict) and len(back) > 0
    except Exception:
        return False


def fetch_mehist(
    match_id: str,
    market_code: str,
    bookie_id: int,
    geo: str,
    lang: str,
    fetch_py: str,
    cache_dir: str,
    decrypt_js: str,
) -> dict[str, Any]:
    url = f"https://www.oddsportal.com/match-event-history/1-{match_id}-{market_code}-0-{bookie_id}/?geo={geo}&lang={lang}"
    out_path = Path(cache_dir) / f"{match_id}_{market_code}_{bookie_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _refetch() -> dict[str, Any]:
        subprocess.run(
            [
                "python3",
                fetch_py,
                "--url",
                url,
                "--out-json",
                str(out_path),
                "--decrypt-script",
                decrypt_js,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(out_path.read_text("utf-8"))

    # Read cache if present
    if out_path.exists() and out_path.stat().st_size >= 20:
        try:
            j = json.loads(out_path.read_text("utf-8"))
            if _looks_valid_mehist(j):
                return j
        except Exception:
            pass

    # (Re)fetch
    j = _refetch()
    if _looks_valid_mehist(j):
        return j

    # One more retry: cache might have been written partially
    try:
        out_path.unlink(missing_ok=True)
    except Exception:
        pass
    return _refetch()


def main() -> int:
    args = parse_args()

    in_rows = list(csv.DictReader(open(args.in_csv, encoding="utf-8")))
    if not in_rows:
        Path(args.out_csv).write_text("", encoding="utf-8")
        return 0

    # bookies default: from input file
    if args.bookies.strip():
        bookies = [int(x.strip()) for x in args.bookies.split(",") if x.strip()]
    else:
        bookies = sorted({int(r["bookie_id"]) for r in in_rows if r.get("bookie_id")})

    scopes = [int(x.strip()) for x in args.scopes.split(",") if x.strip()]

    match_urls = sorted({r["match_url"] for r in in_rows if r.get("match_url")})

    # build selection maps per match
    sel_map: dict[str, dict[str, AhSelInfo]] = {}
    token_map: dict[str, str] = {}
    # token suffixes per match_id (helps split 3-part selection keys)
    known_tokens_by_mid: dict[str, set[str]] = {}

    for mu in match_urls:
        mid = parse_match_id(mu)
        token = capture_token(mu, args.capture_me, args.geo, args.lang)
        token_map[mid] = token

        merged: dict[str, AhSelInfo] = {}
        seg1_by_scope: dict[int, str] = {}
        known_tokens: set[str] = set()

        if token:
            for sc in scopes:
                try:
                    me = fetch_match_event(mid, bt=5, sc=sc, token=token, geo=args.geo, lang=args.lang, decrypt_js=args.decrypt_js)
                    m = build_ah_selection_map(me, sc)
                    marker = m.pop("__seg1_used__", None)
                    if marker and marker.line_label:
                        seg1_by_scope[int(marker.scope)] = marker.line_label
                    # collect outcome tokens from canon keys (seg2 is token in our canon)
                    for ck in m.keys():
                        # ck format seg0xcodextok
                        ps = ck.split("x")
                        if len(ps) == 3:
                            known_tokens.add(ps[2])
                    merged.update(m)
                except Exception:
                    continue

        sel_map[mid] = merged
        sel_map[mid]["__seg1_by_scope__"] = seg1_by_scope  # type: ignore
        known_tokens_by_mid[mid] = known_tokens

    # pick meta rows for each match_url
    meta_by_mu: dict[str, dict[str, str]] = {}
    for r in in_rows:
        mu = r.get("match_url")
        if mu and mu not in meta_by_mu:
            meta_by_mu[mu] = {
                "match_date_utc": r.get("match_date_utc", ""),
                "home_team": r.get("home_team", ""),
                "away_team": r.get("away_team", ""),
                "match_url": mu,
                "match_id": r.get("match_id", parse_match_id(mu)),
            }

    out_rows = list(in_rows)

    for mu in match_urls:
        mid = parse_match_id(mu)
        meta = meta_by_mu.get(mu, {})
        for b in bookies:
            try:
                d = fetch_mehist(mid, args.market_code, b, args.geo, args.lang, args.fetch_mehist, args.cache_dir, args.decrypt_js)
            except Exception:
                continue
            back = d.get("d", {}).get("history", {}).get("back", {})
            if not isinstance(back, dict) or not back:
                continue
            for sel_key, inner in back.items():
                points = inner.get(str(b), []) if isinstance(inner, dict) else []
                for odd_str, _, ts in points:
                    ts_i = int(ts)
                    known_tokens = known_tokens_by_mid.get(mid, set())
                    ck = _canon_ah_key_with_tokens(sel_key, known_tokens)
                    info = sel_map.get(mid, {}).get(ck)
                    if not info:
                        # Try rewriting seg1 to match match-event's seg1 for each scope
                        seg1_by_scope = sel_map.get(mid, {}).get("__seg1_by_scope__", {})  # type: ignore
                        for _sc, seg1 in (seg1_by_scope or {}).items():
                            if not seg1:
                                continue
                            ck2 = _canon_ah_key_compat(sel_key, seg1, known_tokens)
                            info = sel_map.get(mid, {}).get(ck2)
                            if info:
                                break
                    # create a row with same schema as input
                    r: dict[str, Any] = {k: "" for k in in_rows[0].keys()}
                    r.update(meta)
                    r.update(
                        {
                            "market": "ah",
                            "bookie_id": str(b),
                            "selection_key": sel_key,
                            "ts": str(ts_i),
                            "ts_utc": iso_utc(ts_i),
                            "odds": str(float(odd_str)),
                            "ou_side_base": "",
                            "ou_line_code": "",
                            "outcome_1x2": "",
                            "outcome_1x2_label": "",
                            "outcome_ou": "",
                        }
                    )
                    if info:
                        r["line_label"] = info.line_label
                    else:
                        r["line_label"] = ""
                    # Store AH-specific columns (added later)
                    r["outcome_ah"] = info.outcome_ah if info else ""
                    r["ah_handicap_home"] = f"{info.ah_handicap_home:+g}" if info else ""
                    r["ah_handicap"] = f"{info.ah_handicap:+g}" if info else ""
                    r["ah_scope"] = str(info.scope) if info else ""

                    out_rows.append(r)

    # Ensure new columns exist
    base_fields = list(in_rows[0].keys())
    extra = ["outcome_ah", "ah_handicap_home", "ah_handicap", "ah_scope"]
    fieldnames = base_fields + [c for c in extra if c not in base_fields]

    Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in out_rows:
            # fill missing keys
            for c in extra:
                r.setdefault(c, "")
            w.writerow({k: r.get(k, "") for k in fieldnames})

    summary = {
        "in_rows": len(in_rows),
        "out_rows": len(out_rows),
        "n_matches": len(match_urls),
        "bookies": bookies,
        "market_code": args.market_code,
        "scopes": scopes,
        "out": args.out_csv,
        "token_map": token_map,
        "mapped_counts": {mid: len(sel_map.get(mid, {})) for mid in sel_map},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
