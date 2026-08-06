# Stage playbooks (detail)

> Loaded on demand. Hard rules + decision tree stay in SKILL.md.

## 4. Stage 0 — Own-head (in-catalogue)

**Goal:** If the target RBP has its own RhoBind head, use that head **once** and stop.

### Steps

1. Parse the user message → extract **RNA sequence** + **target RBP** (name / UniProt / alias).  
   If RNA is missing → ask **once**, then wait.
2. Call `resolve_rbp` (fallback: `get_known_rbp_list` with a `query`).
3. If `in_panel=true`:
   - Call `predict_interaction(rna, rbp_id=<alias>, cohort)` **exactly once**
   - `p_hat` = `predictions[0].prob`
   - `supporting_rbps` = `[{ "alias", "rbp_id": <uniprot>, "prob": p_hat, "similarity_score": 1.0 }]`
   - `explanation` must state **own-head / in-catalogue** (include `cohort` / `head_index` when tools provide them)
   - Emit final JSON and **STOP**

### Stage 0 forbids

After a successful in-panel resolve, do **not** call:

`seq_similarity`, `rna_blastn`, `domain_architecture`, `struct_*`, `structure_*`, `literature_search`, `fuse_*`, `similarity_weighted_vote`, transfer / abstain tools.

### Near-known Fast Path (own-head on matched catalogue RBP)

1. Call `check_near_known` (exact catalogue AA equality **or** MMseqs identity
   ≥ **0.95**; masked MMseqs can under-report on low-complexity self-hits;
   exact resolve also counts).
2. If `near_match=true` and `donor_alias` has a panel head:
   - Call `predict_interaction(rna, rbp_id=<donor_alias>, cohort)` **exactly once**
     (do **not** set `force_transfer`; runtime promotes this to own-head).
   - `p_hat` = that head's `prob`; `mode=own_head`
   - Explanation must disclose **near_match** (matched donor / identity basis)
   - Emit final JSON and **STOP** — do not run multi-donor retrieve/fuse/vote
3. Else continue Stage 1 (true unseen).

### LOO / leave-one-out (`force_transfer=true`)

When the user asks for 留一法 / LOO / forced transfer on an in-panel or near-match target:

**Stage 0 own-head STOP is overridden** — still resolve (and optionally `check_near_known` to disclose identity), then continue retrieve → fuse → commit → abstain → predict on **foreign donors only**.

1. Set `force_transfer=true` on `commit_proxy_candidates` and `predict_interaction` (runtime also seeds sticky `loo_force_transfer` from user LOO language or prior commit).
2. Commit / predict **foreign donor** aliases only (single foreign donor is valid LOO).
3. Do **not** pass the query/target alias alone; runtime refuses own-head disguised as transfer and never promotes near-match-to-self own-head.
4. `path=multi_head`; `p_hat` from delivery weighted vote (one donor → that donor’s weighted contrib).

---

## 5. Stage 1 — Retrieve (unseen / cache miss)

**Goal:** Find up to **5** donor RBPs that have heads, via multi-view similarity.

**Recommended scientific gates** (not a fixed shortlist — use any registered
retrieve/structure/annotation tools that help): characterize → **parallel**
retrieve → deterministic fuse (authoritative numeric `s_i`) →
**`commit_proxy_candidates`** (selection/text only) → **`confidence_abstain`**
→ Stage 2 predict. Extra delivery tools are welcome; do not invent scores.

### 5.1 Cache first

Call `lookup_proxy_cache`.

| Result | Action |
| --- | --- |
| **Hit** | Skip multi-view retrieve; still run **`confidence_abstain`** on embedding-like hits before Stage 2 |
| **Miss** | Continue §5.2 |

### 5.2 Characterize (before parallel retrieve)

| Tool | Role |
| --- | --- |
| `structure_fetch` | AFDB / cache for the query RBP |
| `get_func_annotation` | Function / GO / **function_category** / optional pdb_metadata (**≤ 1** / UniProt) — Checkpoint 1 input |
| `domain_architecture` | Domains / RBD ranges (feed `predict_structure(regions=…)` later if AF3 needed) |

### 5.3 Parallel multi-view retrieve (`parallel_retrieve=true`)

