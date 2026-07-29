# -*- coding: utf-8 -*-
"""ColabFold MSA HTTP 429: classify + do not poison structure cache."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nanobot.agent.tools.rbp.structure import (  # noqa: E402
    _classify_af3_failure,
    _is_colabfold_rate_limit,
)


def test_detect_colabfold_http_429():
    assert _is_colabfold_rate_limit("colabfold HTTP 429 after 6 attempt(s): Too Many Requests")
    assert _is_colabfold_rate_limit("colabfold MSA failed: HTTP Error 429: Too Many Requests")
    assert not _is_colabfold_rate_limit("af3 failed: GPU compute capability unsupported")


def test_classify_429_is_actionable_not_permanent():
    msg = _classify_af3_failure("colabfold HTTP 429 after 6 attempt(s): Too Many Requests")
    assert "429" in msg
    assert "sim=0" in msg
    assert "msa_path" in msg or "structure_fetch" in msg
