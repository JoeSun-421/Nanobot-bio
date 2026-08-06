# -*- coding: utf-8 -*-
"""Acceptance commands: own-head, accept-golden/llm, gap-closure."""

from __future__ import annotations

import argparse


def cmd_accept_golden(args: argparse.Namespace) -> int:
    """Alias of own-head (Delivery accept-golden)."""
    return cmd_own_head(args)


def cmd_batch_prompts(args: argparse.Namespace) -> int:
    """Outer-loop: one agent turn per markdown case → many JSON verdicts."""
    from rbp_eval.accept.batch_prompts import run_batch_prompts

    if bool(getattr(args, "quiet", False)):
        stream_flag: bool | None = False
    elif bool(getattr(args, "stream", False)):
        stream_flag = True
    else:
        stream_flag = None  # auto: stream when stderr is a TTY

    report = run_batch_prompts(
        prompts_md=args.prompts,
        out_dir=getattr(args, "out_dir", None),
        cases=getattr(args, "case", None),
        limit=getattr(args, "limit", None),
        offset=getattr(args, "offset", None),
        last=getattr(args, "last", None),
        device=str(getattr(args, "device", "auto") or "auto"),
        dry_run=bool(getattr(args, "dry_run", False)),
        continue_on_error=not bool(getattr(args, "stop_on_error", False)),
        stream=stream_flag,
    )
    print(
        f"batch-prompts ok={report.get('ok')} "
        f"n_ok={report.get('n_ok', report.get('n_cases'))}/"
        f"{report.get('n_cases')} path={report.get('path')}"
    )
    if report.get("jsonl"):
        print(f"jsonl: {report.get('jsonl')}")
    for r in report.get("results") or []:
        status = "ok" if r.get("ok") else "FAIL"
        print(
            f"  [{status}] {r.get('case')} label={r.get('label')} "
            f"p_hat={r.get('p_hat')} mode={r.get('path_mode')}"
            + (f" err={r.get('error')}" if r.get("error") else "")
        )
    if report.get("dry_run"):
        for c in report.get("cases") or []:
            print(f"  - {c}")
    return 0 if report.get("ok") else 1


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