Run **in parallel intent** (batch tool calls in one turn when possible):

| Tool | Axis | Notes |
| --- | --- | --- |
| `seq_similarity` | `hits_emb` + `hits_seq` | Default dual-axis (ESM-C + MMseqs). Prefer `alias`/`uniprot`. **Never** pass RNA. |
| `rna_blastn` | RNA peaks | Delivery registry tool (proposal Table 1 optional RNA axis) |
| `struct_similarity` | Structure | After `structure_fetch`; US-align refine follows `axes.struct_align_refine` (default on) |
| `domain_architecture` | Domain | Pfam-root Jaccard vs catalogue (required multi-view axis) |
| `structure_consensus` | Structure | When multiple PDBs |
| `literature_search` | Function (PMC ∪ UniProt) | Unseen: **≤ 1** PMC call; craft query or default; merges UniProt peers; Function peers enter fuse; agent sets `fusion_weights` on fuse |

Raw delivery tools (`esm_embed`, `colabfold_msa`, `pymol_util`, `function_category`, …)
are on the default full surface (`RBP_RAW_TOOLS=all`); prefer curated wrappers when
they cover the same science path, but call extras when they add evidence.

### 5.4 Deterministic donor fusion + Checkpoint 1 selection

```text
fuse_similarity_views(
  hits_emb=..., hits_seq=..., hits_struct=..., hits_dom=...,
  exclude_aliases=[target]
)
# donors[*].similarity_score and breakdown are authoritative tool output

commit_proxy_candidates(candidates=[
  {
    "rbp_id": "...",
    "rationale": "selected because multiple tool-derived modalities agree"
  },
  ...
])
```

**Fusion / commit rules**

| Rule | Value |
| --- | --- |
| Required axes before fuse | Runtime blocks fuse until **structure** (`structure_fetch` / `struct_similarity` / AF3) **and** **domain** (`domain_architecture`) have been attempted when those axes are on; honest `structure_axis_unavailable` / `domain_empty` satisfy without inventing sim=0 |
| Include RNA view when available | `rna_blastn` hits (delivery); cite as `rna_blastn` |
| Do not claim RNA-FM | Not in delivery registry; use `rna_blastn` for RNA-side evidence |
| Drop donors | Committed / fused similarity **&lt; 0.30** (`τ_drop`) |
| Cap | **N_cand ≤ 5** |
| Checkpoint 1 | LLM may select fused donor IDs and write text; **must not** supply numeric scores |
| Authoritative `s_i` | Copied unchanged from deterministic fusion into committed rows |

### 5.5 Abstain **before** predict (mandatory on transfer)

```text
confidence_abstain(hits=<hits_emb or fused embedding hits>)
```

- Use **embedding** hits (`hits_emb`) when available.
- If `confident=false` → hedge / low confidence; you may still predict donors but must surface abstain in `caveats`.
- Runtime **blocks** `predict_interaction` on transfer/multi-donor until `commit_proxy_candidates` **and** `confidence_abstain` have been called this turn.

### 5.6 Structure axis order

Mandatory order — **AF3 only on AFDB miss**:

1. `structure_fetch` (AFDB / cache) for the **QUERY**
2. `struct_similarity` (Foldseek; US-align refine when enabled)
3. Optional `structure_consensus`
4. On **AFDB miss** → `predict_structure` (AF3) **≤ 1** with `sequence=` (optional name); pass `regions=[[start,end],…]` from domain/RBD when known
5. After AF3: if a structure path is returned → MAY `struct_similarity` on that path; if AF3 soft-fails → `structure_axis_unavailable` caveat → continue without structure zeros; force **low confidence**
6. AFDB present → skip AF3 (`skipped AF3` is correct). Catalogue coverage ≠ AF3 unused forever — AF3 is for novel / no-AFDB sequences

**AFDB miss includes:** no UniProt/alias for the QUERY; `structure_fetch` error/unavailable; no local/catalogue PDB.

**Do not:** invent UniProt to avoid AF3; pass a catalogue uniprot/alias on the QUERY that would load AFDB and skip AF3; use a nearest homolog's UniProt as the query for `structure_fetch` / `predict_structure` just to skip AF3.

