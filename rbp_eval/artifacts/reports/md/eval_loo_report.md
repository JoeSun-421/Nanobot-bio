# LOO light report

- protocol: `LOO light: hide head, select donors, lookup loo_transfer_metrics (no RhoBind re-run)`
- n: **10**
- mean policy_best AUPRC: **0.54445625**
- mean own_full AUPRC: **0.6848**
- mean gap (own − policy_best): **0.13360624999999998**

| held_rbp | own_full | policy_best | best_foreign | donors | status |
|---|---:|---:|---:|---|---|
| NSUN2 | 0.5832 | None | 0.56714 | - | fail_no_measured_donors |
| FXR2 | 0.7679 | 0.7449 | 0.7449 | FXR1,FMR1,PCBP1 | ok |
| HNRNPUL1 | 0.6133 | 0.49163 | 0.57173 | HNRNPU,SLTM,SAFB | ok |
| EEF2 | 0.6977 | 0.42461 | 0.69833 | EFTUD2 | ok |
| PTBP1 | 0.9311 | 0.51181 | 0.82453 | ELAVL1,SF3B4,TRA2A | ok |
| CPSF6 | 0.7846 | 0.67254 | 0.73258 | SF3B4,TRA2A,SRSF9 | ok |
| DHX30 | 0.4953 | 0.48448 | 0.50611 | DDX52,DDX47,DDX24 | ok |
| DDX51 | 0.5516 | 0.51691 | 0.51969 | DDX52,DDX47,DDX24 | ok |
| DROSHA | 0.583 | 0.50877 | 0.55649 | DGCR8,ILF3 | ok |
| RPS6 | 0.8403 | None | 0.81702 | - | fail_no_measured_donors |

## Failures

- **NSUN2**: no domain/seq hits
- **RPS6**: no domain/seq hits

## Deficiencies

- Light protocol: does not re-run RhoBind on test FASTA (needs rhobind env + panels).
- LOO priors calibrate transfer-as-a-method on held-out catalogue RBPs; dark/novel UniProt IDs correctly have no per-target LOO prior.
- Donor selection default=domain-only; pass --with-seq for ESM-C axis.
