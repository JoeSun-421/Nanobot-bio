# Self-evolution and scientific memory assessment

## Status

The agent has an offline tuning pipeline, not an autonomous scientific discovery
engine. It can attribute tools, retune fusion/abstention/`tau_drop`, write a
candidate policy, run ablations, and update the proxy cache. Candidate deployment
remains a separate, human-invoked `promote-evolved` operation.

The light nested-split evaluator uses delivery LOO CSV lookups. It is useful as a
regression gate but is not instance-level transfer calibration and cannot, by
itself, justify promotion.

## Promotion evidence

Normal promotion now requires all of the following:

1. light LOO and evaluation-plan reports;
2. the retained `n >= 10` and `delta_auprc > 0` evolve decision;
3. `transfer_calibration.json` with real RhoBind scores, a positive
   before/after AUPRC delta, at least 10 scored cases, disjoint train/validation
   IDs, source hashes, objective metadata, an exact candidate-policy hash, and
   rollback paths; and
4. the existing RNA-axis hold: nonzero RNA fusion weight is rejected unless the
   delivery RNA/PEAKS capability is ready.

`--force` remains an explicit operator escape hatch for report checks. It does
not bypass the RNA capability hold.

## Memory boundary

`USER.md` and `MEMORY.md` are personal-assistant state and are excluded from the
scientific prompt. Recent-history injection is allowed only for the exact,
nonempty current session key with unified sessions disabled. Automatic Dream,
idle compaction, and token-triggered Consolidator runs are disabled for the RBP
agent, while the generic Nanobot implementation remains available.

The scientific domain memory is `artifacts/cache/proxy_map.json`. Its metadata
identifies it as `domain_memory` and records that `promote_from_traces` updates
repeated donor signatures from query-end traces. This cache changes retrieval
shortcuts only; it does not create or alter RhoBind scores.

