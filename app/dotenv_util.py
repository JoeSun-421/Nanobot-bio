# -*- coding: utf-8 -*-
"""Load nanobot-bio/.env into os.environ (do not override existing exports)."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path | None = None, *, override: bool = False) -> Path | None:
    """Parse KEY=VALUE lines from ``.env``. Returns path if loaded, else None."""
    if path is None:
        # app/dotenv_util.py → parents[1] = nanobot-bio
        path = Path(__file__).resolve().parents[1] / ".env"
    path = path.expanduser()
    if not path.is_file():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = val
    return path