**Sequence-only / anonymous targets** (no accession): skip tools that require UniProt (or call only with clear **donor/homolog** attribution); structure path = AFDB miss → `predict_structure` ≤ 1. Do not thrash `get_func_annotation` / `literature_search` on homolog IDs without labeling them as donor/homolog annotations.

**Critical:** structure failure is **not** similarity `0`. Omit that axis.

### 5.7 Sequence failure fallback

If ESM fails but MMseqs returned `hits_seq`, continue with seq axis only and keep confidence low.

---

## 6. Stage 2 — Predict donors

**Goal:** Score the query RNA under each donor’s RhoBind head (**after** §5.5 abstain).

```text
predict_interaction(rna, rbps=[donor aliases…])   # batch preferred; aggregate=weighted default
```

| Situation | Action |
| --- | --- |
| Single donor fails inside a batch | Skip that donor; do **not** blindly retry the whole batch |
| Collect scores | `prob` from successful rows; empty `feature_attribution` → `feature_attribution_source=unavailable` (saliency is delivery v2) |
| Cross-donor `p_hat` | Default **weighted**: delivery `similarity_weighted_vote` — `Σ(s_i × tprior × quality × prob) / Σ(s_i × tprior × quality)` using committed `s_i` |
| Batch / head fails with OOM or timeout | **No retry** → `p_hat: null`, low confidence |

---

## 7. Stage 3 — Integrate + evidence critic

**Goal:** Ground the verdict; `p_hat` is already tool-sourced from Stage 2 weighted aggregation.

### 7.1 Integrate tools (call when useful)

Skip if required inputs are missing. Order is a recommendation, not a rigid sequence:

| Tool | Purpose |
| --- | --- |
| `transfer_prior_lookup` | LOO / transfer prior for the method |
| `donor_quality_prior` | Down-weight weak donors (context for explanation) |
| `similarity_weighted_vote` | Same formula as Stage-2 `predict_interaction` aggregation; use `contributions` for evidence table |
| *(no tool)* Evidence critic | Checklist below → may force low confidence |

> Note: `confidence_abstain` is **Stage 1.5** (post-commit, pre-predict), not Stage 3.
> `p_hat` remains tool-sourced — never replace with LLM numbers.

### 7.2 `supporting_rbps`

Use committed LLM `similarity_score` (and predict `prob`) for each supporting donor — not the raw deterministic fuse score alone.

### 7.3 Evidence checklist

Mark each row **pass** or **fail**. State the count in `explanation` (e.g. `checklist failures=2`).

| # | Item | Fail when |
| --- | --- | --- |
| 1 | Structure axis | `structure_axis=unavailable`, or AF3/AFDB missing / `structure_trust!=ok` |
| 2 | Domain / RBD | `domain_architecture` empty **and** donors lack shared RBD-type evidence |
| 3 | Kingdom / panel match | Cross-kingdom or clearly non-RBP query vs human CLIP-trained donors |
| 4 | LOO prior | `prior_missing=true` or no transfer prior for target |
| 5 | RNA axis | Query RNA present but RNA view missing/failed → `rna_axis=unavailable` |

**Hard rules**

- If **≥ 2** items fail → force low confidence even when `p_hat` is large.
- High ESM similarity with function/domain mismatch (shared fold ≠ RNA binding) counts as an **extra** failure under item 2 or 3.
- `confidence_abstain` does **not** override this. Runtime `normalize_verdict` also enforces checklist ≥ 2 → low confidence.

### 7.4 Missing LOO prior (common for novel UniProt)

- Set `prior_missing=true` in reasoning / explanation
- Force low confidence
- Explain: LOO calibrates the **method** on held-out catalogue RBPs — it does **not** supply a per-target prior
- Never silently ignore a missing prior

### 7.5 Scientific caveat (always when transferring)

Transfer / “dark protein” scores are **cautious triage only** — **not** a substitute for CLIP / eCLIP wet-lab evidence. Say this in `explanation`.

If integrate tools fail: fall back to a weighted average of **tool-returned numbers only**. Still emit JSON; `p_hat` remains tool-sourced (or `null`).

---

