# -*- coding: utf-8 -*-
"""Run a registry-driven smoke matrix through the nanobot-bio delivery bridge.

The delivery registry is authoritative: every registered tool must have a bridge
mapping, an app mapping entry, and a real scenario here. External prerequisites
are reported separately from failures. A machine-readable report is always
written under ``artifacts/reports`` by default.

Usage:
    python scripts/smoke_delivery_tools.py            # offline-safe subset + science
    python scripts/smoke_delivery_tools.py --network  # also hit network tools
    python scripts/smoke_delivery_tools.py --af3       # explicitly run AF3 (minutes, GPU)
    python scripts/smoke_delivery_tools.py --report /tmp/delivery-smoke.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.backends.delivery.client import DEFAULT_CONDA_ENV, SCRIPT_MAP  # noqa: E402
from app.backends.delivery.env import apply_delivery_env  # noqa: E402
from app.core.paths import REPORTS, ensure_artifact_dirs  # noqa: E402
from app.dotenv_util import load_dotenv  # noqa: E402

RNA = (
    "ACGUACGUACGUCUCUCUCUUUCUCUCUUCUCACGUACGUACGUACGUCUCUCUCUUUCUCUCUUCUC"
    "ACGUACGUACGUCUCUCUCUUUCUCUCUUCUC"
)
TARGET_ALIAS = "PTBP1"
TARGET_UNIPROT = "P26599"
DEFAULT_REPORT = REPORTS / "delivery_tools_smoke_report.json"
MAPPING_PATH = ROOT / "app" / "backends" / "delivery" / "mapping.yaml"

STATUS_PASSED = "passed"
STATUS_CACHED = "passed_cached"
STATUS_SKIPPED = "skipped_external"
STATUS_FAILED = "failed"

# Requirements not expressible in registry.json. Registry flags, schemas, and
# conda routing are merged into every report row.
SCENARIO_META: dict[str, dict[str, Any]] = {
    "structure_fetch": {
        "prerequisites": ["UniProt accession", "AFDB cache or network"],
        "fallback": "structure axis unavailable; do not score as zero",
    },
    "structure_predict_af3": {
        "prerequisites": ["protein sequence", "AF3 runtime/assets", "GPU", "MSA network/cache"],
        "fallback": "reuse successful AF3 status/artifact, otherwise prefer AFDB",
    },
    "colabfold_msa": {
        "prerequisites": ["protein sequence", "ColabFold API"],
        "fallback": "cached MSA or skip AF3",
    },
    "structure_consensus": {
        "prerequisites": ["UniProt accession", "AFDB/AF3 structure source"],
        "fallback": "use whichever real structure source is available",
    },
    "struct_similarity_foldseek": {
        "prerequisites": ["query PDB", "Foldseek binary/database"],
        "fallback": "sequence/domain axes; structure unavailable is not similarity zero",
    },
    "struct_align_usalign": {
        "prerequisites": ["query PDB", "target structures", "USalign or Foldseek"],
        "fallback": "keep unrefined Foldseek hits",
    },
    "pymol_util": {
        "prerequisites": ["query PDB"],
        "fallback": "sequence from catalogue",
    },
    "protein_seq_similarity": {
        "prerequisites": ["protein sequence", "MMseqs sequence database"],
        "fallback": "ESM/domain similarity",
    },
    "esm_embed": {
        "prerequisites": ["protein sequence", "encoder weights/runtime"],
        "fallback": "MMseqs/domain similarity",
    },
    "esm_similarity": {
        "prerequisites": ["protein sequence", "encoder weights", "embedding bank"],
        "fallback": "MMseqs/domain similarity",
    },
    "domain_architecture": {
        "prerequisites": ["RBP alias/accession or protein domains"],
        "fallback": "network InterProScan when explicitly enabled",
    },
    "rna_blastn": {
        "prerequisites": ["RNA sequence", "MMseqs peaks database"],
        "fallback": "RNA axis unavailable; configured fusion weight must remain zero",
    },
    "uniprot_annotation": {
        "prerequisites": ["UniProt accession", "UniProt network"],
        "fallback": "offline GO/Pfam registry lookup",
    },
    "pdb_metadata": {
        "prerequisites": ["UniProt accession", "PDB network"],
        "fallback": "omit PDB metadata with caveat",
    },
    "literature_retrieval": {
        "prerequisites": ["RBP name", "literature service network"],
        "fallback": "omit literature evidence with caveat",
    },
    "go_pfam_lookup": {
        "prerequisites": ["UniProt accession", "local registry"],
        "fallback": "network UniProt annotation",
    },
    "function_category": {
        "prerequisites": ["RBP alias/accession", "local registry"],
        "fallback": "unknown category",
    },
    "rhobind_predict": {
        "prerequisites": ["RNA sequence", "known donor head", "RhoBind release/runtime"],
        "fallback": "abstain; never fabricate a binding probability",
    },
    "rna_preprocess": {
        "prerequisites": ["RNA sequence"],
        "fallback": "reject invalid RNA",
    },
    "similarity_weighted_vote": {
        "prerequisites": ["real donor predictions", "real similarity hits"],
        "fallback": "abstain when no eligible donors",
    },
    "transfer_prior_lookup": {
        "prerequisites": ["target/donor aliases", "transfer matrix"],
        "fallback": "neutral/missing prior explicitly reported",
    },
    "confidence_abstain": {
        "prerequisites": ["real similarity hits"],
        "fallback": "abstain",
    },
    "donor_quality_prior": {
        "prerequisites": ["donor aliases", "validation metrics registry"],
        "fallback": "missing donor quality explicitly reported",
    },
    "resolve_rbp": {
        "prerequisites": ["free-text RBP query", "local registry"],
        "fallback": "unseen target contract",
    },
}


def _seq() -> str:
    from nanobot.agent.tools.rbp.common import load_catalogue_sequence

    return load_catalogue_sequence(TARGET_ALIAS) or ""


def _ok(out: dict) -> bool:
    if not isinstance(out, dict):
        return False
    if out.get("ok") is False or out.get("error"):
        return False
    if out.get("status") == "error":
        return False
    return True


def _mapping_entries(value: Any) -> list[dict[str, str]]:
    """Collect nested ``registry_name`` declarations from mapping.yaml."""
    entries: list[dict[str, str]] = []
    if isinstance(value, dict):
        registry_name = value.get("registry_name")
        if registry_name:
            entries.append(
                {
                    "registry_name": str(registry_name),
                    "script": str(value.get("script") or ""),
                }
            )
        for child in value.values():
            entries.extend(_mapping_entries(child))
    elif isinstance(value, list):
        for child in value:
            entries.extend(_mapping_entries(child))
    return entries


def build_scenario_matrix(
    registry: dict[str, Any],
    *,
    mapping_path: Path = MAPPING_PATH,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build one scenario per registry tool and audit bridge/mapping coverage."""
    tools = [
        dict(tool)
        for tool in registry.get("tools", [])
        if isinstance(tool, dict) and tool.get("name")
    ]
    registry_names = [str(tool["name"]) for tool in tools]
    registry_set = set(registry_names)

    mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    mapping_rows = _mapping_entries(mapping)
    mapping_names = {row["registry_name"] for row in mapping_rows}
    mapping_scripts = {
        row["registry_name"]: row["script"]
        for row in mapping_rows
        if row.get("script")
    }
    script_names = set(SCRIPT_MAP)
    script_mismatches = {
        name: {"script_map": SCRIPT_MAP[name], "mapping": mapping_scripts[name]}
        for name in sorted(registry_set & set(mapping_scripts) & script_names)
        if SCRIPT_MAP[name] != mapping_scripts[name]
    }

    matrix: list[dict[str, Any]] = []
    for meta in tools:
        name = str(meta["name"])
        scenario = SCENARIO_META.get(name, {})
        prerequisites = list(scenario.get("prerequisites") or [])
        if meta.get("network") and not any(
            "network" in item.lower() for item in prerequisites
        ):
            prerequisites.append("network")
        if meta.get("gpu") and not any("gpu" in item.lower() for item in prerequisites):
            prerequisites.append("GPU")
        matrix.append(
            {
                "name": name,
                "category": meta.get("category"),
                "registry_status": meta.get("status"),
                "metadata": {
                    "network": bool(meta.get("network")),
                    "gpu": bool(meta.get("gpu")),
                    "runtime": meta.get("est_runtime"),
                    "conda": DEFAULT_CONDA_ENV.get(name),
                    "input": dict(meta.get("input_schema") or {}),
                    "output": dict(meta.get("output_schema") or {}),
                    "prerequisites": prerequisites,
                    "fallback": scenario.get(
                        "fallback",
                        "return a structured error; never synthesize science output",
                    ),
                },
                "scenario_defined": name in SCENARIO_META,
            }
        )

    duplicate_registry_names = sorted(
        {name for name in registry_names if registry_names.count(name) > 1}
    )
    coverage: dict[str, Any] = {
        "ok": False,
        "registry_total": len(registry_names),
        "bridge_total": len(script_names),
        "mapping_registry_total": len(mapping_names),
        "missing_bridge": sorted(registry_set - script_names),
        "extra_bridge": sorted(script_names - registry_set),
        "missing_mapping": sorted(registry_set - mapping_names),
        "mapping_script_mismatches": script_mismatches,
        "missing_scenarios": sorted(registry_set - set(SCENARIO_META)),
        "duplicate_registry_names": duplicate_registry_names,
    }
    coverage["ok"] = not any(
        coverage[key]
        for key in (
            "missing_bridge",
            "extra_bridge",
            "missing_mapping",
            "mapping_script_mismatches",
            "missing_scenarios",
            "duplicate_registry_names",
        )
    )
    return matrix, coverage


