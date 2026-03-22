# PinchTab integration (manual execution)

This project supports **manual execution** (human confirms bets) and can use **PinchTab** to speed up navigation and data capture.

## Where PinchTab runs

PinchTab should run on the same machine where you place bets (the bookmaker host / browser host).

In Kris' current setup:

- Host: `192.168.0.182`
- PinchTab binary: `/opt/pinchtab-084/pinchtab`
- Service: `pinchtab084.service` (systemd)
- Config: `/root/.config/pinchtab/config.json`
- Dashboard (local): `http://localhost:19867`

PinchTab `/health` returns **401** without auth.

## Env vars

Set these in the environment where *the automation client runs* (ideally on the same host as PinchTab):

- `PINCHTAB_BASE_URL` (default: `http://127.0.0.1:19867`)
- `PINCHTAB_TOKEN` (required)

Example:

```bash
export PINCHTAB_BASE_URL=http://127.0.0.1:19867
export PINCHTAB_TOKEN=... # copy from pinchtab config output
python -m v2.manual_execution.pinchtab_probe --json
```

## Quick probe

```bash
python -m v2.manual_execution.pinchtab_probe --json
```

If it fails with 401: token missing.
If it fails with connection refused: PinchTab is not reachable from this machine (run the client on the browser host or forward the port securely).
