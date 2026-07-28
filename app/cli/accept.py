# -*- coding: utf-8 -*-
"""Acceptance commands: own-head, accept-golden/llm, gap-closure."""

from __future__ import annotations

import argparse


def cmd_accept_golden(args: argparse.Namespace) -> int:
    """Alias of own-head (Delivery accept-golden)."""
    return cmd_own_head(args)


def cmd_accept_llm(args: argparse.Namespace) -> int:
    """LLM touchpoint acceptance (nanobot_llm + abstain-before-predict evidence)."""
    from rbp_eval.accept.accept_llm import run_accept_llm

    report = run_accept_llm(
        run_catalogue=not bool(getattr(args, "skip_catalogue", False)),
        run_unseen=not bool(getattr(args, "skip_unseen", False)),
        strict=not bool(getattr(args, "no_strict", False)),
    )
    print(f"accept-llm ok={report.get('ok')} path={report.get('path')}")
    tp = report.get("touchpoints") or {}
    print(
        "touchpoints:",
        {k: tp.get(k) for k in (
            "stage1_function_or_donor",
            "stage3_explanation",
            "abstain_before_predict",
            "parallel_or_dual_seq",
        )}
    )
    return 0 if report.get("ok") else 1


def cmd_gap_closure(args: argparse.Namespace) -> int:
    """Lightweight Proposal/Delivery gap-closure evidence pack."""
    from rbp_eval.accept.gap_closure import main as gap_main

    argv: list[str] = []
    if getattr(args, "no_live", False):
        argv.append("--no-live")
    if getattr(args, "out_dir", None):
        argv.extend(["--out-dir", str(args.out_dir)])
    return int(gap_main(argv))


def cmd_own_head(args: argparse.Namespace) -> int:
    """Ideal-env scientific accept: delivery own-head on sample_rna_pos (no LLM)."""
    from rbp_eval.accept.own_head import main as own_main

    skip_predict = bool(getattr(args, "skip_predict", False))
    return int(own_main(skip_predict=skip_predict))