def _payload(name: str, *, seq: str, pdb_path: str, device: str) -> dict[str, Any]:
    payloads: dict[str, dict[str, Any]] = {
        "resolve_rbp": {"query": TARGET_ALIAS},
        "rna_preprocess": {"rna": RNA, "window": 128, "stride": 64},
        "rhobind_predict": {
            "rna": RNA,
            "rbps": [TARGET_ALIAS],
            "cohort": "K562",
            "device": device,
        },
        "protein_seq_similarity": {"sequence": seq, "top_k": 5},
        "esm_similarity": {
            "sequence": seq,
            "encoder": "esmc",
            "top_k": 5,
            "device": device,
            "uniprot": TARGET_UNIPROT,
        },
        "esm_embed": {"sequence": seq, "encoder": "esmc", "device": device},
        "domain_architecture": {"alias": TARGET_ALIAS, "top_k": 5},
        "rna_blastn": {"rna": RNA, "top_k": 5},
        "go_pfam_lookup": {"uniprot": TARGET_UNIPROT},
        "function_category": {"alias": TARGET_ALIAS},
        "structure_fetch": {"uniprot": TARGET_UNIPROT},
        "struct_similarity_foldseek": {"pdb_path": pdb_path, "top_k": 5},
        "struct_align_usalign": {
            "query_pdb": pdb_path,
            "targets": ["MATR3", "HNRNPC"],
        },
        "pymol_util": {"pdb_path": pdb_path, "op": "seq"},
        "similarity_weighted_vote": {
            "predictions": [{"donor": "FMR1", "prob": 0.8}],
            "hits": [{"alias": "FMR1", "score": 0.9}],
        },
        "transfer_prior_lookup": {
            "target": "FXR2",
            "donors": ["FMR1", "FXR1"],
        },
        "confidence_abstain": {
            "hits": [
                {"alias": "FMR1", "score": 0.91, "metric": "esmc_cosine"}
            ]
        },
        "donor_quality_prior": {
            "donors": ["FMR1", "FXR1"],
            "cohort": "K562",
        },
        "structure_consensus": {
            "uniprot": TARGET_UNIPROT,
            "sequence": seq,
            "alias": TARGET_ALIAS,
            "run_af3": False,
        },
        "uniprot_annotation": {"uniprot": TARGET_UNIPROT},
        "pdb_metadata": {"uniprot": TARGET_UNIPROT},
        "literature_retrieval": {"name": TARGET_ALIAS, "max_results": 3},
        "colabfold_msa": {"sequence": seq[:200]},
        "structure_predict_af3": {
            "sequence": seq[:200],
            "name": f"{TARGET_ALIAS.lower()}_delivery_smoke",
        },
    }
    return dict(payloads.get(name) or {})


