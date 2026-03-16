#!/usr/bin/env bash
set -euo pipefail

# Reproducible local env bootstrap for systems where python3 lacks ensurepip.
# Usage:
#   bash scripts/setup_env.sh
#   bash scripts/setup_env.sh --recreate

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RECREATE=0
if [[ "${1:-}" == "--recreate" ]]; then
  RECREATE=1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
USER_PIP="${HOME}/.local/bin/pip"
USER_VIRTUALENV="${HOME}/.local/bin/virtualenv"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[error] python3 not found"
  exit 1
fi

if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  echo "[info] system pip missing; bootstrapping user pip via get-pip.py"
  "$PYTHON_BIN" -c "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py','get-pip.py')"
  "$PYTHON_BIN" get-pip.py --user
fi

if [[ ! -x "$USER_PIP" ]]; then
  echo "[error] expected pip at $USER_PIP"
  exit 1
fi

if [[ ! -x "$USER_VIRTUALENV" ]]; then
  echo "[info] installing virtualenv in user site-packages"
  "$USER_PIP" install --user virtualenv
fi

if [[ "$RECREATE" -eq 1 && -d .venv ]]; then
  mv .venv ".venv.bak.$(date +%Y%m%d-%H%M%S)"
fi

if [[ ! -f .venv/bin/pip ]]; then
  echo "[info] creating .venv with virtualenv"
  "$USER_VIRTUALENV" -p "$(command -v "$PYTHON_BIN")" .venv
fi

.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt lxml

# Light sanity checks
.venv/bin/python -c "import dotenv, requests, pandas; print('import-ok')"
.venv/bin/python scripts/paper_one_day.py --help >/dev/null

echo "[ok] environment ready: $ROOT_DIR/.venv"
