"""MySQL connection helpers for the afb_* data layer.

Credential resolution order:
1. AFB_MYSQL_* environment variables (normally provided via repo `.env`)
2. Fallback: read MYSQL_* keys from a shared credentials file given by
   AFB_CREDENTIALS_ENV (default: the sofascore-backfill `.env`). Only the
   PATH is referenced here — no credential values ever live in this repo.

Under pytest the MySQL backend is hard-disabled so the test suite stays
hermetic (deterministic CSV/baseline path); the DB path is covered by
scripts/smoke_db_layer.py instead.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from config import settings_v2

_DEFAULT_CRED_ENV = "/root/.openclaw/workspace/sofascore-backfill/.env"


def _under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules


def _load_fallback_creds() -> dict:
    """Read MYSQL_* keys from the shared credentials file (path only, no values)."""
    path = Path(os.getenv("AFB_CREDENTIALS_ENV", _DEFAULT_CRED_ENV))
    out: dict = {}
    if not path.exists():
        return out
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k in {"MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"}:
                out[k] = v
    except Exception:
        return {}
    return out


def _cfg() -> dict:
    c = {
        "host": os.getenv("AFB_MYSQL_HOST", ""),
        "port": os.getenv("AFB_MYSQL_PORT", ""),
        "user": os.getenv("AFB_MYSQL_USER", ""),
        "password": os.getenv("AFB_MYSQL_PASSWORD", ""),
        "database": os.getenv("AFB_MYSQL_DATABASE", ""),
    }
    if not c["user"] or not c["password"]:
        fb = _load_fallback_creds()
        c["host"] = c["host"] or fb.get("MYSQL_HOST", "127.0.0.1")
        c["port"] = c["port"] or fb.get("MYSQL_PORT", "3306")
        c["user"] = c["user"] or fb.get("MYSQL_USER", "")
        c["password"] = c["password"] or fb.get("MYSQL_PASSWORD", "")
        c["database"] = c["database"] or fb.get("MYSQL_DATABASE", "appdb")
    return {
        "host": c["host"] or "127.0.0.1",
        "port": int(c["port"] or 3306),
        "user": c["user"],
        "password": c["password"],
        "database": c["database"] or "appdb",
    }


def afb_mysql_connect(ensure_schema: bool = True):
    """Open a PyMySQL connection to the afb database.

    Raises RuntimeError with a clear message when not configured.
    """
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover - environment issue
        raise RuntimeError("pymysql is not installed; cannot use MySQL backend") from exc

    c = _cfg()
    if not c["user"] or not c["password"]:
        raise RuntimeError(
            "AFB_MYSQL_USER / AFB_MYSQL_PASSWORD not configured; "
            "set them in .env (names only in .env.example)"
        )
    if _under_pytest():
        raise RuntimeError("mysql backend disabled under pytest (hermetic tests)")

    conn = pymysql.connect(
        host=c["host"],
        port=c["port"],
        user=c["user"],
        password=c["password"],
        database=c["database"],
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=10,
        read_timeout=600,
        write_timeout=600,
    )
    if ensure_schema:
        from afbdb.schema import ensure_afb_schema

        ensure_afb_schema(conn)
    return conn


def afb_mysql_available() -> bool:
    """True when a connection can be established and schema ensured."""
    try:
        conn = afb_mysql_connect(ensure_schema=True)
    except Exception:
        return False
    try:
        conn.close()
    except Exception:
        pass
    return True


def is_db_history_backend() -> bool:
    """History backend switch: 'db' (default) with graceful CSV fallback."""
    return str(getattr(settings_v2, "afb_history_backend", "db")).strip().lower() == "db"


def is_bets_mirror_enabled() -> bool:
    return bool(getattr(settings_v2, "afb_bets_mirror_db", False))


def is_snapshots_db_enabled() -> bool:
    return bool(getattr(settings_v2, "afb_snapshots_db", False))


def new_run_id(prefix: str = "run") -> str:
    from datetime import datetime, timezone

    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


__all__ = [
    "afb_mysql_available",
    "afb_mysql_connect",
    "is_bets_mirror_enabled",
    "is_db_history_backend",
    "is_snapshots_db_enabled",
    "new_run_id",
    "Optional",
]
