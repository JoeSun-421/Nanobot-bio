# config/

YAML defaults and evolved knobs for retrieval / fusion / runtime behaviour.

[English] · [中文](README.zh.md)

## Features



## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
# Checkout folder is often Nanobot-bio (GitHub); lowercase nanobot-bio also OK.
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"
source scripts/nbio.sh
```

- Product default hyperparameters (`schema_version`, axes, fusion weights, abstain / label thresholds, integrate / predict / structure / llm blocks)
- Optional promoted evolved overlay and gitignored candidate files
- Constrained by `tests/test_proposal_compliance.py` against the proposal matrix

## Implementation

| File | Role | VCS |
|------|------|-----|
| `defaults.yaml` | **Primary defaults**: `backend`, `cohort`, `top_k`/`n_cand`, `axes.*`, `fusion_weights.*`, `tau_drop`, `models:`, … | Tracked |
| `evolved.yaml` | Promoted evolved config (when present) | May be tracked |
| `evolved.candidate.yaml` | Evolve candidate before promote | **gitignored** |
| `evolved.candidate.yaml.example` | Candidate example | Tracked |

Runtime load path: `app.core.runtime_config` (deep-merge `evolved.yaml` when enabled). Writers: `rbp_eval.evolve.*` (`promote.py`, …). Skill / CLI must not silently replace Table defaults.

Example fields currently in `defaults.yaml`:

- `axes.use_af3` / `rna_blastn` / `structure` …
- `fusion_weights.rna_peak_homology` default `0` until peaks ablation promotes
- `tau_drop: 0.30`, `n_cand: 5`, `integrate.max_vote_donors: 2`

## How to use

Edit defaults only with eval evidence + test updates ([`AGENTS.md`](../AGENTS.md)):

```bash
# After evolve produces a candidate:
nanobot-bio promote-evolved # gated; or python -m rbp_eval.evolve.promote
pytest tests/test_proposal_compliance.py
```

Do not put secret-bearing `*.local.json` here (gitignore already blocks some patterns).

## Design rationale

- Keep a single, reviewable YAML SoT for product knobs instead of scattering magic numbers in skill text.
- Candidate files stay local/ignored so experimental promote artifacts are not force-committed.
- Honesty for unavailable axes is enforced together with `app/core/capability_matrix.py`, not by inventing fusion weights.

## See also

[`../README.md`](../README.md) · [`../rbp_eval/README.md`](../rbp_eval/README.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) §5
