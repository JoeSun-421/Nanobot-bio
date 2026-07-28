#!/usr/bin/env python3
"""Reproduce immutable delivery release metrics without editing delivery."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
METRIC_RE = re.compile(r"AUPRC=([0-9.]+)\s+AUROC=([0-9.]+)")


def _assets(release: Path, cohort: str) -> tuple[Path, Path]:
    token = cohort.lower()
    checkpoint = (
        release
        / "checkpoints"
        / f"rhobind_{token}_mt_all118_cutoff08.ckpt"
    )
    head_index = release / "checkpoints" / f"head_index_{token}.json"
    return checkpoint, head_index


def reproduce(
    *,
    cohort: str | None = None,
    rbps: set[str] | None = None,
    device: str = "cuda",
    tolerance: float = 5e-4,
) -> dict[str, Any]:
    from app.backends.delivery.env import (
        apply_delivery_env,
        conda_env_python,
        resolve_delivery_paths,
    )

    apply_delivery_env()
    release = Path(resolve_delivery_paths()["rhobind_release"])
    expected_path = release / "expected_metrics.csv"
    python = conda_env_python("rhobind")
    if python is None:
        raise RuntimeError("rhobind conda Python unavailable")
    expected = list(csv.DictReader(expected_path.open(encoding="utf-8")))
    rows: list[dict[str, Any]] = []
    for reference in expected:
        cohort_name = str(reference["cohort"])
        rbp = str(reference["rbp"])
        if cohort and cohort_name.upper() != cohort.upper():
            continue
        if rbps and rbp.upper() not in {item.upper() for item in rbps}:
            continue
        checkpoint, head_index = _assets(release, cohort_name)
        fasta = release / "test_data" / cohort_name.lower() / rbp / "test.fasta"
        cmd = [
            str(python),
            str(release / "infer.py"),
            "--checkpoint",
            str(checkpoint),
            "--head_index",
            str(head_index),
            "--rbp",
            rbp,
            "--fasta",
            str(fasta),
            "--device",
            device,
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(release),
            env={**os.environ, "PYTHONPATH": str(release)},
            timeout=3600,
        )
        text = f"{proc.stdout}\n{proc.stderr}"
        match = METRIC_RE.search(text)
        measured_auprc = float(match.group(1)) if match else None
        measured_auroc = float(match.group(2)) if match else None
        expected_auprc = float(reference["auprc"])
        expected_auroc = float(reference["auroc"])
        passed = (
            proc.returncode == 0
            and measured_auprc is not None
            and measured_auroc is not None
            and abs(measured_auprc - expected_auprc) <= tolerance
            and abs(measured_auroc - expected_auroc) <= tolerance
        )
        rows.append(
            {
                "cohort": cohort_name,
                "rbp": rbp,
                "n_test": int(reference["n_test"]),
                "expected_auprc": expected_auprc,
                "measured_auprc": measured_auprc,
                "expected_auroc": expected_auroc,
                "measured_auroc": measured_auroc,
                "returncode": proc.returncode,
                "passed": passed,
                "error": None if passed else text[-1000:],
            }
        )
    return {
        "schema": "delivery_release_metrics.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if rows and all(row["passed"] for row in rows) else "fail",
        "tolerance": tolerance,
        "device": device,
        "expected_metrics": str(expected_path),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", choices=("K562", "HepG2"), default=None)
    parser.add_argument("--rbp", action="append", default=None)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--tolerance", type=float, default=5e-4)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "artifacts" / "reports" / "release_metrics.json",
    )
    args = parser.parse_args()
    report = reproduce(
        cohort=args.cohort,
        rbps=set(args.rbp or []) or None,
        device=args.device,
        tolerance=args.tolerance,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "out": str(args.out)}, indent=2))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
