# -*- coding: utf-8 -*-
"""Maintainer gates: gate, mvp, layout, compliance."""

from __future__ import annotations

import argparse


def cmd_compliance(args: argparse.Namespace) -> int:
    from app.dev.compliance import main as compliance_main

    return int(compliance_main())


def cmd_gate(args: argparse.Namespace) -> int:
    from app.dev.gate import run_gate

    return int(
        run_gate(
            skip_eval=bool(getattr(args, "skip_eval", False)),
            with_cov=not bool(getattr(args, "no_cov", False)),
        )
    )


def cmd_layout(args: argparse.Namespace) -> int:
    from app.dev.layout import main as layout_main

    try:
        layout_main()
    except SystemExit as e:
        return int(e.code or 0)
    return 0


def cmd_mvp(args: argparse.Namespace) -> int:
    from app.dev.mvp import main as mvp_main

    return int(mvp_main())

