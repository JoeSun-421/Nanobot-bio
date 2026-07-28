# -*- coding: utf-8 -*-
"""RNA–RBP agent CLI (product shell).

Layout::

    app/cli/user.py       # agent, chat, onboard, doctor
    app/cli/accept.py     # accept-golden, accept-llm, gap-closure
    app/cli/eval_cmds.py  # eval-plan, evolve*
    app/cli/maint.py      # gate, layout, mvp, compliance
    app/cli/parser.py     # argparse (command names stable)

Entry: ``nanobot-bio`` / ``rbp-agent`` → ``app.cli:main``.
"""

from __future__ import annotations

from typing import Optional

# Side-effect: env + sys.path bootstrap
from app.cli import common as _common  # noqa: F401
from app.cli.parser import build_parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


__all__ = ["main", "build_parser"]