def _af3_cached_result() -> dict[str, Any] | None:
    """Return a validated prior AF3 status/artifact without launching inference."""
    from app.core.capability_matrix import read_af3_status

    status = read_af3_status()
    if (status.get("state") or "").lower() != "ok":
        return None
    note = status.get("note") or ""
    match = re.search(r"(?:^|;\s*)output=([^;]+)", note)
    artifact: Path | None = None
    if match:
        artifact = Path(match.group(1).strip()).expanduser()
        if not artifact.is_absolute():
            artifact = ROOT / artifact
        if not artifact.is_file():
            return None
    return {
        "source": "af3_status",
        "status_path": str(ROOT / ".af3_status"),
        "artifact": str(artifact) if artifact else None,
        "recorded_at": status.get("ts"),
        "note": note,
        "gpu": status.get("gpu"),
    }


def _summarize_output(out: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "ok": _ok(out),
        "keys": [str(key) for key in out if not str(key).startswith("_")],
        "latency_ms": out.get("_latency_ms"),
        "invocation": out.get("_invocation"),
        "script": out.get("_script"),
    }
    for key in (
        "error",
        "reason",
        "source",
        "method",
        "matched",
        "in_panel",
        "n_windows",
    ):
        if key in out:
            summary[key] = out[key]
    for key in ("hits", "papers", "entries", "predictions", "windows"):
        if isinstance(out.get(key), list):
            summary[f"n_{key}"] = len(out[key])
    return summary


