"""Test/runtime bootstrap.

Pytest sometimes runs with a sys.path that does NOT include the repo root,
which breaks imports like `import v2` used throughout this project.

Python automatically imports `sitecustomize` (if present on sys.path) during
startup, so we use it to ensure the repository root is importable.

This keeps `pytest` and `python -m pytest` consistent.
"""

from __future__ import annotations

import os
import sys


def _ensure_repo_root_on_syspath() -> None:
    repo_root = os.path.dirname(__file__)
    if repo_root and repo_root not in sys.path:
        # Prepend so local code wins over any installed packages with same name.
        sys.path.insert(0, repo_root)


_ensure_repo_root_on_syspath()
