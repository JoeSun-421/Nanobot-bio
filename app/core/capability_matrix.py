# -*- coding: utf-8 -*-
"""Single source of truth for agent capability honesty (doctor / layout / promote)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.core.paths import CACHE, REPORTS_JSON, ensure_artifact_dirs, find_report
from app.core.runtime_config import load_runtime_config

REPO_ROOT = Path(__file__).resolve().parents[2]
# AF3 host status lives outside the git workspace by default (never under the repo).
# Override with AF3_STATUS_FILE. Legacy repo-root ``.af3_status`` is still read as fallback.
_LEGACY_AF3_STATUS_PATH = REPO_ROOT / ".af3_status"
DELIVERY_SMOKE_REPORT_PATH = REPORTS_JSON / "delivery_tools_smoke_report.json"


def af3_status_path() -> Path:
    """Resolved path for the AF3 ``state=...`` status file (outside the repo)."""
    override = (os.environ.get("AF3_STATUS_FILE") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    xdg = (os.environ.get("XDG_CACHE_HOME") or "").strip()
    cache_root = Path(xdg).expanduser() if xdg else (Path.home() / ".cache")
    return (cache_root / "nanobot-bio" / "af3_status").resolve()


# Back-compat alias for callers that still import AF3_STATUS_PATH as a Path.
# Prefer af3_status_path() — this is resolved once at import for display only.
AF3_STATUS_PATH = af3_status_path()

# Product: predict_interaction uses the same formula as similarity_weighted_vote.
SIMILARITY_WEIGHTED_VOTE_DRIVES_P_HAT = True

P_HAT_FORMULA = {
    "source": "delivery_similarity_weighted_vote",
    "formula": "sum(s_i * tprior_i * quality_i * prob_i) / sum(s_i * tprior_i * quality_i)",
    "note": "s_i from commit_proxy_candidates; priors optional when lookup missing",
}

RNA_FUSION_KEYS = ("rna_peak_homology",)


def _resolve_af3_status_file() -> Path | None:
    """Return the first existing AF3 status file (canonical, then legacy repo root)."""
    for path in (af3_status_path(), _LEGACY_AF3_STATUS_PATH):
        if path.is_file():
            return path
    return None


def read_af3_status() -> dict[str, str]:
    """Parse AF3 status key=value lines into a dict (empty if missing)."""
    path = _resolve_af3_status_file()
    out: dict[str, str] = {}
    if path is None:
        return out
    raw = path.read_text(encoding="utf-8", errors="replace")
    for line in raw.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def af3_runtime_status(status: dict[str, str] | None = None) -> str:
    """Map host AF3 status file + AF3_PYTHON → ready|degraded|off."""
    st = status if status is not None else read_af3_status()
    first = (st.get("state") or "").strip().lower()
    if first == "ok":
        return "ready"
    if first in ("deferred", "import_ok"):
        return "degraded"
    if first in ("broken", "missing"):
        return "off"
    if not (os.environ.get("AF3_PYTHON") or "").strip():
        return "degraded"
    return "ready"


def delivery_smoke_report_status(path: Path | None = None) -> dict[str, Any]:
    """Summarize the latest registry-driven delivery smoke report, if present."""
    smoke_path = path or find_report("delivery_tools_smoke_report.json") or DELIVERY_SMOKE_REPORT_PATH
    base: dict[str, Any] = {
        "status": "unavailable",
        "path": str(smoke_path),
        "generated_at": None,
        "summary": {},
        "coverage_ok": None,
    }
    if not smoke_path.is_file():
        base["reason"] = "delivery smoke report has not been generated"
        return base
    try:
        data = json.loads(smoke_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        base["reason"] = f"invalid delivery smoke report: {type(exc).__name__}"
        return base
    if not isinstance(data, dict):
        base["reason"] = "invalid delivery smoke report: root is not an object"
        return base
    report_status = str(data.get("status") or "unknown").lower()
    base.update(
        {
            "status": "ready" if report_status == "pass" else "degraded",
            "report_status": report_status,
            "generated_at": data.get("generated_at"),
            "summary": dict(data.get("summary") or {}),
            "coverage_ok": (data.get("coverage") or {}).get("ok"),
        }
    )
    if report_status != "pass":
        base["reason"] = "latest delivery smoke report did not pass"
    return base


def feature_attribution_status() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "source": "unavailable",
        "reason": "saliency is delivery v2; predict rows stub empty dict",
    }


def rna_blastn_status() -> dict[str, Any]:
    """Delivery registry RNA axis (proposal Table 1 optional)."""
    from app.backends.delivery.env import try_delivery_root

    delivery = try_delivery_root()
    peaks = (os.environ.get("PEAKS_DB") or "").strip()
    if delivery is None or not delivery.is_dir():
        return {
            "status": "unavailable",
            "reason": "DELIVERY_ROOT missing",
            "tool": "rna_blastn",
        }
    if peaks and Path(peaks).exists():
        return {
            "status": "ready",
            "reason": f"delivery present; PEAKS_DB={peaks}",
            "tool": "rna_blastn",
        }
    return {
        "status": "degraded",
        "reason": "delivery present; PEAKS_DB unset or missing — axis may skip",
        "tool": "rna_blastn",
    }


def fusion_rna_weights(cfg: dict[str, Any] | None = None) -> dict[str, float]:
    if cfg is None:
        cfg = load_runtime_config(prefer_evolved=True)
    fw = dict(cfg.get("fusion_weights") or {})
    out: dict[str, float] = {}
    for k in RNA_FUSION_KEYS:
        try:
            out[k] = float(fw.get(k, 0.0) or 0.0)
        except (TypeError, ValueError):
            out[k] = 0.0
    return out


def assert_rna_fusion_promotable(cfg: dict[str, Any]) -> None:
    """Hard-fail promote when RNA fusion weight > 0 without peaks DB."""
    if rna_blastn_status().get("status") == "ready":
        return
    bad = {k: v for k, v in fusion_rna_weights(cfg).items() if v > 0.0}
    if bad:
        raise ValueError(
            "rna_peak_homology fusion weight must be 0 without PEAKS_DB; "
            f"got {bad}. Set weight to 0.0 or build peaks DB."
        )


def model_specs() -> dict[str, dict[str, Any]]:
    cfg = load_runtime_config(prefer_evolved=False)
    raw = cfg.get("models") or {}
    return {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}


def probe_model_capabilities() -> dict[str, Any]:
    """Per-model ready/degraded/unavailable (used by doctor artifact)."""
    from app.backends.delivery.env import try_delivery_root

    specs = model_specs()
    delivery = try_delivery_root()
    af3 = read_af3_status()
    matrix: dict[str, Any] = {}

    for name, spec in specs.items():
        entry: dict[str, Any] = {
            "tool": spec.get("tool"),
            "backend": spec.get("backend"),
            "status": "unknown",
            "reason": "",
        }
        backend = spec.get("backend")
        if backend == "delivery":
            env_name = spec.get("conda_env")
            if delivery is None or not delivery.is_dir():
                entry["status"] = "unavailable"
                entry["reason"] = "DELIVERY_ROOT missing"
            else:
                entry["status"] = "ready"
                entry["reason"] = f"delivery present; conda_env={env_name}"
                if name == "af3":
                    first = (af3.get("state") or "").strip().lower()
                    entry["af3_status_file"] = first or "unknown"
                    entry["af3_python"] = af3.get("af3_python") or os.environ.get(
                        "AF3_PYTHON", ""
                    )
                    if not (os.environ.get("AF3_PYTHON") or "").strip() and not af3.get(
                        "af3_python"
                    ):
                        entry["status"] = "degraded"
                        entry["reason"] = "AF3_PYTHON unset; use AFDB/Foldseek fallback"
                    if first == "ok":
                        entry["status"] = "ready"
                        entry["reason"] = "AF3 probe ok"
                    elif first in ("deferred", "import_ok"):
                        entry["status"] = "degraded"
                        entry["reason"] = f".af3_status={first}; prefer AFDB"
                    elif first in ("broken", "missing"):
                        entry["status"] = "unavailable"
                        entry["reason"] = f".af3_status={first}; AFDB only"
                    elif not first and not (os.environ.get("AF3_PYTHON") or "").strip():
                        entry["status"] = "degraded"
                        entry["reason"] = "AF3_PYTHON unset; use AFDB/Foldseek fallback"
                if name == "esm_c":
                    entry["cache"] = str(CACHE / "esm")
                if name == "rna_blastn":
                    peaks = (os.environ.get("PEAKS_DB") or "").strip()
                    if peaks and Path(peaks).exists():
                        entry["reason"] = f"delivery present; PEAKS_DB={peaks}"
                    else:
                        entry["status"] = "degraded"
                        entry["reason"] = (
                            "delivery present; PEAKS_DB unset or missing — axis may skip"
                        )
        elif backend == "agent_local":
            ckpt_env = str(spec.get("checkpoint_env") or "")
            ckpt = (os.environ.get(ckpt_env) or "").strip() if ckpt_env else ""
            if ckpt and Path(ckpt).is_file():
                entry["status"] = "ready"
                entry["reason"] = f"{ckpt_env} set"
                entry["mode"] = "real"
            else:
                entry["status"] = "unavailable"
                entry["reason"] = "agent-local; not in delivery registry"
                entry["mode"] = "unavailable"
        else:
            entry["status"] = "unknown"
            entry["reason"] = f"backend={backend}"
        matrix[name] = entry

    return {
        "models": matrix,
        "n_ready": sum(1 for v in matrix.values() if v.get("status") == "ready"),
        "n_degraded": sum(1 for v in matrix.values() if v.get("status") == "degraded"),
        "n_unavailable": sum(
            1 for v in matrix.values() if v.get("status") == "unavailable"
        ),
    }


def probe_capabilities() -> dict[str, Any]:
    """Full honesty matrix: models + product feature contracts."""
    models = probe_model_capabilities()
    af3 = read_af3_status()
    axes = dict(load_runtime_config(prefer_evolved=False).get("axes") or {})
    return {
        "models": models["models"],
        "n_ready": models["n_ready"],
        "n_degraded": models["n_degraded"],
        "n_unavailable": models["n_unavailable"],
        "features": {
            "delivery_tool_smoke": delivery_smoke_report_status(),
            "rna_blastn": rna_blastn_status(),
            "feature_attribution": feature_attribution_status(),
            "af3": {
                "status": af3_runtime_status(af3),
                "state_file": af3.get("state") or "missing",
                "af3_python": af3.get("af3_python")
                or (os.environ.get("AF3_PYTHON") or ""),
                "axes_use_af3": bool(axes.get("use_af3")),
                "status_path": str(
                    _resolve_af3_status_file() or af3_status_path()
                ),
            },
            "similarity_weighted_vote_drives_p_hat": SIMILARITY_WEIGHTED_VOTE_DRIVES_P_HAT,
            "p_hat_formula": dict(P_HAT_FORMULA),
            "rna_fusion_weights": fusion_rna_weights(
                load_runtime_config(prefer_evolved=False)
            ),
        },
    }


def write_capability_matrix(path: Path | None = None) -> Path:
    ensure_artifact_dirs()
    out = path or (REPORTS_JSON / "model_capability_matrix.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    data = probe_capabilities()
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
