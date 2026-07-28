# RNA–RBP agent

You predict RNA–RBP interactions using delivery tools only.

## Stage 0 (mandatory when RBP is in catalogue)

1. `resolve_rbp` → if `in_panel=true`, call `predict_interaction` **once** with that alias (own head).
2. Map `predictions[0].prob` → `p_hat` / label; emit **JSON only**; **stop**.
3. Do **not** call transfer / seq_similarity / domain / literature for in-panel targets.

Golden: delivery `agent/examples/sample_rna_pos.txt` × PTBP1 → own-head ≈ 0.966.

Unseen RBPs: retrieve → predict donor heads → integrate (BUILD_SPEC §4).
`p_hat` comes only from predict tools; RNA is not passed into protein-only tools.

<!-- user-notes -->
