# rbp_eval/rna/

RNA-axis fusion gate helpers (delivery-aligned HOLD).

[English] · [中文](README.zh.md)

## Purpose

Documents and emits the RNA fusion gate used by offline eval / promote. Delivery has **no RNA-FM axis** in the registry; the product RNA axis is `rna_blastn` / peaks homology, and fusion `rna_*` weights stay at 0 until peaks are ready. `run_rna_fm_gate` always returns `decision: HOLD` with `allow_fusion: False` and `fusion_weight: 0.0`, then calls `app.core.fusion_rna_policy.write_gate` (currently a no-op — readiness is runtime-only).

## Layout

| Module | Role |
|--------|------|
| `rna_fm_gate.py` | `run_rna_fm_gate`, CLI `python -m rbp_eval.rna.rna_fm_gate` |
| `__init__.py` | Package marker |

## Entry points

```bash
python -m rbp_eval.rna.rna_fm_gate
python -m rbp_eval.rna.rna_fm_gate --weight 0.30
```

```python
from rbp_eval.rna.rna_fm_gate import run_rna_fm_gate
from app.core.fusion_rna_policy import apply_fusion_rna_policy, DEFAULT_REAL_WEIGHT
```

## Code examples

```bash
python -m rbp_eval.rna.rna_fm_gate
# prints JSON: schema rna_fm_eval_gate.v1, decision HOLD, fusion_weight 0.0
```

```python
from rbp_eval.rna.rna_fm_gate import run_rna_fm_gate
from app.core.fusion_rna_policy import apply_fusion_rna_policy

gate = run_rna_fm_gate()
assert gate["decision"] == "HOLD"
assert gate["allow_fusion"] is False
assert float(gate["fusion_weight"]) == 0.0

# Runtime fusion weights: zero rna_peak_homology when peaks DB not ready
w = apply_fusion_rna_policy({"esmc_cosine": 0.4, "rna_peak_homology": 0.3})
print(w.get("rna_peak_homology"), "rna_embed" in w)  # typically 0.0, False
```

## Dependencies / env

- No GPU required for the gate CLI.
- Live fusion weight zeroing consults `app.core.capability_matrix.rna_blastn_status`.
- Peaks DB / `rna_blastn` readiness is separate from this historical RNA-FM gate name.

## See also

[`../README.md`](../README.md) · [`../scoring/README.md`](../scoring/README.md) · [`../../app/core/README.md`](../../app/core/README.md) · [`../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../docs/product/BINDING_PREDICTION_FLOW.zh.md)
