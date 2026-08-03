# -*- coding: utf-8 -*-
"""Argparse surface — command names unchanged for collaborators/CI."""

from __future__ import annotations

import argparse

from app.cli.accept import (
    cmd_accept_golden,
    cmd_accept_llm,
    cmd_batch_prompts,
    cmd_gap_closure,
    cmd_own_head,
)
from app.cli.eval_cmds import (
    cmd_eval_plan,
    cmd_evolve,
    cmd_evolve_eval,
    cmd_expand_loo_matrix,
    cmd_heavy_loo,
    cmd_loo_matrix_ab,
    cmd_promote_evolved,
    cmd_run_eval,
)
from app.cli.maint import (
    cmd_compliance,
    cmd_gate,
    cmd_layout,
    cmd_mvp,
)
from app.cli.user import (
    cmd_agent,
    cmd_chat,
    cmd_doctor,
    cmd_nanobot_smoke,
    cmd_onboard,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rbp-agent",
        description=(
            "RNA–RBP agent (nanobot + delivery tools). "
            "Groups: user (agent/chat/…) · accept · eval · maint."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # --- user ---
    d = sub.add_parser("doctor", help="Capability table: paths, science envs, LLM")
    d.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed path/store dumps in addition to the capability table",
    )
    d.set_defaults(func=cmd_doctor)

    o = sub.add_parser("onboard", help="Configure LLM provider + API key + model")
    o.add_argument("--provider", default=None, help="Non-interactive: registry name")
    o.add_argument("--model", default=None, help="Model id (required with --provider)")
    o.add_argument("--key", default=None, help="API key")
    o.add_argument("--api-base", default=None, help="OpenAI-compatible base URL")
    o.add_argument("--show", action="store_true", help="Print active provider/model")
    o.add_argument("--list-models", action="store_true", help="List curated models and exit")
    o.set_defaults(func=cmd_onboard)

    n = sub.add_parser("nanobot-smoke", help="Register tools + start Nanobot")
    n.set_defaults(func=cmd_nanobot_smoke)

    a = sub.add_parser("agent", help="PRIMARY: one-shot Nanobot.run")
    a.add_argument("--message", default=None)
    a.add_argument("--example", choices=["pos", "neg"], default=None,
                   help="Delivery golden RNA × PTBP1 own-head path")
    a.add_argument("--query", default=None)
    a.add_argument("--uniprot", default=None)
    a.add_argument("--sequence-fasta", default=None)
    a.add_argument("--rna-file", default=None)
    a.add_argument(
        "--fasta",
        default=None,
        help="Allowlisted FASTA path: batch own-head score (no LLM); needs --query RBP",
    )
    a.add_argument(
        "--max-seqs",
        type=int,
        default=None,
        help="Optional subsample for --fasta",
    )
    a.add_argument(
        "--doc",
        default=None,
        help="Print allowlisted markdown slice (read_project_doc; no LLM)",
    )
    a.add_argument("--force-transfer", action="store_true")
    a.add_argument("--strict", action="store_true", help="Exit 2 unless mode=nanobot_llm")
    a.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    a.add_argument("--session-key", default="rbp:cli")
    a.add_argument("--out", default=None)
    a.add_argument("--fallback", action="store_true", help=argparse.SUPPRESS)
    a.add_argument("--offline", action="store_true", help=argparse.SUPPRESS)
    a.add_argument("-v", "--verbose", action="store_true",
                   help="Also show framework DEBUG logs")
    a.set_defaults(func=cmd_agent)

    chat = sub.add_parser("chat", help="Multi-turn agent (thinking/tools + JSON verdict)")
    chat.add_argument("--session-key", default=None)
    chat.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    chat.add_argument("-v", "--verbose", action="store_true")
    chat.set_defaults(func=cmd_chat)

    # --- accept ---
    oh = sub.add_parser("own-head", help="Ideal-env: delivery own-head (no LLM)")
    oh.add_argument("--skip-predict", action="store_true",
                    help="Skip rhobind_predict (no GPU)")
    oh.set_defaults(func=cmd_own_head)

    ag = sub.add_parser("accept-golden", help="Delivery accept-golden (alias of own-head)")
    ag.add_argument("--skip-predict", action="store_true")
    ag.set_defaults(func=cmd_accept_golden)

    al = sub.add_parser("accept-llm", help="LLM touchpoints accept")
    al.add_argument("--skip-catalogue", action="store_true")
    al.add_argument("--skip-unseen", action="store_true")
    al.add_argument("--no-strict", action="store_true")
    al.set_defaults(func=cmd_accept_llm)

    bp = sub.add_parser(
        "batch-prompts",
        help=(
            "Outer-loop multi-verdict: one agent turn per markdown case "
            "(e.g. docs/eval/UNSEEN_RBP_TEST_PROMPTS_20.md)"
        ),
    )
    bp.add_argument(
        "--prompts",
        default=str(
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "docs"
            / "eval"
            / "UNSEEN_RBP_TEST_PROMPTS_20.md"
        ),
        help="Markdown with ## Prompt NN — Case NN — GENE + ```text``` blocks",
    )
    bp.add_argument("--out-dir", default=None, help="Directory for jsonl + summary json")
    bp.add_argument(
        "--case",
        action="append",
        default=None,
        help="Filter by case id / prompt id / gene (repeatable)",
    )
    bp.add_argument("--limit", type=int, default=None, help="Run at most N cases")
    bp.add_argument(
        "--offset",
        type=int,
        default=None,
        help="Skip the first N cases before applying --limit",
    )
    bp.add_argument(
        "--last",
        type=int,
        default=None,
        help="Run only the last N cases (after --case filter)",
    )
    bp.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    bp.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse/list cases only (no LLM)",
    )
    bp.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Abort after the first failed case",
    )
    bp.add_argument(
        "--stream",
        action="store_true",
        help="Force chat-like per-case tool streaming (default: on when stderr is a TTY)",
    )
    bp.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-case banners / tool streaming",
    )
    bp.set_defaults(func=cmd_batch_prompts)

    gc = sub.add_parser("gap-closure", help="Gap-closure evidence report")
    gc.add_argument("--no-live", action="store_true")
    gc.add_argument("--out-dir", default=None)
    gc.set_defaults(func=cmd_gap_closure)

    # --- eval ---
    evo = sub.add_parser("evolve", help="Offline self-evolution (knobs; toolkit proposals need humans)")
    evo.add_argument("--top-k", type=int, default=5)
    from app.core.paths import DEFAULT_EVAL_TRACE, DEFAULT_VAL_BATCH
    evo.add_argument("--trace", default=str(DEFAULT_EVAL_TRACE))
    evo.add_argument("--out", default=str(DEFAULT_VAL_BATCH))
    evo.add_argument("--with-esm", action="store_true")
    evo.add_argument("--with-labels", default=None)
    evo.add_argument(
        "--allow-missing-loo",
        action="store_true",
        help="Dev only: skip LOO/heavy-LOO report requirement",
    )
    evo.add_argument(
        "--allow-retrieval-only",
        action="store_true",
        help="Dev only: allow writing candidate from retrieval-only synthetic batch",
    )
    evo.add_argument(
        "--transfer-dir",
        default=None,
        help="Prefer agent-side LOO matrix dir (sets RBP_LOO_TRANSFER_DIR for this run)",
    )
    evo.set_defaults(func=cmd_evolve)

    re = sub.add_parser("run-eval", help="LOO ceiling + modality ablation harness")
    re.add_argument("--hits-json", default=None)
    re.add_argument("--top-k", type=int, default=5)
    re.add_argument("--out-dir", default=None)
    re.set_defaults(func=cmd_run_eval)

    ee = sub.add_parser("evolve-eval", help="Light nested-split evolve eval")
    ee.add_argument("--seed", type=int, default=42)
    ee.add_argument("--n-test", type=int, default=5)
    ee.add_argument("--top-k", type=int, default=5)
    ee.add_argument("--with-esm", action="store_true")
    ee.add_argument("--no-live", action="store_true")
    ee.add_argument("--tier-a-ok", choices=["true", "false"], default=None)
    from app.core.paths import report_path as _report_path
    ee.add_argument("--out", default=str(_report_path("evolve_eval_report.json")))
    ee.add_argument("--md", default=str(_report_path("evolve_eval_report.md")))
    ee.set_defaults(func=cmd_evolve_eval)

    pe = sub.add_parser("promote-evolved", help="Promote evolved.candidate → evolved.yaml")
    pe.add_argument("--force", action="store_true")
    pe.add_argument("--seed", action="store_true")
    pe.set_defaults(func=cmd_promote_evolved)

    ep = sub.add_parser("eval-plan", help="Evaluation plan report")
    ep.add_argument("--with-seq", action="store_true")
    ep.add_argument("--labels", default=None)
    ep.add_argument("--out", default=str(_report_path("evaluation_plan_report.json")))
    ep.set_defaults(func=cmd_eval_plan)

    hl = sub.add_parser(
        "heavy-loo",
        help="Heavy hide-own-head LOO (real predict): recovered-AUPRC + instance AUROC/AUPRC/ECE",
    )
    hl.add_argument("--rbp", default=None, help="Single held-out RBP alias (default PTBP1)")
    hl.add_argument("--medoids", action="store_true", help="Run the default medoid validation set")
    hl.add_argument("--cohort", default="K562", help="K562|HepG2")
    hl.add_argument("--max-seqs", type=int, default=64, help="Subsample per held RBP (pilot)")
    hl.add_argument("--top-k", type=int, default=5, help="Foreign donor heads per held RBP")
    hl.add_argument("--out", default=None, help="Output JSON path (md written alongside)")
    hl.set_defaults(func=cmd_heavy_loo)

    elm = sub.add_parser(
        "expand-loo-matrix",
        help="Expand LOO transfer matrix into rbp_eval/data/transfer (never edits delivery)",
    )
    elm.add_argument("--out-dir", default=None)
    elm.add_argument("--cohort", default="K562")
    elm.add_argument("--max-seqs", type=int, default=64)
    elm.add_argument("--device", default=None)
    elm.add_argument("--rbp-chunk", type=int, default=40)
    elm.add_argument("--seed", type=int, default=42)
    elm.add_argument("--no-resume", action="store_true")
    elm.add_argument("--held", action="append", default=None, help="Limit to alias (repeatable)")
    elm.add_argument(
        "--skip-existing-helds",
        action="store_true",
        help="Skip helds already in loo_summary.csv (only score new test.fasta)",
    )
    elm.add_argument(
        "--list-helds",
        action="store_true",
        help="Dry-run: show catalogue ∩ test.fasta planned helds and exit",
    )
    elm.set_defaults(func=cmd_expand_loo_matrix)

    lab = sub.add_parser(
        "loo-matrix-ab",
        help="A/B delivery vs expanded LOO matrix (policy AUPRC / prior_missing / retune)",
    )
    lab.add_argument("--expanded-dir", default=None)
    lab.add_argument("--top-k", type=int, default=5)
    lab.add_argument("--no-retune", action="store_true")
    lab.add_argument("--out", default=None)
    lab.add_argument("--held", action="append", default=None)
    lab.set_defaults(func=cmd_loo_matrix_ab)

    # --- maint ---
    g = sub.add_parser("gate", help="Engineering gate: ruff + pytest + layout (+ light eval)")
    g.add_argument("--skip-eval", action="store_true")
    g.add_argument("--no-cov", action="store_true")
    g.set_defaults(func=cmd_gate)

    m = sub.add_parser("mvp", help="MVP acceptance (Nanobot.run required)")
    m.set_defaults(func=cmd_mvp)

    c = sub.add_parser("compliance", help="Delivery path self-check")
    c.set_defaults(func=cmd_compliance)

    lay = sub.add_parser("layout", help="Assert nanobot SoT layout + Runtime import")
    lay.set_defaults(func=cmd_layout)

    return p
