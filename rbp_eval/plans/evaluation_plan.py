# -*- coding: utf-8 -*-
"""Proposal Evaluation Plan harness (held-out LOO + ablations + metrics).

Protocol tiers
--------------
**Light (default, 2 GiB-safe):** hide own head → retrieve donors (domain / optional
seq) → look up measured transfer AUPRC/AUROC from delivery CSVs. Reports
policy-level AUPRC/AUROC and ablation sweeps. Does **not** re-run RhoBind.

**Heavy (opt-in ``--heavy``):** requires ≥8 GiB + rhobind; subsample labeled FASTA
→ predict → (p_hat, y) → instance AUROC/AUPRC/ECE. Skipped when unavailable.

Qualitative: writes a 30-row faithfulness rating sheet (manual).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.paths import REPORTS_CSV, REPORTS_JSON, REPORTS_MD, TRACES, ensure_artifact_dirs
from rbp_eval.loo.loo_eval import (
    DEFAULT_VAL,
    _fetch_domain_hits,
    _fetch_seq_hits,
    _mean,
    load_loo_summary,
    load_transfer_matrix,
    _paths,
)
from rbp_eval.scoring.metrics import (
    average_precision,
    binary_from_four_level,
    expected_calibration_error,
    metrics_from_pairs,
    roc_auc,
)

DEFAULT_OUT = REPORTS_JSON / "evaluation_plan_report.json"
DEFAULT_MD = REPORTS_MD / "evaluation_plan_report.md"
DEFAULT_QUAL = REPORTS_CSV / "faithfulness_rating_sheet.csv"
N_CAND_GRID = (1, 3, 5, 10)

# Acceptance strata tags (heuristic; used in reports / gate docs, not hard CI fail).
STRATA_TAGS = (
    "own_head",
    "in_panel_transfer",
    "dark_protein",
    "cross_kingdom",
)


def assign_strata(
    *,
    in_panel: Optional[bool] = None,
    mode: Optional[str] = None,
    kingdom: Optional[str] = None,
    taxonomy_hint: Optional[str] = None,
    query_note: Optional[str] = None,
    prior_missing: Optional[bool] = None,
    dark: Optional[bool] = None,
) -> list[str]:
    """Heuristic strata tags for acceptance / faithfulness fixtures.

    Rules (countable; prefer explicit flags when present):
    - ``own_head`` — catalogue head used directly (``in_panel`` / mode own-head)
    - ``in_panel_transfer`` — held-out / transfer among panel RBPs
    - ``dark_protein`` — novel UniProt / prior missing / explicit dark flag
    - ``cross_kingdom`` — taxonomy / kingdom mismatch vs human CLIP panel
    """
    tags: list[str] = []
    blob = " ".join(
        str(x or "") for x in (mode, kingdom, taxonomy_hint, query_note)
    ).lower()
    if dark is True or "dark" in blob or prior_missing is True:
        tags.append("dark_protein")
    if (
        "cross_kingdom" in blob
        or "cross-kingdom" in blob
        or (kingdom and kingdom.lower() not in ("", "human", "homo", "h. sapiens", "metazoa"))
    ):
        if any(k in (kingdom or "").lower() for k in ("bacteria", "plant", "fungi", "virus", "yeast", "arabidopsis")):
            tags.append("cross_kingdom")
        elif "cross" in blob and "kingdom" in blob:
            tags.append("cross_kingdom")
    if in_panel is True or (mode or "").lower() in ("own_head", "own-head", "in_catalogue"):
        tags.append("own_head")
    elif in_panel is False and "dark_protein" not in tags:
        tags.append("in_panel_transfer")
    elif (mode or "").lower() in ("transfer", "loo", "held_out", "held-out"):
        tags.append("in_panel_transfer")
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t in STRATA_TAGS and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def strata_bucket_schema() -> dict[str, Any]:
    """Static schema block embedded in evaluation_plan reports."""
    return {
        "tags": list(STRATA_TAGS),
        "definitions": {
            "own_head": "Query RBP is in-panel; predict with own RhoBind head.",
            "in_panel_transfer": (
                "Held-out or unseen-vs-panel transfer among human CLIP catalogue RBPs."
            ),
            "dark_protein": (
                "Novel / poorly annotated protein; LOO prior missing or no close donors."
            ),
            "cross_kingdom": (
                "Query taxonomy outside human/metazoa training distribution of donors."
            ),
        },
        "acceptance_note": (
            "Use strata in faithfulness / chat fixtures. Dark / cross-kingdom "
            "should force confidence=low (≥2 Stage-3 checklist fails). "
            "Not a hard CI fail — see docs/工程指南.zh.md §6."
        ),
    }


# ---------------------------------------------------------------------------
# Metrics (instance-level when (score, y) available) — shared via rbp_eval.scoring.metrics
# ---------------------------------------------------------------------------

# Canonical implementations live in :mod:`rbp_eval.scoring.metrics` (B4 unification).
# This module imports: roc_auc, average_precision, expected_calibration_error,
# binary_from_four_level, metrics_from_pairs — and re-exports them here for
# backwards-compatible callers (``from rbp_eval.plans.evaluation_plan import ...``).
_roc_auc = roc_auc
_average_precision = average_precision



# ---------------------------------------------------------------------------
# Transfer matrix helpers (include AUROC)
# ---------------------------------------------------------------------------

def load_transfer_matrix_full(path: Path) -> dict[tuple[str, str], dict[str, float]]:
    m: dict[tuple[str, str], dict[str, float]] = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m[(r["held_rbp"], r["foreign_rbp"])] = {
                "auprc": float(r["auprc"]),
                "auroc": float(r["auroc"]),
            }
    return m


def policy_metrics(
    held: str,
    donors: list[str],
    matrix: dict[tuple[str, str], dict[str, float]],
) -> dict[str, Any]:
    auprcs = []
    aurocs = []
    for d in donors:
        cell = matrix.get((held, d))
        if not cell:
            continue
        auprcs.append(cell["auprc"])
        aurocs.append(cell["auroc"])
    return {
        "donors": donors,
        "n_measured": len(auprcs),
        "policy_best_auprc": max(auprcs) if auprcs else None,
        "policy_mean_auprc": (sum(auprcs) / len(auprcs)) if auprcs else None,
        "policy_best_auroc": max(aurocs) if aurocs else None,
        "policy_mean_auroc": (sum(aurocs) / len(aurocs)) if aurocs else None,
    }


def _alias_lookup_from_hits(hit_lists: list[list[dict[str, Any]]]) -> dict[str, str]:
    """Map uniprot / rbp_id → gene alias for transfer-matrix keys."""
    m: dict[str, str] = {}
    for hits in hit_lists:
        for h in hits or []:
            alias = h.get("alias")
            if not alias:
                continue
            for key in (h.get("uniprot"), h.get("rbp_id"), alias):
                if key:
                    m[str(key)] = str(alias)
    return m


def select_donors(
    held: str,
    hit_lists: list[list[dict[str, Any]]],
    *,
    n_cand: int,
    mode: str = "fuse",
) -> list[str]:
    """mode: fuse (weighted fuse_rbp_hits) | mean (fusion.fuse_proxy_candidates).

    Always returns gene aliases (transfer CSV keys), never UniProt-only ids.
    """
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits
    from rbp_eval.scoring.fuse_hits import fuse_proxy_candidates

    id2alias = _alias_lookup_from_hits(hit_lists)

    if mode == "mean":
        views: dict[str, list] = {}
        for i, hits in enumerate(hit_lists):
            views[f"v{i}"] = hits
        fused = fuse_proxy_candidates(views, n_cand=max(n_cand * 3, n_cand), tau_drop=0.0)
        out: list[str] = []
        seen: set[str] = set()
        for x in fused:
            rid = str(x.get("rbp_id") or "")
            a = id2alias.get(rid, rid)
            if not a or a == held or a in seen:
                continue
            seen.add(a)
            out.append(a)
            if len(out) >= n_cand:
                break
        return out

    donors = fuse_rbp_hits(
        hit_lists,
        top_k=n_cand,
        exclude_aliases={held},
        use_rank_normalize=True,
        tau_drop=0.30,
    )
    return [d["alias"] for d in donors if d.get("alias")]


# ---------------------------------------------------------------------------
# Ablation runner (light)
# ---------------------------------------------------------------------------

def run_light_evaluation_plan(
    *,
    n_cand_grid: tuple[int, ...] = N_CAND_GRID,
    try_seq: bool = False,
    offline: bool = True,
) -> dict[str, Any]:
    from app.backends.delivery.client import DeliveryToolClient

    ensure_artifact_dirs()
    summary_p, metrics_p = _paths()
    if not summary_p.is_file() or not metrics_p.is_file():
        raise FileNotFoundError(f"LOO CSVs missing: {summary_p}, {metrics_p}")

    summary = load_loo_summary(summary_p)
    matrix = load_transfer_matrix_full(metrics_p)
    held_list = [h for h in DEFAULT_VAL if h in summary]
    seen_note = (
        "Seen = K562 panel heads used as donors (≈118); "
        "Held-out = 10 LOO medoids (DEFAULT_VAL)."
    )

    cli = DeliveryToolClient(offline=offline, device="cpu", use_conda=bool(try_seq))

    # Cache hits per held × view
    cache: dict[str, dict[str, list]] = {}
    fetch_errors: dict[str, dict[str, str]] = {}
    for held in held_list:
        cache[held] = {}
        fetch_errors[held] = {}
        dom, err = _fetch_domain_hits(cli, held, top_k=20)
        cache[held]["domain"] = dom
        if err:
            fetch_errors[held]["domain"] = err
        if try_seq:
            seq, err2 = _fetch_seq_hits(cli, held, top_k=20)
            cache[held]["seq"] = seq
            if err2:
                fetch_errors[held]["seq"] = err2

    ablations: dict[str, Any] = {}

    def _run_ablation(name: str, views: list[str], fuse_mode: str) -> dict[str, Any]:
        by_k: dict[str, Any] = {}
        for k in n_cand_grid:
            rows = []
            for held in held_list:
                lists = [cache[held].get(v) or [] for v in views]
                lists = [x for x in lists if x]
                donors = select_donors(held, lists, n_cand=k, mode=fuse_mode) if lists else []
                pm = policy_metrics(held, donors, matrix)
                own = float(summary[held].get("own_full_auprc") or 0)
                best_f = float(summary[held].get("best_foreign_auprc") or 0)
                row = {
                    "held_rbp": held,
                    "views": views,
                    "fuse_mode": fuse_mode,
                    "n_cand": k,
                    **pm,
                    "own_full_auprc": own,
                    "best_foreign_auprc": best_f,
                    "gap_to_own": (
                        (own - pm["policy_best_auprc"])
                        if pm["policy_best_auprc"] is not None
                        else None
                    ),
                }
                rows.append(row)
            ok = [r for r in rows if r["policy_best_auprc"] is not None]
            by_k[str(k)] = {
                "n_ok": len(ok),
                "mean_policy_best_auprc": _mean([r["policy_best_auprc"] for r in ok]),
                "mean_policy_mean_auprc": _mean([r["policy_mean_auprc"] for r in ok]),
                "mean_policy_best_auroc": _mean([r["policy_best_auroc"] for r in ok]),
                "mean_gap_to_own": _mean([r["gap_to_own"] for r in ok]),
                "mean_own_full_auprc": _mean([r["own_full_auprc"] for r in rows]),
                "rows": rows,
            }
        return {"views": views, "fuse_mode": fuse_mode, "by_n_cand": by_k}

    # (i) single-view + multi-view
    ablations["domain_only_fuse"] = _run_ablation("domain", ["domain"], "fuse")
    ablations["domain_only_mean"] = _run_ablation("domain_mean", ["domain"], "mean")
    if try_seq and any(cache[h].get("seq") for h in held_list):
        ablations["seq_only_fuse"] = _run_ablation("seq", ["seq"], "fuse")
        ablations["domain_plus_seq_fuse"] = _run_ablation(
            "dom+seq", ["domain", "seq"], "fuse"
        )
    else:
        ablations["seq_only_fuse"] = {
            "status": "skipped",
            "reason": "seq view not fetched (pass --with-seq; needs protein_embed + RAM)",
        }
        ablations["structure_only"] = {
            "status": "skipped",
            "reason": "structure view deferred (foldseek/AFDB; not in light default)",
        }
        ablations["function_only"] = {
            "status": "skipped",
            "reason": (
                "function similarity not a ranked RbpHit bank offline; "
                "use get_func_annotation qualitatively"
            ),
        }

    # (ii) fixed-weight (fuse) vs mean-view — already in domain_only_fuse vs domain_only_mean
    # (iii) Stage 3 LLM-explanation ablation (A4): the light protocol is numeric-only,
    # but when (p_hat, y) pairs are available the harness can compare the full agent
    # path (with Stage-3 LLM explanation) vs the de-LLM-explanation path (verdict from
    # similarity_weighted_vote.score alone) using the SAME metrics. The no-LLM verdict
    # is the weighted-vote score; the full-LLM verdict is supplied via --labels-llm.
    stage3 = {
        "mode": "numeric_only",
        "note": (
            "Light Evaluation Plan uses measured LOO transfer AUPRC/AUROC "
            "(no Stage-3 LLM explanation). LLM Stage-3 is agent-path only."
        ),
        "ablation_no_llm_explanation": {
            "status": "skipped",
            "reason": (
                "Needs (p_hat, y) pairs: pass --labels (no-LLM verdicts from "
                "similarity_weighted_vote.score) and optionally --labels-llm "
                "(full-path verdicts with Stage-3 LLM explanation)."
            ),
            "no_llm": None,
            "full_llm": None,
        },
    }

    # Primary metrics: transfer-level summary from default ablation (domain, n_cand=5)
    primary_transfer = ablations["domain_only_fuse"]["by_n_cand"].get("5", {})

    # Instance-level primary (need pairs) — try load optional labels file later
    primary_instance = {
        "status": "skipped",
        "reason": (
            "No (p_hat, y) pairs under 2 GiB (RhoBind OOM). "
            "Pass --labels PATH with [{p_hat,y},…] or --heavy when RAM≥8 GiB."
        ),
        "auroc": None,
        "auprc": None,
        "ece": None,
    }

    # Tag held-out LOO medoids as in-panel transfer strata (all are catalogue RBPs).
    held_strata = {
        h: assign_strata(in_panel=False, mode="held_out") for h in held_list
    }

    return {
        "schema": "evaluation_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tier": "light",
        "held_out_split": {
            "held_out_rbps": held_list,
            "n_held": len(held_list),
            "seen": "K562 panel donor heads (~118)",
            "note": seen_note,
        },
        "strata": {
            **strata_bucket_schema(),
            "held_out_tags": held_strata,
            "example_fixtures": {
                "own_head": assign_strata(in_panel=True, mode="own_head"),
                "in_panel_transfer": assign_strata(in_panel=False, mode="transfer"),
                "dark_protein": assign_strata(
                    in_panel=False, prior_missing=True, dark=True
                ),
                "cross_kingdom": assign_strata(
                    in_panel=False,
                    kingdom="bacteria",
                    taxonomy_hint="cross_kingdom",
                ),
            },
        },
        "primary_metrics": {
            "transfer_level": {
                "description": (
                    "Policy donor → held transfer AUPRC/AUROC from "
                    "loo_transfer_metrics.csv (scientific LOO protocol)."
                ),
                "n_cand": 5,
                "view": "domain",
                "mean_policy_best_auprc": primary_transfer.get("mean_policy_best_auprc"),
                "mean_policy_best_auroc": primary_transfer.get("mean_policy_best_auroc"),
                "mean_own_full_auprc": primary_transfer.get("mean_own_full_auprc"),
                "mean_gap_to_own": primary_transfer.get("mean_gap_to_own"),
                "n_ok": primary_transfer.get("n_ok"),
            },
            "instance_level": primary_instance,
            "four_level_collapse": "Strong|Likely→1, Unlikely|No→0 (when labels present)",
        },
        "ablations": ablations,
        "stage3": stage3,
        "fetch_errors": fetch_errors,
        "gaps": [
            "structure-only / function-only retrieval not run in light default",
            "LLM-fused similarity not measured (no LLM in light loop); compare fuse vs mean",
            "instance AUROC/AUPRC/ECE require (p_hat,y) — use --labels or --heavy",
            "qualitative faithfulness is manual (see faithfulness_rating_sheet.csv)",
        ],
    }


def attach_instance_metrics(report: dict[str, Any], labels_path: Path) -> dict[str, Any]:
    raw = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        pairs = raw.get("scored_labels") or raw.get("pairs") or []
    else:
        pairs = raw
    report["primary_metrics"]["instance_level"] = metrics_from_pairs(list(pairs))
    report["primary_metrics"]["instance_level"]["source"] = str(labels_path)
    return report


def write_faithfulness_sheet(
    path: Path,
    *,
    n: int = 30,
    traces_dir: Optional[Path] = None,
) -> Path:
    """Create/overwrite CSV for manual faithfulness rating; prefill from traces if any."""
    ensure_artifact_dirs()
    rows: list[dict[str, str]] = []
    # harvest explanations from recent query_end traces
    harvested: list[dict[str, str]] = []
    tdir = traces_dir or TRACES
    if tdir.is_dir():
        for p in sorted(tdir.glob("*.jsonl"))[-5:]:
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    ev = json.loads(line)
                    if ev.get("type") != "query_end":
                        continue
                    v = ev.get("verdict") or {}
                    expl = (v.get("explanation") or "").strip()
                    if not expl:
                        continue
                    harvested.append(
                        {
                            "trace_file": p.name,
                            "alias": str(ev.get("alias") or (ev.get("query") or {}).get("alias") or ""),
                            "p_hat": str(v.get("p_hat")),
                            "label": str(v.get("label") or ""),
                            "explanation": expl.replace("\n", " ")[:500],
                            "tools_used": ",".join(ev.get("tools_used") or [])[:200],
                        }
                    )
            except (OSError, json.JSONDecodeError):
                continue

    for i in range(n):
        base = harvested[i] if i < len(harvested) else {}
        rows.append(
            {
                "id": str(i + 1),
                "trace_file": base.get("trace_file", ""),
                "alias": base.get("alias", ""),
                "p_hat": base.get("p_hat", ""),
                "label": base.get("label", ""),
                "explanation": base.get("explanation", ""),
                "tools_used": base.get("tools_used", ""),
                "faithfulness_1to5": "",
                "notes": "",
                "rater": "",
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return path


def report_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Evaluation Plan Report",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Tier: **{report.get('tier')}**",
        "",
        "## Held-out split",
        "",
        f"- Held-out (n={report['held_out_split']['n_held']}): "
        + ", ".join(report["held_out_split"]["held_out_rbps"]),
        f"- Seen: {report['held_out_split']['seen']}",
        f"- {report['held_out_split']['note']}",
        "",
        "## Acceptance strata",
        "",
    ]
    strata = report.get("strata") or {}
    if strata:
        lines += [
            f"- Tags: {', '.join(strata.get('tags') or STRATA_TAGS)}",
            f"- Note: {strata.get('acceptance_note') or ''}",
            "",
        ]
    lines += [
        "## Primary metrics",
        "",
        "### Transfer-level (LOO CSV lookup)",
        "",
    ]
    tl = report["primary_metrics"]["transfer_level"]
    lines += [
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| mean policy best AUPRC (domain, N=5) | {tl.get('mean_policy_best_auprc')} |",
        f"| mean policy best AUROC | {tl.get('mean_policy_best_auroc')} |",
        f"| mean own-head AUPRC ceiling | {tl.get('mean_own_full_auprc')} |",
        f"| mean gap to own | {tl.get('mean_gap_to_own')} |",
        f"| n_ok | {tl.get('n_ok')} |",
        "",
        "### Instance-level (ˆp vs y*)",
        "",
    ]
    il = report["primary_metrics"]["instance_level"]
    if il.get("status") == "ok":
        lines += [
            f"| AUROC | {il.get('auroc')} |",
            f"| AUPRC | {il.get('auprc')} |",
            f"| ECE | {il.get('ece')} |",
            f"| n | {il.get('n')} |",
            "",
        ]
    else:
        lines += [f"- Status: `{il.get('status')}` — {il.get('reason')}", ""]

    lines += ["## Ablations (N_cand sweep)", ""]
    for name, abl in (report.get("ablations") or {}).items():
        lines.append(f"### `{name}`")
        if abl.get("status") == "skipped":
            lines += [f"- Skipped: {abl.get('reason')}", ""]
            continue
        lines.append("| N_cand | mean best AUPRC | mean best AUROC | mean gap_to_own | n_ok |")
        lines.append("|--------|-----------------|-----------------|-----------------|------|")
        for k, block in sorted(
            (abl.get("by_n_cand") or {}).items(), key=lambda x: int(x[0])
        ):
            lines.append(
                f"| {k} | {block.get('mean_policy_best_auprc')} | "
                f"{block.get('mean_policy_best_auroc')} | "
                f"{block.get('mean_gap_to_own')} | {block.get('n_ok')} |"
            )
        lines.append("")

    lines += [
        "## Stage 3",
        "",
        f"- {report.get('stage3', {}).get('note')}",
        "",
        "## Gaps",
        "",
    ]
    for g in report.get("gaps") or []:
        lines.append(f"- {g}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Proposal Evaluation Plan (light/heavy)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--md", type=Path, default=DEFAULT_MD)
    ap.add_argument("--qual", type=Path, default=DEFAULT_QUAL)
    ap.add_argument("--with-seq", action="store_true", help="Also fetch ESM view")
    ap.add_argument(
        "--labels",
        type=Path,
        default=None,
        help="JSON list of {p_hat,y} for instance AUROC/AUPRC/ECE",
    )
    ap.add_argument(
        "--labels-llm",
        type=Path,
        default=None,
        help=(
            "JSON list of {p_hat,y} from the FULL agent path (with Stage-3 LLM "
            "explanation). Used by --no-llm-explanation to compare against the "
            "de-LLM verdicts supplied via --labels."
        ),
    )
    ap.add_argument(
        "--no-llm-explanation",
        action="store_true",
        help=(
            "A4: record the Stage-3 de-LLM-explanation ablation. Requires --labels "
            "(no-LLM verdicts from similarity_weighted_vote.score); optionally "
            "--labels-llm (full-path verdicts) for the contrast."
        ),
    )
    ap.add_argument(
        "--heavy",
        action="store_true",
        help="Attempt RhoBind subsample (requires ≥8 GiB); otherwise skip",
    )
    args = ap.parse_args(argv)

    ensure_artifact_dirs()
    report = run_light_evaluation_plan(try_seq=bool(args.with_seq))

    if args.labels and Path(args.labels).is_file():
        attach_instance_metrics(report, Path(args.labels))

    # A4: Stage-3 de-LLM-explanation ablation.
    if args.no_llm_explanation:
        abl = report["stage3"].setdefault("ablation_no_llm_explanation", {})
        if args.labels and Path(args.labels).is_file():
            no_llm_pairs = json.loads(Path(args.labels).read_text(encoding="utf-8"))
            if isinstance(no_llm_pairs, dict):
                no_llm_pairs = no_llm_pairs.get("scored_labels") or no_llm_pairs.get("pairs") or []
            abl["no_llm"] = metrics_from_pairs(list(no_llm_pairs))
            abl["no_llm"]["source"] = str(args.labels)
            if args.labels_llm and Path(args.labels_llm).is_file():
                llm_pairs = json.loads(Path(args.labels_llm).read_text(encoding="utf-8"))
                if isinstance(llm_pairs, dict):
                    llm_pairs = llm_pairs.get("scored_labels") or llm_pairs.get("pairs") or []
                abl["full_llm"] = metrics_from_pairs(list(llm_pairs))
                abl["full_llm"]["source"] = str(args.labels_llm)
                abl["status"] = "ok"
                abl["reason"] = None
                # Delta summary (positive = no-LLM path is better)
                nl = abl["no_llm"]
                fl = abl["full_llm"]
                abl["delta_auroc"] = (
                    (nl.get("auroc") or 0) - (fl.get("auroc") or 0)
                    if nl.get("status") == "ok" and fl.get("status") == "ok"
                    else None
                )
                abl["delta_auprc"] = (
                    (nl.get("auprc") or 0) - (fl.get("auprc") or 0)
                    if nl.get("status") == "ok" and fl.get("status") == "ok"
                    else None
                )
                abl["delta_ece"] = (
                    (nl.get("ece") or 0) - (fl.get("ece") or 0)
                    if nl.get("status") == "ok" and fl.get("status") == "ok"
                    else None
                )
            else:
                abl["status"] = "ok"
                abl["reason"] = "no-LLM path only (no --labels-llm contrast supplied)"
        else:
            abl["status"] = "skipped"
            abl["reason"] = "--no-llm-explanation requires --labels (no-LLM verdicts)"

    if args.heavy:
        report["heavy"] = {
            "status": "skipped",
            "reason": (
                "Heavy force_transfer not auto-run in this harness yet "
                "(use delivery test FASTA + rhobind when RAM≥8 GiB; see E2E P0-1b)."
            ),
        }

    qual = write_faithfulness_sheet(Path(args.qual), n=30)
    report["qualitative"] = {
        "n_requested": 30,
        "sheet": str(qual),
        "instruction": (
            "Manually rate faithfulness_1to5 against tool outputs in the same "
            "trace (resolve/predict/integrate). 5=fully grounded, 1=hallucinated."
        ),
    }

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md = Path(args.md)
    if not md.is_absolute():
        md = ROOT / md
    md.write_text(report_to_markdown(report), encoding="utf-8")

    print("wrote", out)
    print("wrote", md)
    print("wrote", qual)
    tl = report["primary_metrics"]["transfer_level"]
    print(
        "primary transfer: AUPRC*=",
        tl.get("mean_policy_best_auprc"),
        "AUROC*=",
        tl.get("mean_policy_best_auroc"),
        "gap_to_own=",
        tl.get("mean_gap_to_own"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
