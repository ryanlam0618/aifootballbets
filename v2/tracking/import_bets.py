from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
import sqlite3
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from v2.tracking.xlsx_reader import read_first_sheet_rows

HKT = timezone(timedelta(hours=8))
EXCEL_EPOCH = datetime(1899, 12, 30, tzinfo=HKT)

HEADER_ALIASES = {
    "date": "bet_time_hkt",
    "datetime": "bet_time_hkt",
    "league": "league",
    "home": "home",
    "away": "away",
    "market": "market",
    "line": "line",
    "selection": "selection",
    "odds": "odds_bet",
    "model prob": "model_prob",
    "model_prob": "model_prob",
    "ev": "ev",
    "kelly %": "kelly_pct",
    "kelly": "kelly_pct",
    "stake ($)": "stake",
    "stake": "stake",
    "result (win/loss)": "result",
    "result": "result",
    "profit": "profit",
    "bankroll": "bankroll",
    "bank roll": "bankroll",
    "notes": "notes",
    "reason": "notes",
    "source_book": "source_book",
    "kickoff": "kickoff_time_hkt",
    "kickoff time": "kickoff_time_hkt",
    "kickoff_time": "kickoff_time_hkt",
    "match time": "kickoff_time_hkt",
}

TARGET_COLUMNS = [
    "bet_id",
    "bet_time_hkt",
    "kickoff_time_hkt",
    "closing_time_hkt",
    "league",
    "home",
    "away",
    "market",
    "market_type",
    "line",
    "selection",
    "odds_bet",
    "model_prob",
    "ev",
    "kelly_pct",
    "stake",
    "result",
    "profit",
    "bankroll",
    "notes",
    "source_book",
    "source_file",
    "run_id",
    "odds_close",
    "clv_abs",
    "clv_pct",
]


def _norm_key(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _is_blank_row(row: Sequence[str]) -> bool:
    return all((str(x).strip() == "") for x in row)


def detect_header(rows: Sequence[Sequence[str]]) -> Tuple[int, Dict[int, str]]:
    best_idx = 0
    best_score = -1
    best_map: Dict[int, str] = {}

    for i, row in enumerate(rows[:20]):
        idx_to_field: Dict[int, str] = {}
        score = 0
        for j, cell in enumerate(row):
            key = _norm_key(cell)
            field = HEADER_ALIASES.get(key)
            if field:
                idx_to_field[j] = field
                score += 1

        if score > best_score:
            best_score = score
            best_idx = i
            best_map = idx_to_field

    if best_score < 4:
        raise ValueError("Unable to detect header row reliably")

    return best_idx, best_map


def parse_datetime_hkt(value: str) -> Optional[str]:
    v = (value or "").strip()
    if not v:
        return None

    # Excel serial date/time
    if re.match(r"^-?\d+(\.\d+)?$", v):
        try:
            serial = float(v)
            dt = EXCEL_EPOCH + timedelta(days=serial)
            return dt.replace(microsecond=0).isoformat(timespec="seconds")
        except Exception:
            pass

    # ISO-like strings
    candidates = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in candidates:
        try:
            dt = datetime.strptime(v, fmt).replace(tzinfo=HKT)
            return dt.isoformat(timespec="seconds")
        except Exception:
            continue

    # Try fromisoformat fallback
    try:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=HKT)
        else:
            dt = dt.astimezone(HKT)
        return dt.replace(microsecond=0).isoformat(timespec="seconds")
    except Exception:
        return None


def _to_float(value: str) -> Optional[float]:
    v = (value or "").strip()
    if not v:
        return None
    v = v.replace(",", "")
    try:
        return float(v)
    except Exception:
        return None


def _to_result(value: str) -> str:
    v = (value or "").strip().lower()
    if not v:
        return ""
    if v.startswith("w"):
        return "win"
    if v.startswith("l"):
        return "loss"
    if v.startswith("d") or v.startswith("p"):
        return "push"
    return v


def parse_market_and_line(market: str, existing_line: str = "") -> Tuple[str, str, str]:
    raw = (market or "").strip()
    line = (existing_line or "").strip()
    market_type = raw

    if not raw:
        return "", "", line

    s = raw.lower()

    m = re.match(r"^(asian\s*handicap)\s*([+-]?\d+(?:\.\d+)?)$", s, flags=re.I)
    if m:
        market_type = "Asian Handicap"
        if not line:
            line = m.group(2)
        return raw, market_type, line

    m = re.match(r"^(over\s*/?\s*under)\s*([+-]?\d+(?:\.\d+)?)$", s, flags=re.I)
    if m:
        market_type = "Over/Under"
        if not line:
            line = m.group(2)
        return raw, market_type, line

    if s in {"1x2", "1x2 ", "1x2 market"} or s.replace(" ", "") == "1x2":
        market_type = "1X2"
        return raw, market_type, line

    # Generic trailing numeric line parser
    m = re.match(r"^(.*?)[\s:]+([+-]?\d+(?:\.\d+)?)$", raw)
    if m:
        base = m.group(1).strip()
        if not line:
            line = m.group(2)
        market_type = base

    return raw, market_type, line


def compute_bet_id(rec: Dict[str, object]) -> str:
    material = "|".join(
        [
            str(rec.get("bet_time_hkt") or ""),
            str(rec.get("league") or ""),
            str(rec.get("home") or ""),
            str(rec.get("away") or ""),
            str(rec.get("market") or ""),
            str(rec.get("line") or ""),
            str(rec.get("selection") or ""),
            str(rec.get("odds_bet") or ""),
        ]
    )
    return hashlib.sha1(material.encode("utf-8")).hexdigest()[:16]


