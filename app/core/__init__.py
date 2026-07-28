"""Product helpers for the RNA–RBP agent CLI (not the agent loop itself).

Kept:
  - ``paths`` — artifact dirs + legacy symlinks
  - ``onboard`` — LLM provider login
  - ``chat_ux`` — quiet logs + visible agent steps / verdict display
  - ``verdict_schema`` — verdict JSON normalize/validate

Eval-only fusion helpers live under ``rbp_eval``. The fixed ``pipeline``
module was removed — product path is ``app.agent.RBPAgent`` → ``Nanobot.run``
(``app.integrate`` remains a thin re-export).
"""

from __future__ import annotations

__all__ = ["normalize_verdict", "validate_verdict", "extract_verdict_from_content"]


def __getattr__(name: str):
    if name in ("normalize_verdict", "validate_verdict", "extract_verdict_from_content"):
        from . import verdict_schema

        return getattr(verdict_schema, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
