#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ideal-env acceptance: delivery own-head path on sample_rna_pos × PTBP1.

BUILD_SPEC §4 / examples/README.md:
  resolve_rbp(PTBP1) → in_panel
  rhobind_predict(rna_pos, rbps=[PTBP1]) → prob ≈ 0.966

This script does **not** use the LLM. It verifies the scientific call chain
the agent must invoke on the Stage-0 fast path. Run after conda envs +
adequate RAM/GPU are configured.

C5 boundary: this is the ``accept-golden`` / ``own-head`` scientific acceptance
path and lives in ``rbp_eval`` alongside ``accept_llm`` — all ``accept-*``
commands belong here. ``app/dev`` keeps the engineering gates
(``gate`` / ``compliance`` / ``layout`` / ``mvp``).

Exit codes:
  0 — own-head prob within tolerance of golden
  1 — resolve/tool wiring failed
  3 — predictor failed (OOM / missing env) — wiring OK, science blocked
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(*, skip_predict: bool = False) -> int:
    from app.backends.delivery.client import DeliveryToolClient
    from app.backends.delivery.examples import GOLDEN_OWN_HEAD_POS, load_example
    from app.core.chat_ux import memory_blocker_message
    from app.core.verdict_schema import label_from_p_hat

    ex = load_example("pos")
    print("=== own-head accept (delivery, no LLM) ===")
    print("# Authoritative acceptance path. Covers delivery examples/run_example.sh assertions.")
    print(f"RNA file: {ex['rna_path']}")
    print(f"RNA len:  {len(ex['rna'])}")

    warn = memory_blocker_message()
    if warn:
        print(warn, file=sys.stderr)

    device = "cuda"
    try:
        import subprocess

        chk = subprocess.run(
            ["conda", "run", "-n", "rhobind", "python", "-c",
             "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)"],
            capture_output=True,
            timeout=60,
        )
        if chk.returncode != 0:
            device = "cpu"
    except Exception:
        device = "cpu"

    cli = DeliveryToolClient(offline=False, device=device, use_conda=True)
    print(f"device: {device}")
    r = cli.call("resolve_rbp", {"query": ex["query"]})
    print("resolve:", json.dumps({k: r.get(k) for k in (
        "matched", "alias", "uniprot", "in_panel", "head_index", "ok", "error"
    )}, ensure_ascii=False))
    if not r.get("in_panel"):
        print("FAIL: PTBP1 not in_panel — registry/env broken")
        return 1

    if skip_predict:
        print("PASS (lightweight): resolve_rbp in_panel OK; rhobind_predict skipped (--skip-predict)")
        verdict = {
            "label": "Strong",
            "p_hat": None,
            "confidence": "low",
            "explanation": (
                f"Lightweight own-head wiring check for {ex['query']} "
                f"(UniProt {ex['uniprot']}, cohort {ex['cohort']}, "
                f"head_index={r.get('head_index')}); predict skipped."
            ),
            "supporting_rbps": [
                {
                    "rbp_id": ex["uniprot"],
                    "alias": ex["query"],
                    "prob": None,
                    "similarity_score": 1.0,
                }
            ],
            "path": "own_head_light",
        }
        print(json.dumps(verdict, indent=2, ensure_ascii=False))
        return 0

    pred = cli.call(
        "rhobind_predict",
        {
            "rna": ex["rna"],
            "rbps": [ex["query"]],
            "cohort": ex["cohort"],
            "device": device,
            "aggregate": "max",
            "timeout_s": 300,
        },
    )
    if not pred.get("ok") or pred.get("error"):
        print("PREDICT_BLOCKED:", pred.get("error") or pred)
        print(
            "Wiring OK (resolve in_panel). "
            "Configure rhobind conda + raise memory/GPU, then re-run."
        )
        return 3

    preds = pred.get("predictions") or []
    if not preds or preds[0].get("prob") is None:
        print("FAIL: empty predictions", pred)
        return 3

    p = float(preds[0]["prob"])
    label = label_from_p_hat(p)
    golden = GOLDEN_OWN_HEAD_POS["expected_prob_approx"]
    tol = GOLDEN_OWN_HEAD_POS["tolerance"]
    print(f"own-head prob={p} label={label} (golden≈{golden} ±{tol})")
    verdict = {
        "label": label,
        "p_hat": p,
        "confidence": "high" if abs(p - golden) <= tol else "medium",
        "explanation": (
            f"Own-head / in-catalogue path for {ex['query']} "
            f"(UniProt {ex['uniprot']}, cohort {ex['cohort']}, "
            f"head_index={r.get('head_index')})."
        ),
        "supporting_rbps": [
            {
                "rbp_id": ex["uniprot"],
                "alias": ex["query"],
                "prob": p,
                "similarity_score": 1.0,
            }
        ],
        "path": "own_head",
    }
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    if abs(p - golden) > tol:
        print(f"FAIL: prob outside golden tolerance ({golden}±{tol})")
        return 3
    print("PASS: own-head matches delivery golden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
