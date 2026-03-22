from __future__ import annotations

import argparse
import json

from v2.manual_execution.pinchtab_client import health, load_pinchtab_config


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe PinchTab connectivity")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg = load_pinchtab_config()
    out = {"base_url": cfg.base_url, "has_token": bool(cfg.token)}
    try:
        out["health"] = health(cfg)
        out["ok"] = True
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(out)

    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
