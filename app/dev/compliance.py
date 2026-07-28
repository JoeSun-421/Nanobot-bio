#!/usr/bin/env python3
"""Self-check agent package against delivery markdown requirements.

Checks HANDOFF / SETUP / AGENT_BUILD_SPEC structural rules.
Exit 0 if critical checks pass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.backends.delivery.client import SCRIPT_MAP, DeliveryToolClient, tools_meta_by_name
    from app.backends.delivery.env import apply_delivery_env, resolve_delivery_paths

    print("=== COMPLIANCE CHECK (delivery markdown) ===")
    apply_delivery_env()
    paths = resolve_delivery_paths()
    checks = []

    def add(name: str, ok: bool, detail: str = ""):
        checks.append((name, ok, detail))
        flag = "PASS" if ok else "FAIL"
        print(f"[{flag}] {name}" + (f" — {detail}" if detail else ""))

    # SETUP / HANDOFF paths
    add("DELIVERY_ROOT exists", paths["delivery_root"].is_dir(), str(paths["delivery_root"]))
    add("agent_db present", paths["agent_db"].is_dir())
    add("RBP registry present", paths["rbp_registry"].is_file())
    add("tools/registry.json present", paths["registry_json"].is_file())
    add("predict_api present", paths["predict_api"].is_file())
    add("release present", paths["rhobind_release"].is_dir())
    add("setup.sh present", paths["setup_sh"].is_file())

    # Registry tools ready
    meta = tools_meta_by_name()
    add("registry has 24 tools", len(meta) == 24, f"n={len(meta)}")
    ready = [n for n, t in meta.items() if t.get("status") == "ready"]
    add("all tools status=ready", len(ready) == len(meta), f"ready={len(ready)}")

    # SCRIPT_MAP covers registry tools we need for pipeline
    required = {
        "resolve_rbp", "domain_architecture", "esm_similarity",
        "protein_seq_similarity", "struct_similarity_foldseek",
        "rhobind_predict", "rna_preprocess",
        "similarity_weighted_vote", "transfer_prior_lookup",
        "confidence_abstain", "donor_quality_prior",
        "uniprot_annotation", "structure_fetch",
    }
    missing = sorted(required - set(SCRIPT_MAP))
    add("SCRIPT_MAP covers pipeline tools", not missing, str(missing))

    for n in sorted(required):
        if n in SCRIPT_MAP:
            p = paths["delivery_root"] / SCRIPT_MAP[n]
            add(f"script exists: {n}", p.is_file(), SCRIPT_MAP[n])

    # Pure-python tool invocation (HANDOFF contract)
    cli = DeliveryToolClient(offline=True, use_conda=False, device="cpu")
    r = cli.call("resolve_rbp", {"query": "PTBP1"})
    add("resolve_rbp import/run", bool(r.get("matched") and r.get("alias") == "PTBP1"), str(r.get("error")))

    dom = cli.call("domain_architecture", {"alias": "PTBP1", "top_k": 5})
    add("domain_architecture run", bool(dom.get("hits")), dom.get("error") or f"n={len(dom.get('hits') or [])}")

    vote = cli.call(
        "similarity_weighted_vote",
        {
            "predictions": [{"alias": "U2AF2", "prob": 0.2}, {"alias": "QKI", "prob": 0.3}],
            "hits": [{"alias": "U2AF2", "score": 0.96}, {"alias": "QKI", "score": 0.95}],
        },
    )
    add("similarity_weighted_vote run", vote.get("score") is not None, str(vote.get("score")))

    tprior = cli.call("transfer_prior_lookup", {"target": "PTBP1", "donors": ["U2AF2", "QKI"]})
    add("transfer_prior_lookup run", "priors" in tprior, tprior.get("error"))

    qual = cli.call("donor_quality_prior", {"donors": ["U2AF2"], "cohort": "K562"})
    add("donor_quality_prior run", "quality" in qual, qual.get("error"))

    abst = cli.call(
        "confidence_abstain",
        {"hits": [{"alias": "U2AF2", "score": 0.96, "metric": "esmc_cosine"}]},
    )
    add("confidence_abstain run", "confident" in abst, abst.get("error"))

    # Fixed pipeline removed — Stage-0 wiring checked via resolve + examples
    from app.backends.delivery.examples import load_example
    try:
        ex = load_example("pos")
        add("golden example pos loads", len(ex["rna"]) == 128, f"len={len(ex['rna'])}")
    except Exception as e:
        add("golden example pos loads", False, str(e))

    # Identifier convention
    add("IDs use alias+uniprot in resolve", r.get("uniprot") == "P26599")

    failed = [c for c in checks if not c[1] and "optional" not in c[0]]
    # only hard fails
    hard_fail = [
        c for c in checks
        if not c[1] and "optional" not in c[0] and "rhobind_predict" not in c[0]
    ]
    print("---")
    print(f"total={len(checks)} hard_fail={len(hard_fail)}")
    report = {
        "total": len(checks),
        "hard_fail": len(hard_fail),
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }
    outp = ROOT / "artifacts" / "reports" / "compliance_report.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {outp}")
    return 0 if not hard_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
