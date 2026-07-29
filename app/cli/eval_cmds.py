# -*- coding: utf-8 -*-
"""Offline eval / self-evolution CLI glue (logic lives in rbp_eval)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.cli.common import ROOT

def cmd_eval_plan(args: argparse.Namespace) -> int:
    """Evaluation plan: held-out LOO + ablations + metrics report."""
    from rbp_eval.plans.evaluation_plan import main as eval_main

    argv: list[str] = []
    if getattr(args, "with_seq", False):
        argv.append("--with-seq")
    if getattr(args, "labels", None):
        argv.extend(["--labels", str(args.labels)])
    if getattr(args, "out", None):
        argv.extend(["--out", str(args.out)])
    return int(eval_main(argv))


def cmd_evolve(args: argparse.Namespace) -> int:
    """Offline self-evolution: LOO val batch → attribution / retune / cache / report."""
    from app.core.paths import (
        DEFAULT_EVAL_TRACE,
        DEFAULT_EVOLVE_REPORT,
        DEFAULT_VAL_BATCH,
        TRACES,
        ensure_artifact_dirs,
    )
    from rbp_eval.evolve.orchestrator import run_self_evolution, summarize_verdicts
    from rbp_eval.evolve.runner import load_traces, run_loo_val_batch

    ensure_artifact_dirs()
    top_k = int(getattr(args, "top_k", 5) or 5)
    trace_path = Path(getattr(args, "trace", None) or DEFAULT_EVAL_TRACE)
    out_json = Path(getattr(args, "out", None) or DEFAULT_VAL_BATCH)
    if not out_json.is_absolute():
        out_json = ROOT / out_json

    results, held_hits = run_loo_val_batch(
        top_k=top_k,
        trace_path=trace_path,
        with_esm=bool(getattr(args, "with_esm", False)),
    )
    summary = summarize_verdicts(results)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(
            {"summary": summary, "n": len(results), "results": results},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print("val_batch:", out_json)
    print("summary:", json.dumps(summary, ensure_ascii=False))
    print(
        "note: retrieval-only batch cannot promote candidate; "
        "use heavy-loo / --with-labels for real scores"
    )

    scored_labels: list[dict] | None = None
    labels_path = getattr(args, "with_labels", None)
    if labels_path:
        lp = Path(labels_path)
        if not lp.is_absolute():
            lp = ROOT / lp
        raw = json.loads(lp.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            scored_labels = raw
        elif isinstance(raw, dict) and isinstance(raw.get("scored_labels"), list):
            scored_labels = raw["scored_labels"]
        else:
            print("WARN: --with-labels must be a JSON list of {p_hat,y}", file=sys.stderr)

    traces = load_traces(trace_path)
    # Merge other agent JSONL under artifacts/traces/ (exclude the val trace itself)
    try:
        for p in sorted(TRACES.glob("*.jsonl")):
            if p.resolve() == Path(trace_path).expanduser().resolve():
                continue
            traces.extend(load_traces(p))
    except OSError:
        pass

    report = run_self_evolution(
        results,
        held_to_hit_lists=held_hits,
        scored_labels=scored_labels,
        traces=traces,
        top_k=top_k,
        write_config=True,
        require_loo_report=not bool(getattr(args, "allow_missing_loo", False)),
        allow_retrieval_only=bool(getattr(args, "allow_retrieval_only", False)),
    )
    print("self_evolution_report:", DEFAULT_EVOLVE_REPORT)
    print("candidate_config:", report.evolved_config_path)
    print(
        "Toolkit expansion proposals (human review required) — "
        "not an auto-installed toolkit."
    )
    print("Promote after gate: rbp-agent promote-evolved")
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False)[:3000])
    return 0


def cmd_run_eval(args: argparse.Namespace) -> int:
    """DESIGN run_eval harness: LOO ceiling + modality ablation."""
    from rbp_eval.evolve.run_eval import run_eval

    held = None
    hits = getattr(args, "hits_json", None)
    if hits:
        p = Path(hits)
        if not p.is_absolute():
            p = ROOT / p
        raw = json.loads(p.read_text(encoding="utf-8"))
        held = raw.get("held_to_hit_lists", raw) if isinstance(raw, dict) else None
    out_dir = getattr(args, "out_dir", None)
    report = run_eval(
        held_to_hit_lists=held,
        top_k=int(getattr(args, "top_k", 5) or 5),
        out_dir=Path(out_dir) if out_dir else None,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False)[:4000])
    return 0 if report.get("ok") else 1


def cmd_evolve_eval(args: argparse.Namespace) -> int:
    """Light nested-split eval: retune on train half, score defaults vs retuned on test."""
    from rbp_eval.evolve.evolve_eval import run_evolve_eval

    tier_a = getattr(args, "tier_a_ok", None)
    if tier_a == "true":
        tier_a_ok: bool | None = True
    elif tier_a == "false":
        tier_a_ok = False
    else:
        # Infer from latest gate_report if present
        tier_a_ok = None
        try:
            from app.core.paths import REPORTS_JSON, find_report

            gp = find_report("gate_report.json") or (REPORTS_JSON / "gate_report.json")
            if gp.is_file():
                tier_a_ok = bool(json.loads(gp.read_text(encoding="utf-8")).get("ok"))
        except Exception:
            tier_a_ok = None

    out = Path(getattr(args, "out", None) or "")
    if not out.parts:
        from app.core.paths import report_path

        out = report_path("evolve_eval_report.json")
    if not out.is_absolute():
        out = ROOT / out
    from app.core.paths import paired_md_path

    md = Path(getattr(args, "md", None) or paired_md_path(out))
    if not md.is_absolute():
        md = ROOT / md

    report = run_evolve_eval(
        seed=int(getattr(args, "seed", 42) or 42),
        n_test=int(getattr(args, "n_test", 5) or 5),
        top_k=int(getattr(args, "top_k", 5) or 5),
        with_esm=bool(getattr(args, "with_esm", False)),
        include_live=not bool(getattr(args, "no_live", False)),
        tier_a_ok=tier_a_ok,
        out_json=out,
        out_md=md,
        write=True,
    )
    print("evolve_eval:", report.get("paths", {}).get("json", out))
    print("delta_auprc:", report.get("delta_auprc"))
    print("promote:", json.dumps(report.get("promote"), ensure_ascii=False))
    return 0


def cmd_heavy_loo(args: argparse.Namespace) -> int:
    """Heavy hide-own-head LOO: recovered-AUPRC + instance AUROC/AUPRC/ECE (real predict)."""
    from rbp_eval.loo.heavy_loo import MEDOIDS, run_heavy_loo

    if getattr(args, "medoids", False):
        rbps = list(MEDOIDS)
    elif getattr(args, "rbp", None):
        rbps = [str(args.rbp).strip()]
    else:
        rbps = ["PTBP1"]

    out = getattr(args, "out", None)
    report = run_heavy_loo(
        rbps=rbps,
        cohort=str(getattr(args, "cohort", "K562") or "K562"),
        top_k=int(getattr(args, "top_k", 5) or 5),
        max_seqs=int(getattr(args, "max_seqs", 64) or 64),
        out=Path(out) if out else None,
    )
    paths = report.get("paths", {})
    print("heavy_loo:", paths.get("json"))
    print("md:", paths.get("md"))
    print("summary:", json.dumps(report.get("summary"), ensure_ascii=False))
    return 0 if report.get("ok") else 1


def cmd_promote_evolved(args: argparse.Namespace) -> int:
    """Promote config/evolved.candidate.yaml → evolved.yaml after light eval asserts."""
    from rbp_eval.evolve.promote import promote_evolved_config

    try:
        path = promote_evolved_config(
            require_reports=not bool(getattr(args, "force", False)),
            seed=bool(getattr(args, "seed", False)),
        )
    except Exception as e:
        print(f"promote-evolved FAIL: {e}", file=sys.stderr)
        return 1
    print(f"promoted → {path}")
    return 0

