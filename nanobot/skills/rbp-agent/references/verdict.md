# Verdict JSON schema (detail)

> Loaded on demand. SKILL.md keeps the minimal output contract.

## 8. Final JSON output

Your **entire** final message must be one object:

```json
{
  "label": "Strong",
  "p_hat": 0.0,
  "confidence": "high",
  "explanation": "3–5 plain sentences grounded only in tool outputs.",
  "supporting_rbps": [
    {
      "rbp_id": "P26599",
      "alias": "PTBP1",
      "prob": 0.966,
      "similarity_score": 1.0,
      "similarity_breakdown": {"esmc_cosine": 1.0}
    }
  ],
  "caveats": ["optional: structure_axis unavailable; prior_missing; …"],
  "evidence_flags": {
    "checklist_failures": 0
  }
}
```

### 8.1 When optional fields are required

| Situation | Must include |
| --- | --- |
| Unseen / force_transfer path | `caveats` (method limits + any failed axes) |
| Multi-view fuse produced modality scores | `similarity_breakdown` on each supporting donor when available |
| Checklist ≥ 2 failures | Low confidence **and** list failures in `caveats` / `evidence_flags` |
| `literature_search` failed or skipped | `caveats` entry `literature_unavailable` or `literature_skipped` |

Do **not** omit `caveats` on unseen paths just because `label` is Likely/Strong.

### 8.2 Field reference

| Field | Type | Rules |
| --- | --- | --- |
| `label` | string | One of `Strong` \| `Likely` \| `Unlikely` \| `No` |
| `p_hat` | number or `null` | From predict / vote tools only |
| `confidence` | string | Enum `high` \| `medium` \| `low` (verdict-level). A float in `[0,1]` is accepted and coerced (≥0.75→high, ≥0.45→medium, else low); checklist ≥ 2 failures → `low`. Distinct from delivery per-donor head scores — not used in `p_hat` aggregation. |
| `explanation` | string | Grounded prose; mention stage path + checklist count when relevant |
| `supporting_rbps` | array | Donors or own-head row with `rbp_id`, `alias`, `prob`, `similarity_score` |
| `caveats` | array (optional) | Structure unavailable, prior missing, literature skipped, … |
| `evidence_flags` | object (optional) | Tool-sourced flags; ≥ 2 checklist failures → force low confidence |

### 8.3 Label cuts (Table defaults)

| Label | When |
| --- | --- |
| **Strong** | `p_hat ≥ 0.75` |
| **Likely** | `p_hat ≥ 0.50` |
| **Unlikely** | `p_hat ≥ 0.25` |
| **No** | otherwise |

On predict failure: `"p_hat": null`, low confidence, label typically `"No"` (do not overclaim Strong).

---

