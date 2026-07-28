# -*- coding: utf-8 -*-
"""Golden fixtures from ``rhobind_agent_delivery/agent/examples/``.

Ideal-env smoke (examples/README.md):
  PTBP1 + sample_rna_pos → own-head prob ≈ 0.966 (Strong)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from app.backends.delivery.env import delivery_root

ExampleName = Literal["pos", "neg", "ptbp1_pos", "ptbp1_neg"]

# Delivery golden expectations (ideal scientific env)
GOLDEN_OWN_HEAD_POS = {
    "query": "PTBP1",
    "uniprot": "P26599",
    "cohort": "K562",
    "expected_prob_approx": 0.966,
    "expected_label": "Strong",
    "tolerance": 0.05,
}


def examples_dir() -> Path:
    return delivery_root() / "agent" / "examples"


def load_example(name: ExampleName | str = "pos") -> dict:
    """Load RNA (+ optional protein fasta) for agent / smoke tests."""
    key = str(name).lower().strip()
    if key in ("pos", "ptbp1_pos", "positive"):
        rna_name = "sample_rna_pos.txt"
        kind = "pos"
    elif key in ("neg", "ptbp1_neg", "negative"):
        rna_name = "sample_rna_neg.txt"
        kind = "neg"
    else:
        raise ValueError(f"unknown example {name!r}; use pos|neg")

    ed = examples_dir()
    rna_path = ed / rna_name
    prot_path = ed / "new_rbp_PTBP1.fasta"
    if not rna_path.is_file():
        raise FileNotFoundError(f"missing delivery example RNA: {rna_path}")

    rna = rna_path.read_text(encoding="utf-8").strip().splitlines()
    rna_seq = "".join(ln.strip() for ln in rna if ln.strip() and not ln.startswith(">"))

    protein_seq = None
    if prot_path.is_file():
        lines = prot_path.read_text(encoding="utf-8").splitlines()
        protein_seq = "".join(
            ln.strip() for ln in lines if ln.strip() and not ln.startswith(">")
        )

    return {
        "name": kind,
        "query": "PTBP1",
        "uniprot": "P26599",
        "cohort": "K562",
        "rna": rna_seq,
        "rna_path": str(rna_path),
        "protein_sequence": protein_seq,
        "protein_fasta": str(prot_path) if prot_path.is_file() else None,
        "path": "own_head",
        "golden": dict(GOLDEN_OWN_HEAD_POS) if kind == "pos" else None,
    }


def own_head_prompt(name: ExampleName | str = "pos") -> str:
    """User message that must trigger Stage-0 own-head (in-panel PTBP1)."""
    ex = load_example(name)
    return (
        f"Does this RNA interact with RBP {ex['query']} "
        f"(UniProt {ex['uniprot']}) in cohort {ex['cohort']}?\n"
        f"RNA: {ex['rna']}\n"
        "Use the own-head fast path (resolve_rbp → predict_interaction → JSON). "
        "Do not run transfer/retrieval — PTBP1 is in the catalogue."
    )
