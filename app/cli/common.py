# -*- coding: utf-8 -*-
"""Shared CLI bootstrap: repo root, env, sys.path, helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# app/cli/common.py → parents[2] = nanobot-bio repo root
ROOT = Path(__file__).resolve().parents[2]

try:
    from app.dotenv_util import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass

BIO_ROOT = Path(os.environ.get("BIO_ROOT", ROOT.parent)).expanduser().resolve()
os.environ.setdefault("BIO_ROOT", str(BIO_ROOT))
os.environ.setdefault("NANOBOT_BIO_ROOT", str(ROOT))
os.environ.setdefault("NANOBOT_SRC", str(ROOT / "nanobot"))

_rt = str(ROOT)
_br = str(BIO_ROOT)
for _p in (_rt, _br):
    while _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, _rt)
if _br != _rt:
    sys.path.insert(1, _br)


def read_fasta(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    return "".join(ln.strip() for ln in lines if ln.strip() and not ln.startswith(">"))
