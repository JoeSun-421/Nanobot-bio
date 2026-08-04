# -*- coding: utf-8 -*-
"""Package transfer-calibration evidence for promote-evolved after evolve.

Runs live calibration under live vs candidate runtime config, then builds the
promotion-gate ``transfer_calibration.json`` via ``transfer_promotion``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from app.core.paths import PACKAGE_ROOT, REPORTS, ensure_artifact_dirs, report_path
from rbp_eval.evolve.promote import CANDIDATE_CONFIG, EVOLVED_CONFIG
from rbp_eval.evolve.transfer_promotion import build_promotion_report
from rbp_eval.loo.heavy_loo import MEDOIDS


def _write(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def attach_calibration_evidence(
    *,
    candidate: Path = CANDIDATE_CONFIG,
    live: Path = EVOLVED_CONFIG,
    cohort: str = "K562",
    top_k: int = 5,
    max_seqs: int = 32,
    device: str = "cuda",
    targets: Optional[list[str]] = None,
    out_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Produce promote-ready transfer_calibration.json from two live runs.

    Temporarily sets ``RBP_RUNTIME_CONFIG`` so fusion/abstain knobs come from
    live vs candidate YAML without mutating ``evolved.yaml``.
    """
    from app.core.runtime_config import clear_runtime_config_cache
    from rbp_eval.accept.transfer_calibration import TRUE_UNSEEN, run_live_calibration

    ensure_artifact_dirs()
    root = Path(out_dir or REPORTS)
    candidate = Path(candidate).expanduser()
    live = Path(live).expanduser()
    if not candidate.is_file():
        return {
            "ok": False,
            "status": "skipped",
            "reason": f"candidate missing: {candidate}",
        }

    helds = list(targets) if targets else list(MEDOIDS)
    train_ids = helds[: max(1, len(helds) // 2)]
    val_ids = helds[len(train_ids) :]
    if not val_ids:
        val_ids = [helds[0]]
        train_ids = helds[1:] or [helds[0] + "_train_placeholder"]
        # Ensure disjoint: if only one held, synthesize train id
        if train_ids == val_ids:
            train_ids = [f"{helds[0]}__train"]
    prev_cfg = os.environ.get("RBP_RUNTIME_CONFIG")
    baseline_path = report_path("transfer_calibration_baseline.json", root=root)
    candidate_run_path = report_path("transfer_calibration_candidate_run.json", root=root)
    promote_path = report_path("transfer_calibration.json", root=root)

    try:
        # Baseline: live evolved (or defaults)
        if live.is_file():
            os.environ["RBP_RUNTIME_CONFIG"] = str(live.resolve())
        else:
            os.environ.pop("RBP_RUNTIME_CONFIG", None)
        clear_runtime_config_cache()
        baseline = run_live_calibration(
            regimes=(TRUE_UNSEEN,),
            targets=helds,
            cohort=cohort,
            top_k=top_k,
            max_seqs=max_seqs,
            device=device,
            with_seq=False,
            with_rna=False,
        )
        _write(baseline_path, baseline)

        # Candidate policy
        os.environ["RBP_RUNTIME_CONFIG"] = str(candidate.resolve())
        clear_runtime_config_cache()
        cand_report = run_live_calibration(
            regimes=(TRUE_UNSEEN,),
            targets=helds,
            cohort=cohort,
            top_k=top_k,
            max_seqs=max_seqs,
            device=device,
            with_seq=False,
            with_rna=False,
        )
        _write(candidate_run_path, cand_report)

        promo = build_promotion_report(
            baseline_report=baseline_path,
            candidate_report=candidate_run_path,
            candidate_policy=candidate,
            train_ids=train_ids,
            validation_ids=val_ids,
            live_policy=live if live.is_file() else PACKAGE_ROOT / "config" / "defaults.yaml",
        )
        _write(promote_path, promo)

        # Nested evolve_eval decision advisory (does not replace real Δ)
        decision_path = report_path("evolve_eval_decision.json", root=root)
        n_pm = int((promo.get("promotion_metric") or {}).get("n") or 0)
        delta_pm = float((promo.get("promotion_metric") or {}).get("value") or 0.0)
        decision = {
            "schema": "evolve_eval_decision/v1",
            "source": "calibration_evidence",
            "n": n_pm,
            "delta_auprc": delta_pm,
            "decision": "PROMOTE" if (n_pm >= 10 and delta_pm > 0) else "HOLD",
            "note": (
                "Aligned with transfer_calibration promotion_metric; "
                "CSV-only evolve-eval is advisory only."
            ),
        }
        _write(decision_path, decision)

        return {
            "ok": True,
            "status": "ok",
            "paths": {
                "baseline": str(baseline_path),
                "candidate_run": str(candidate_run_path),
                "transfer_calibration": str(promote_path),
                "evolve_eval_decision": str(decision_path),
            },
            "decision": promo.get("decision"),
            "promotion_metric": promo.get("promotion_metric"),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "status": "failed",
            "reason": f"{type(e).__name__}: {e}",
            "paths": {
                "baseline": str(baseline_path) if baseline_path.is_file() else None,
                "candidate_run": str(candidate_run_path) if candidate_run_path.is_file() else None,
            },
        }
    finally:
        if prev_cfg is None:
            os.environ.pop("RBP_RUNTIME_CONFIG", None)
        else:
            os.environ["RBP_RUNTIME_CONFIG"] = prev_cfg
        clear_runtime_config_cache()
