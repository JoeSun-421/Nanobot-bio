"""Build the promotion-gate artifact from two real transfer calibration runs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_real_report(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "transfer_calibration.v1":
        raise ValueError(f"not a transfer calibration report: {path}")
    regimes = data.get("regimes") or {}
    block = regimes.get("true_unseen")
    if not isinstance(block, dict):
        raise ValueError(f"true_unseen regime missing: {path}")
    rows = block.get("rows") or []
    if not rows or not all(
        row.get("aggregation_source") == "delivery_similarity_weighted_vote"
        and row.get("own_head_prob") is not None
        for row in rows
        if row.get("status") == "scored"
    ):
        raise ValueError(f"report lacks real delivery/own-head score provenance: {path}")
    return data


def build_promotion_report(
    *,
    baseline_report: Path,
    candidate_report: Path,
    candidate_policy: Path,
    train_ids: list[str],
    validation_ids: list[str],
    live_policy: Path,
) -> dict[str, Any]:
    baseline = _read_real_report(baseline_report)
    candidate = _read_real_report(candidate_report)
    train = {str(value) for value in train_ids}
    validation = {str(value) for value in validation_ids}
    if not train or not validation or train & validation:
        raise ValueError("train_ids and validation_ids must be nonempty and disjoint")
    if not candidate_policy.is_file():
        raise ValueError(f"candidate policy unavailable: {candidate_policy}")

    base_block = baseline["regimes"]["true_unseen"]
    cand_block = candidate["regimes"]["true_unseen"]
    base_auprc = (base_block.get("metrics") or {}).get("all_scored", {}).get("auprc")
    cand_auprc = (cand_block.get("metrics") or {}).get("all_scored", {}).get("auprc")
    if base_auprc is None or cand_auprc is None:
        raise ValueError("baseline/candidate true_unseen AUPRC unavailable")
    delta = float(cand_auprc) - float(base_auprc)
    n = int(cand_block.get("n_scored") or 0)
    return {
        "schema": "transfer_calibration.v1",
        "source_manifest": {
            "score_source": "real_rhobind",
            "reference_score_source": "real_rhobind_own_head",
            "synthetic": False,
            "inputs": [
                {"path": str(baseline_report.resolve()), "sha256": _sha256(baseline_report)},
                {"path": str(candidate_report.resolve()), "sha256": _sha256(candidate_report)},
            ],
        },
        "split_manifest": {
            "train_ids": sorted(train),
            "validation_ids": sorted(validation),
        },
        "objective": {"name": "delta_auprc", "regime": "true_unseen"},
        "before_after_metrics": {
            "baseline": {"auprc": float(base_auprc)},
            "candidate": {"auprc": float(cand_auprc)},
        },
        "promotion_metric": {
            "name": "delta_auprc",
            "score_source": "real_rhobind",
            "n": n,
            "value": delta,
        },
        "policy_manifest": {
            "candidate_path": str(candidate_policy.resolve()),
            "candidate_sha256": _sha256(candidate_policy),
        },
        "rollback": {
            "candidate_path": str(candidate_policy.resolve()),
            "live_path": str(live_policy.resolve()),
        },
        "decision": "PROMOTE" if n >= 10 and delta > 0 else "HOLD",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-policy", type=Path, required=True)
    parser.add_argument("--live-policy", type=Path, required=True)
    parser.add_argument("--train-id", action="append", required=True)
    parser.add_argument("--validation-id", action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_promotion_report(
        baseline_report=args.baseline,
        candidate_report=args.candidate,
        candidate_policy=args.candidate_policy,
        train_ids=args.train_id,
        validation_ids=args.validation_id,
        live_policy=args.live_policy,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"decision": report["decision"], "out": str(args.out)}))
    return 0 if report["decision"] == "PROMOTE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
