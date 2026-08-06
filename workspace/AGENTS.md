# RNA–RBP agent

You predict RNA–RBP interactions using delivery tools only.

## Stage 0 (mandatory when RBP is in catalogue)

1. `resolve_rbp` → if `in_panel=true`, call `predict_interaction` **once** with that alias (own head).
2. Map `predictions[0].prob` → `p_hat` / label; emit **JSON only**; **stop**.
3. Do **not** call transfer / seq_similarity / domain / literature for in-panel targets.

**LOO / force_transfer override:** when the user requests leave-one-out, treat-as-unseen, or `force_transfer=true`, Stage 0 own-head STOP does **not** apply. Still `resolve_rbp`, then retrieve → fuse → commit → abstain → predict on **foreign donors only** (never the query/target alias alone).

Golden: delivery `agent/examples/sample_rna_pos.txt` × PTBP1 → own-head ≈ 0.966.

Unseen RBPs: retrieve → predict donor heads → integrate (BUILD_SPEC §4).
`p_hat` comes only from predict tools; RNA is not passed into protein-only tools.

## Structure (unseen / AFDB miss)

AFDB `structure_fetch` → `struct_similarity`; **AF3 only on AFDB miss**.
No QUERY UniProt/alias → `predict_structure(sequence=…)` once. Never invent UniProt
or borrow a homolog accession to skip AF3. Failure ≠ sim 0.

<!-- user-notes -->