def _external_precheck(
    name: str,
    *,
    requires_network: bool,
    network: bool,
    run_af3: bool,
    seq: str,
    pdb_path: str,
) -> str | None:
    if name == "structure_predict_af3":
        if run_af3:
            return None
        return "AF3 rerun not requested and no validated successful artifact/status"
    if name in {
        "struct_similarity_foldseek",
        "struct_align_usalign",
        "pymol_util",
    } and not pdb_path:
        return (
            "no query PDB available; enable --network for structure_fetch "
            "or provide AFDB cache"
        )
    if name in {
        "protein_seq_similarity",
        "esm_embed",
        "esm_similarity",
        "structure_consensus",
        "colabfold_msa",
    } and not seq:
        return f"catalogue protein sequence unavailable for {TARGET_ALIAS}"
    if requires_network and not network:
        return "network execution disabled (pass --network)"
    return None


def run_scenario_matrix(
    matrix: list[dict[str, Any]],
    *,
    client: Any,
    af3_client: Any,
    device: str,
    network: bool,
    run_af3: bool,
    sequence: str | None = None,
    cached_af3: Callable[[], dict[str, Any] | None] = _af3_cached_result,
) -> list[dict[str, Any]]:
    """Execute registry scenarios and return JSON-serializable result rows."""
    seq = _seq() if sequence is None else sequence
    pdb_path = ""
    results: list[dict[str, Any]] = []

    for spec in matrix:
        name = str(spec["name"])
        row = dict(spec)
        row["payload"] = _payload(
            name, seq=seq, pdb_path=pdb_path, device=device
        )

        if not spec.get("scenario_defined"):
            row.update(
                status=STATUS_FAILED,
                detail="registry tool has no smoke scenario",
            )
            results.append(row)
            continue

        if name == "structure_predict_af3" and not run_af3:
            cached = cached_af3()
            if cached is not None:
                row.update(
                    status=STATUS_CACHED,
                    detail="consumed prior successful AF3 status/artifact",
                    observed=cached,
                )
                results.append(row)
                continue

        blocker = _external_precheck(
            name,
            requires_network=bool((spec.get("metadata") or {}).get("network")),
            network=network,
            run_af3=run_af3,
            seq=seq,
            pdb_path=pdb_path,
        )
        if blocker:
            row.update(
                status=STATUS_SKIPPED,
                detail=blocker,
                blocker="prerequisite",
            )
            results.append(row)
            continue

        try:
            out = (
                af3_client if name == "structure_predict_af3" else client
            ).call(name, row["payload"])
        except Exception as exc:  # noqa: BLE001
            row.update(
                status=STATUS_FAILED,
                detail=f"{type(exc).__name__}: {exc}"[:500],
            )
            results.append(row)
            continue

        if not isinstance(out, dict):
            row.update(
                status=STATUS_FAILED,
                detail=f"bridge returned {type(out).__name__}",
            )
        elif out.get("skipped") or out.get("_skipped") or out.get("_skip"):
            row.update(
                status=STATUS_SKIPPED,
                detail=str(
                    out.get("error")
                    or out.get("reason")
                    or "bridge prerequisite skip"
                )[:500],
                blocker="bridge",
                observed=_summarize_output(out),
            )
        elif _ok(out):
            row.update(
                status=STATUS_PASSED,
                detail="real bridge scenario completed",
                observed=_summarize_output(out),
            )
            if name == "structure_fetch":
                pdb_path = str(out.get("pdb_path") or out.get("path") or "")
        else:
            row.update(
                status=STATUS_FAILED,
                detail=str(
                    out.get("error") or out.get("reason") or "not ok"
                )[:500],
                observed=_summarize_output(out),
            )
        results.append(row)
    return results


