# -*- coding: utf-8 -*-
"""Real-science smoke gate: asserts the delivery science actually computes.

Unlike the mostly-mock unit suite, this runs the REAL RhoBind / ESM-C / Foldseek
tools through the bridge and checks concrete numbers. It auto-skips when the
scientific stack (conda envs + CUDA) is not present, so CI without a GPU stays
green; on a properly provisioned box it is the ground-truth regression guard.

Golden (delivery examples/README.md): PTBP1 + sample_rna_pos → own-head
prob ≈ 0.966 (Strong).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.science


def _science_available() -> tuple[bool, str]:
    try:
        from app.backends.delivery.env import apply_delivery_env, conda_env_python

        apply_delivery_env()
        if conda_env_python("rhobind") is None:
            return False, "no rhobind conda env"
        if conda_env_python("protein_embed") is None:
            return False, "no protein_embed conda env"
        try:
            import torch  # type: ignore

            if not torch.cuda.is_available():
                return False, "CUDA not available"
        except Exception:
            # RhoBind runs in its own conda env; .venv torch may lack CUDA. Allow
            # opting in explicitly so the gate still runs where the science env is fine.
            if os.environ.get("RUN_SCIENCE_GATE") not in ("1", "true", "yes"):
                return False, "no torch/CUDA in agent venv (set RUN_SCIENCE_GATE=1 to force)"
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


_OK, _WHY = _science_available()
skip_no_science = pytest.mark.skipif(not _OK, reason=f"science stack unavailable: {_WHY}")


def _client():
    from app.backends.delivery.client import DeliveryToolClient

    return DeliveryToolClient(offline=True, device="cuda", use_conda=True)


@skip_no_science
def test_ptbp1_own_head_golden_prob():
    from app.backends.delivery.examples import GOLDEN_OWN_HEAD_POS, load_example

    ex = load_example("pos")
    out = _client().call(
        "rhobind_predict",
        {"rna": ex["rna"], "rbps": ["PTBP1"], "cohort": "K562", "device": "cuda"},
    )
    assert out.get("ok") is not False, out.get("error")
    pred = (out.get("predictions") or [{}])[0]
    prob = pred.get("prob")
    assert prob is not None
    expected = GOLDEN_OWN_HEAD_POS["expected_prob_approx"]
    tol = GOLDEN_OWN_HEAD_POS["tolerance"]
    assert abs(float(prob) - expected) <= tol, f"prob={prob} expected≈{expected}±{tol}"
    assert "confidence" not in pred


@skip_no_science
def test_esm_similarity_returns_hits():
    from nanobot.agent.tools.rbp.common import load_catalogue_sequence

    seq = load_catalogue_sequence("PTBP1")
    assert seq, "no catalogue sequence for PTBP1"
    out = _client().call(
        "esm_similarity",
        {"sequence": seq, "encoder": "esmc", "top_k": 3, "device": "cuda",
         "uniprot": "P26599"},
    )
    assert out.get("ok") is not False, out.get("error")
    hits = out.get("hits") or []
    assert hits, "esm_similarity returned no hits"
    assert hits[0].get("score") is not None


@skip_no_science
def test_struct_similarity_foldseek_returns_hits():
    afdb = os.environ.get("AFDB_DIR") or ""
    pdb = os.path.join(afdb, "PTBP1_P26599.pdb")
    if not os.path.exists(pdb):
        pytest.skip(f"AFDB structure missing: {pdb}")
    out = _client().call("struct_similarity_foldseek", {"pdb_path": pdb, "top_k": 5})
    assert out.get("ok") is not False, out.get("error")
    hits = out.get("hits") or []
    assert hits, "foldseek returned no hits"
    aliases = {h.get("alias") for h in hits}
    assert "PTBP1" in aliases  # self-hit is expected in the reference DB
