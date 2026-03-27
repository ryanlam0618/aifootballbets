#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import requests


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch and decrypt OddsPortal match-event-history payload")
    p.add_argument("--url", required=True)
    p.add_argument("--out-json", required=True)
    p.add_argument("--decrypt-script", default="scripts/oddsportal_decrypt_match_event.js")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    enc = requests.get(
        args.url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Accept-Encoding": "identity",
        },
        timeout=30,
    ).text.strip()

    p = subprocess.run(["node", args.decrypt_script, "--in", enc], capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(p.stderr.strip() or "decrypt failed")

    Path(args.out_json).write_text(p.stdout, encoding="utf-8")
    print(json.dumps({"url": args.url, "out": args.out_json, "bytes": len(p.stdout)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
