#!/usr/bin/env bash
# Smoke: fixture traces → self-evolution → candidate → promote dry-run gates.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || true

python - <<'PY'
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from rbp_eval.evolve import orchestrator as orch
from rbp_eval.evolve import promote as promo
from rbp_eval.evolve.orchestrator import run_self_evolution
from rbp_eval.evolve.promote import promote_evolved_config
from rbp_eval.evolve.run_eval import run_eval, run_modality_ablation

tmp = Path(tempfile.mkdtemp(prefix="smoke_evolve_"))
report_path = tmp / "evolve_report.json"
cand = tmp / "evolved.candidate.yaml"
live = tmp / "evolved.yaml"
orch.EVOLVED_REPORT = report_path
orch.CANDIDATE_CONFIG = cand
promo.EVOLVED_REPORT = report_path
promo.CANDIDATE_CONFIG = cand
promo.EVOLVED_CONFIG = live

held = {
    "PTBP1": [
        [
            {
                "alias": "U2AF2",
                "score": 0.9,
                "metric": "domain_overlap",
                "sim_by_modality": {"domain_overlap": 0.9, "esmc_cosine": 0.8},
            },
            {
                "alias": "ELAVL1",
                "score": 0.7,
                "metric": "domain_overlap",
                "sim_by_modality": {"domain_overlap": 0.7, "esmc_cosine": 0.6},
            },
        ]
    ]
}
abl = run_modality_ablation(held, top_k=3)
assert abl["schema"] == "modality_ablation/v1"
assert abl["ablations"], "expected ablation rows"

# Scored (non-synthetic) results so candidate may be written when retune ok
results = [
    {
        "query": {"alias": "PTBP1"},
        "mode": "transfer",
        "donors": held["PTBP1"][0],
        "retrieval": {"domain": {"ok": True, "n": 2}},
        "evidence_table": [
            {
                "alias": "U2AF2",
                "score": 0.9,
                "sim_by_modality": {"domain_overlap": 0.9, "esmc_cosine": 0.8},
            }
        ],
        "predictions": [{"alias": "U2AF2", "prob": 0.72, "confidence": 0.4}],
        "verdict": {
            "label": "Likely",
            "p_hat": 0.72,
            "confidence": "medium",
            "explanation": "smoke",
            "supporting_rbps": [
                {"alias": "U2AF2", "prob": 0.72, "similarity_score": 0.9}
            ],
        },
    }
]
report = run_self_evolution(
    results,
    held_to_hit_lists=held,
    scored_labels=[{"p_hat": 0.72, "y": 1}],
    write_config=True,
    require_loo_report=False,
    allow_retrieval_only=False,
)
assert report_path.is_file(), "evolve report missing"
print("evolve_report:", report_path)
print("candidate:", report.evolved_config_path)

# RNA gate: force-zero weights then promote without reports
if cand.is_file():
    promote_evolved_config(
        candidate=cand, live=live, require_reports=False, seed=False
    )
    assert live.is_file()
    print("promoted:", live)
else:
    print("candidate not written (retune skipped) — still ok for smoke harness")

re = run_eval(held_to_hit_lists=held, top_k=3, out_dir=tmp, write=True)
assert re.get("modality_ablation")
print("run_eval ok:", re.get("status"))
print("SMOKE_EVOLVE_LOOP_OK")
PY
