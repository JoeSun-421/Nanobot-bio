# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

import yaml

from app.core.paths import (
    DEFAULT_EVOLVE_REPORT,
    PACKAGE_ROOT,
    ensure_artifact_dirs,
)

DEFAULT_CONFIG = PACKAGE_ROOT / "config" / "defaults.yaml"
EVOLVED_CONFIG = PACKAGE_ROOT / "config" / "evolved.yaml"
CANDIDATE_CONFIG = PACKAGE_ROOT / "config" / "evolved.candidate.yaml"
CANDIDATE_SEED = PACKAGE_ROOT / "config" / "evolved.candidate.yaml.example"
EVOLVED_REPORT = DEFAULT_EVOLVE_REPORT
ensure_artifact_dirs()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid {label} JSON at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Invalid {label}: expected a JSON object at {path}")
    return data


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_legacy_evolve_decision(path: Path) -> dict[str, Any]:
    """Retain the existing n>=10 and positive-delta promotion gate."""
    data = _read_json_object(path, "evolve decision")
    if data.get("decision") != "PROMOTE":
        raise ValueError(f"Evolve decision is not PROMOTE: {data.get('decision')}")
    if int(data.get("n") or 0) < 10:
        raise ValueError(f"Evolve decision n<10: {data.get('n')}")
    try:
        delta = float(data["delta_auprc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Evolve decision missing numeric delta_auprc") from exc
    if delta <= 0.0:
        raise ValueError(f"Evolve decision delta_auprc<=0: {delta}")
    return data


def assert_transfer_calibration_report(path: Path) -> dict[str, Any]:
    """Require real RhoBind transfer evidence and reproducibility manifests."""
    data = _read_json_object(path, "transfer-calibration report")
    if data.get("schema") != "transfer_calibration.v1":
        raise ValueError("Transfer calibration schema must be transfer_calibration.v1")

    source = data.get("source_manifest")
    if not isinstance(source, dict):
        raise ValueError("Transfer calibration missing source_manifest")
    if (
        source.get("score_source") != "real_rhobind"
        or source.get("reference_score_source") != "real_rhobind_own_head"
        or source.get("synthetic") is not False
    ):
        raise ValueError(
            "Transfer calibration must use real_rhobind transfer and own-head "
            "reference scores with synthetic=false"
        )
    inputs = source.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("Transfer calibration source_manifest.inputs is empty")
    for item in inputs:
        if (
            not isinstance(item, dict)
            or not item.get("path")
            or not item.get("sha256")
        ):
            raise ValueError(
                "Each transfer calibration input requires path and sha256"
            )
        digest = str(item["sha256"]).lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Transfer calibration input sha256 must be 64 hex chars")
        input_path = Path(str(item["path"])).expanduser()
        if not input_path.is_absolute():
            input_path = path.parent / input_path
        if not input_path.is_file():
            raise ValueError(
                f"Transfer calibration manifest input is unavailable: {input_path}"
            )
        if _sha256(input_path) != digest:
            raise ValueError(
                f"Transfer calibration manifest sha256 mismatch: {input_path}"
            )

    split = data.get("split_manifest")
    if not isinstance(split, dict):
        raise ValueError("Transfer calibration missing split_manifest")
    train = {str(x) for x in split.get("train_ids") or []}
    validation = {str(x) for x in split.get("validation_ids") or []}
    if not train or not validation or train & validation:
        raise ValueError(
            "Transfer calibration needs nonempty disjoint train_ids/validation_ids"
        )

    objective = data.get("objective")
    if not isinstance(objective, dict) or objective.get("name") != "delta_auprc":
        raise ValueError("Transfer calibration objective.name must be delta_auprc")
    before_after = data.get("before_after_metrics")
    if not isinstance(before_after, dict):
        raise ValueError("Transfer calibration missing before_after_metrics")
    try:
        baseline = float((before_after.get("baseline") or {})["auprc"])
        candidate = float((before_after.get("candidate") or {})["auprc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Transfer calibration requires baseline/candidate AUPRC"
        ) from exc

    metric = data.get("promotion_metric")
    if not isinstance(metric, dict) or metric.get("name") != "delta_auprc":
        raise ValueError("Transfer calibration promotion_metric must be delta_auprc")
    if metric.get("score_source") != "real_rhobind":
        raise ValueError("Promotion metric score_source must be real_rhobind")
    try:
        n = int(metric["n"])
        delta = float(metric["value"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Promotion metric requires numeric n and value") from exc
    if n < 10:
        raise ValueError(f"Transfer calibration promotion metric n<10: {n}")
    if delta <= 0.0:
        raise ValueError(f"Transfer calibration delta_auprc<=0: {delta}")
    if abs(delta - (candidate - baseline)) > 1e-6:
        raise ValueError(
            "Transfer calibration delta_auprc does not match before/after AUPRC"
        )

    policy = data.get("policy_manifest")
    if (
        not isinstance(policy, dict)
        or not policy.get("candidate_path")
        or not policy.get("candidate_sha256")
    ):
        raise ValueError(
            "Transfer calibration requires policy_manifest candidate_path/sha256"
        )
    candidate_digest = str(policy["candidate_sha256"]).lower()
    if len(candidate_digest) != 64 or any(
        c not in "0123456789abcdef" for c in candidate_digest
    ):
        raise ValueError("Policy candidate_sha256 must be 64 hex chars")
    candidate_path = Path(str(policy["candidate_path"])).expanduser()
    if not candidate_path.is_absolute():
        candidate_path = path.parent / candidate_path
    if not candidate_path.is_file():
        raise ValueError(f"Policy candidate unavailable: {candidate_path}")
    if _sha256(candidate_path) != candidate_digest:
        raise ValueError("Policy candidate checksum changed after calibration")

    rollback = data.get("rollback")
    if (
        not isinstance(rollback, dict)
        or not rollback.get("candidate_path")
        or not rollback.get("live_path")
    ):
        raise ValueError(
            "Transfer calibration requires rollback candidate_path/live_path"
        )
    return data


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_evolved_config(
    *,
    tuned_weights: dict[str, float],
    thresholds: dict[str, float],
    path: Path = CANDIDATE_CONFIG,
    base_path: Path = DEFAULT_CONFIG,
    promoted: bool = False,
    abstain_thresholds: Optional[dict[str, float]] = None,
    tau_drop: Optional[float] = None,
) -> Path:
    """Write evolved knobs. Default path is *candidate* (not live until promote)."""
    # Prefer existing target file so abstain_thresholds / axes survive retunes
    cfg = _load_yaml(path) if path.is_file() else {}
    if not cfg:
        # seed from live evolved or defaults
        cfg = _load_yaml(EVOLVED_CONFIG) if EVOLVED_CONFIG.is_file() else {}
    if not cfg:
        cfg = _load_yaml(base_path)
    # Always take fusion/label defaults as floor, then apply tuned values (incl. 0.0)
    base = _load_yaml(base_path)
    fw = {**(base.get("fusion_weights") or {}), **(cfg.get("fusion_weights") or {})}
    for k, v in (tuned_weights or {}).items():
        try:
            fw[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    cfg["fusion_weights"] = fw
    cfg["label_thresholds"] = {
        **(base.get("label_thresholds") or {}),
        **(cfg.get("label_thresholds") or {}),
        **(thresholds or {}),
    }
    ab = {
        **(base.get("abstain_thresholds") or {}),
        **(cfg.get("abstain_thresholds") or {}),
    }
    if abstain_thresholds:
        for k, v in abstain_thresholds.items():
            try:
                ab[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
    if ab:
        cfg["abstain_thresholds"] = ab
    elif "abstain_thresholds" not in cfg and base.get("abstain_thresholds"):
        cfg["abstain_thresholds"] = dict(base["abstain_thresholds"])
    if tau_drop is not None:
        try:
            cfg["tau_drop"] = float(tau_drop)
        except (TypeError, ValueError):
            pass
    elif "tau_drop" not in cfg and base.get("tau_drop") is not None:
        cfg["tau_drop"] = base["tau_drop"]
    ver = str(cfg.get("schema_version") or base.get("schema_version") or "2.0")
    if not ver.endswith("+evolved"):
        ver = ver + "+evolved"
    cfg["schema_version"] = ver
    cfg["evolved"] = bool(promoted)
    cfg["candidate"] = not bool(promoted)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
    return path


def promote_evolved_config(
    *,
    candidate: Path = CANDIDATE_CONFIG,
    live: Path = EVOLVED_CONFIG,
    require_reports: bool = True,
    seed: bool = False,
    reports_dir: Path | None = None,
) -> Path:
    """Promote candidate after light, real-transfer, manifest, and RNA gates.

    Mirrors DSPy/Haystack: offline compile, then gate, then deploy policy.

    C6: when ``seed=True`` and the candidate file is missing (e.g. fresh clone —
    ``evolved.candidate.yaml`` is gitignored), copy the tracked seed
    ``evolved.candidate.yaml.example`` → candidate first so the promote link is
    reproducible without running the full ``evolve`` loop.
    """
    if not candidate.is_file():
        if seed and CANDIDATE_SEED.is_file():
            import shutil

            candidate.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(CANDIDATE_SEED, candidate)
        else:
            raise FileNotFoundError(
                f"No candidate config at {candidate}. Run: rbp-agent evolve"
                + ("" if seed else "  (or `rbp-agent promote-evolved --seed` to bootstrap)")
            )
    if require_reports:
        from app.dev.gate import assert_eval_plan_report, assert_loo_report
        from app.core.paths import REPORTS, find_report

        report_root = reports_dir or REPORTS
        loo = find_report("eval_loo_report.json", root=report_root)
        plan = find_report("evaluation_plan_report.json", root=report_root)
        if loo is None or plan is None:
            raise FileNotFoundError(
                "Missing light eval reports. Run: rbp-agent gate   "
                "(expected eval_loo_report.json and evaluation_plan_report.json "
                f"under {report_root}/json/ or flat)"
            )
        assert_loo_report(loo)
        assert_eval_plan_report(plan)
        decision = find_report("evolve_eval_decision.json", root=report_root)
        if decision is None:
            raise FileNotFoundError(
                f"Missing evolve_eval_decision.json under {report_root}"
            )
        assert_legacy_evolve_decision(decision)
        transfer = find_report("transfer_calibration.json", root=report_root)
        if transfer is None:
            raise FileNotFoundError(
                f"Missing transfer_calibration.json under {report_root}"
            )
        transfer_report = assert_transfer_calibration_report(transfer)
        expected_candidate_sha = str(
            (transfer_report.get("policy_manifest") or {}).get("candidate_sha256")
            or ""
        ).lower()
        actual_candidate_sha = _sha256(candidate)
        if actual_candidate_sha != expected_candidate_sha:
            raise ValueError(
                "Candidate config sha256 does not match transfer calibration "
                "policy_manifest"
            )
        # Refuse promote when the latest evolve report was retrieval-only synthetic.
        # Stay under report_root (do not leak to the live DEFAULT_EVOLVE_REPORT).
        evolve_rep = find_report("evolve_report.json", root=report_root) or find_report(
            EVOLVED_REPORT.name, root=report_root
        )
        if evolve_rep is not None and evolve_rep.is_file():
            try:
                er = json.loads(evolve_rep.read_text(encoding="utf-8"))
            except Exception:
                er = {}
            if er.get("status") == "blocked" or er.get("promote_blocked"):
                raise ValueError(
                    f"Evolve report blocks promote ({evolve_rep}): "
                    f"{er.get('reason') or er.get('notes')}"
                )
            if er.get("scores_source") == "retrieval_only_synthetic":
                raise ValueError(
                    "Refuse promote: evolve scores_source=retrieval_only_synthetic"
                )

    cfg = _load_yaml(candidate)
    from app.core.capability_matrix import assert_rna_fusion_promotable

    assert_rna_fusion_promotable(cfg)
    cfg["evolved"] = True
    cfg["candidate"] = False
    live.parent.mkdir(parents=True, exist_ok=True)
    with open(live, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)
    try:
        from app.core.runtime_config import clear_runtime_config_cache

        clear_runtime_config_cache()
    except Exception:
        pass
    return live