def build_report(
    *,
    registry: dict[str, Any],
    coverage: dict[str, Any],
    results: list[dict[str, Any]],
    options: dict[str, Any],
) -> dict[str, Any]:
    counts = {
        status: sum(1 for row in results if row.get("status") == status)
        for status in (
            STATUS_PASSED,
            STATUS_CACHED,
            STATUS_SKIPPED,
            STATUS_FAILED,
        )
    }
    counts["total"] = len(results)
    failed = bool(counts[STATUS_FAILED] or not coverage.get("ok"))
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "fail" if failed else "pass",
        "options": options,
        "registry": {
            "schema_version": registry.get("schema_version"),
            "description": registry.get("description"),
            "total": len(registry.get("tools") or []),
        },
        "coverage": coverage,
        "summary": counts,
        "tools": results,
    }


def _resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    try:
        import torch  # type: ignore

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--network", action="store_true", help="also call network tools")
    ap.add_argument(
        "--af3",
        action="store_true",
        help="run AF3 instead of consuming a successful prior status/artifact",
    )
    ap.add_argument("--device", default="auto")
    ap.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help=f"JSON report path (default: {DEFAULT_REPORT})",
    )
    args = ap.parse_args(argv)

    load_dotenv()
    apply_delivery_env()
    from app.backends.delivery.client import DeliveryToolClient, load_delivery_registry

    device = _resolve_device(args.device)
    registry = load_delivery_registry()
    matrix, coverage = build_scenario_matrix(registry)
    cli = DeliveryToolClient(
        offline=not args.network,
        device=device,
        use_conda=True,
    )
    # --af3 is an explicit external-call opt-in even without --network.
    af3_cli = (
        DeliveryToolClient(offline=False, device=device, use_conda=True)
        if args.af3 and not args.network
        else cli
    )
    results = run_scenario_matrix(
        matrix,
        client=cli,
        af3_client=af3_cli,
        device=device,
        network=args.network,
        run_af3=args.af3,
    )
    report = build_report(
        registry=registry,
        coverage=coverage,
        results=results,
        options={
            "network": args.network,
            "af3": args.af3,
            "device": device,
            "delivery_root": os.environ.get("DELIVERY_ROOT"),
        },
    )

    ensure_artifact_dirs()
    report_path = args.report.expanduser()
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    width = max((len(str(row["name"])) for row in results), default=1)
    labels = {
        STATUS_PASSED: "OK",
        STATUS_CACHED: "CACHE",
        STATUS_SKIPPED: "SKIP",
        STATUS_FAILED: "FAIL",
    }
    print(
        f"registry={len(matrix)} coverage={'OK' if coverage['ok'] else 'FAIL'} "
        f"device={device}"
    )
    for row in results:
        print(
            f"  {row['name']:<{width}}  {labels[row['status']]:<5}  "
            f"{str(row.get('detail') or '')[:160]}"
        )
    summary = report["summary"]
    print(
        "\nsummary: "
        f"{summary[STATUS_PASSED]} OK · {summary[STATUS_CACHED]} CACHE · "
        f"{summary[STATUS_SKIPPED]} EXTERNAL SKIP · "
        f"{summary[STATUS_FAILED]} FAIL (of {summary['total']} tools)"
    )
    print(f"report: {report_path}")
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