def transform_rows(rows: List[List[str]], source_file: str, run_id: str, source_book: str) -> List[Dict[str, object]]:
    h_idx, mapping = detect_header(rows)
    out: List[Dict[str, object]] = []

    for row in rows[h_idx + 1 :]:
        if _is_blank_row(row):
            continue

        raw: Dict[str, str] = {}
        for col_idx, field in mapping.items():
            raw[field] = row[col_idx].strip() if col_idx < len(row) else ""

        # Minimal required keys to consider a bet row
        if not raw.get("home") and not raw.get("away") and not raw.get("market"):
            continue

        bet_time_hkt = parse_datetime_hkt(raw.get("bet_time_hkt", ""))
        market_raw, market_type, line = parse_market_and_line(raw.get("market", ""), raw.get("line", ""))

        kickoff_time_hkt = parse_datetime_hkt(raw.get("kickoff_time_hkt", ""))
        closing_time_hkt = None
        if kickoff_time_hkt:
            try:
                kickoff_dt = datetime.fromisoformat(kickoff_time_hkt)
                closing_time_hkt = (kickoff_dt - timedelta(minutes=5)).replace(microsecond=0).isoformat(timespec="seconds")
            except Exception:
                closing_time_hkt = None

        rec: Dict[str, object] = {
            "bet_id": "",
            "bet_time_hkt": bet_time_hkt,
            "kickoff_time_hkt": kickoff_time_hkt,
            "closing_time_hkt": closing_time_hkt,
            "league": raw.get("league", "") or None,
            "home": raw.get("home", "") or None,
            "away": raw.get("away", "") or None,
            "market": market_raw or None,
            "market_type": market_type or None,
            "line": line or None,
            "selection": raw.get("selection", "") or None,
            "odds_bet": _to_float(raw.get("odds_bet", "")),
            "model_prob": _to_float(raw.get("model_prob", "")),
            "ev": _to_float(raw.get("ev", "")),
            "kelly_pct": _to_float(raw.get("kelly_pct", "")),
            "stake": _to_float(raw.get("stake", "")),
            "result": _to_result(raw.get("result", "")),
            "profit": _to_float(raw.get("profit", "")),
            "bankroll": _to_float(raw.get("bankroll", "")),
            "notes": raw.get("notes", "") or None,
            "source_book": raw.get("source_book", "") or source_book,
            "source_file": source_file,
            "run_id": run_id,
            "odds_close": None,
            "clv_abs": None,
            "clv_pct": None,
        }
        rec["bet_id"] = compute_bet_id(rec)
        out.append(rec)

    return out


def _ensure_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def write_csv(records: Sequence[Dict[str, object]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TARGET_COLUMNS)
        w.writeheader()
        for r in records:
            w.writerow({k: r.get(k) for k in TARGET_COLUMNS})


def write_sqlite(records: Sequence[Dict[str, object]], db_path: Path, schema_path: Path) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_schema(conn, schema_path)

        sql = """
        INSERT INTO bet_log (
            bet_id, bet_time_hkt, kickoff_time_hkt, closing_time_hkt,
            league, home, away,
            market, market_type, line, selection,
            odds_bet, model_prob, ev, kelly_pct, stake,
            result, profit, bankroll,
            notes, source_book, source_file, run_id,
            odds_close, clv_abs, clv_pct
        ) VALUES (
            :bet_id, :bet_time_hkt, :kickoff_time_hkt, :closing_time_hkt,
            :league, :home, :away,
            :market, :market_type, :line, :selection,
            :odds_bet, :model_prob, :ev, :kelly_pct, :stake,
            :result, :profit, :bankroll,
            :notes, :source_book, :source_file, :run_id,
            :odds_close, :clv_abs, :clv_pct
        )
        """
        inserted = 0
        for r in records:
            try:
                conn.execute(sql, r)
                inserted += 1
            except sqlite3.IntegrityError:
                # duplicate bet_id (idempotent re-import)
                pass
        conn.commit()
        return inserted
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import betting records XLSX -> normalized CSV/SQLite")
    parser.add_argument("--xlsx", required=True, help="Path to source xlsx")
    parser.add_argument("--out-csv", default="", help="Optional normalized CSV output")
    parser.add_argument("--sqlite", default="", help="Optional sqlite db output")
    parser.add_argument("--schema", default="v2/tracking/schema.sql", help="SQLite schema path")
    parser.add_argument("--source-book", default="sport pp88", help="Default sportsbook label")
    parser.add_argument("--run-id", default="", help="Optional run id")
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        raise SystemExit(f"XLSX not found: {xlsx_path}")

    run_id = args.run_id or datetime.now(timezone.utc).strftime("import_%Y%m%dT%H%M%SZ")
    rows = read_first_sheet_rows(xlsx_path)
    records = transform_rows(rows, source_file=str(xlsx_path), run_id=run_id, source_book=args.source_book)

    print(f"Parsed rows: {len(rows)}")
    print(f"Bet records: {len(records)}")

    if args.out_csv:
        out_csv = Path(args.out_csv)
        write_csv(records, out_csv)
        print(f"Wrote CSV: {out_csv}")

    if args.sqlite:
        db_path = Path(args.sqlite)
        schema_path = Path(args.schema)
        inserted = write_sqlite(records, db_path=db_path, schema_path=schema_path)
        print(f"Inserted into SQLite: {inserted} -> {db_path}")


if __name__ == "__main__":
    main()
