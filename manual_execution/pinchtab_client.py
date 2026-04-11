from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class PinchTabConfig:
    base_url: str
    token: str | None = None


def load_pinchtab_config() -> PinchTabConfig:
    """Load PinchTab connection settings.

    In our deployment, PinchTab runs on the execution host (Kris' machine / node).
    The aifootballbets runner should talk to it over localhost on that host.
    """

    base_url = os.getenv("PINCHTAB_BASE_URL", "http://127.0.0.1:19867").rstrip("/")
    token = os.getenv("PINCHTAB_TOKEN")
    return PinchTabConfig(base_url=base_url, token=token)


def _req(url: str, token: str | None = None) -> urllib.request.Request:
    req = urllib.request.Request(url)
    if token:
        # PinchTab returns 401 on /health without auth.
        req.add_header("Authorization", f"Bearer {token}")
    return req


def health(cfg: PinchTabConfig) -> dict:
    url = f"{cfg.base_url}/health"
    with urllib.request.urlopen(_req(url, cfg.token), timeout=5) as r:
        data = r.read().decode("utf-8", "ignore")
    return json.loads(data)


def post_json(cfg: PinchTabConfig, path: str, payload: dict, timeout_s: int = 20) -> dict:
    full = f"{cfg.base_url}{path}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(full, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if cfg.token:
        req.add_header("Authorization", f"Bearer {cfg.token}")
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
        data = r.read().decode("utf-8", "ignore")
    return json.loads(data)
