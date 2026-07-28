# -*- coding: utf-8 -*-
"""RNA fusion gate — delivery has no RNA-FM axis; fusion rna_* stays 0."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.fusion_rna_policy import DEFAULT_REAL_WEIGHT, write_gate


def run_rna_fm_gate(*, fusion_weight: float = DEFAULT_REAL_WEIGHT) -> dict[str, Any]:
    """Always HOLD: RNA embed axis is not in delivery registry (use rna_blastn)."""
    del fusion_weight
    now = datetime.now(timezone.utc).isoformat()
    gate = {
        "schema": "rna_fm_eval_gate.v1",
        "generated_at": now,
        "allow_fusion": False,
        "decision": "HOLD",
        "reason": (
            "RNA fusion rna_*=0 (no delivery RNA-FM axis); RNA axis = rna_blastn"
        ),
        "checkpoint": None,
        "fusion_weight": 0.0,
    }
    write_gate(gate)
    return gate


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="RNA fusion gate (delivery-aligned)")
    ap.add_argument("--weight", type=float, default=DEFAULT_REAL_WEIGHT)
    args = ap.parse_args(argv)
    gate = run_rna_fm_gate(fusion_weight=float(args.weight))
    print(json.dumps(gate, indent=2, ensure_ascii=False))
    return 0 if gate.get("decision") in ("PROMOTE", "HOLD") else 1


if __name__ == "__main__":
    raise SystemExit(main())
