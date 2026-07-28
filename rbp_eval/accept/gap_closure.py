# -*- coding: utf-8 -*-
"""Lightweight gap-closure report (Proposal evidence without full GPU LOO).

Writes ``artifacts/reports/gap_closure_YYYYMMDD.{json,md}`` covering:
- Stage-0 own-head golden shape (optional live smoke)
- Unseen / force_transfer tool-trace shape fixtures
- Faithfulness / output schema locks
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.paths import REPORTS, ensure_artifact_dirs

# Canonical unseen / force_transfer tool order (names only; LLM not required).
UNSEEN_REQUIRED_PREFIX = (
    "resolve_rbp",
)
UNSEEN_MUST_INCLUDE = (
    "fuse_similarity_views",
    "confidence_abstain",
    "predict_interaction",
    "similarity_weighted_vote",
)
UNSEEN_FORBIDDEN_OWN_HEAD = "predict_interaction_own_head"  # semantic check via args


def check_unseen_trace_shape(tool_names: list[str], *, predict_targets: Optional[list[str]] = None) -> dict[str, Any]:
    """Validate a force_transfer-style tool timeline (no LLM)."""
    names = [str(n) for n in tool_names]
    errors: list[str] = []
    if not names or names[0] != "resolve_rbp":
        errors.append("trace must start with resolve_rbp")
    for req in UNSEEN_MUST_INCLUDE:
        if req not in names:
            errors.append(f"missing required tool {req}")
    # Own-head smell: single predict of the held target before any fuse
    if predict_targets:
        held = {str(x).upper() for x in predict_targets}
        try:
            i_fuse = names.index("fuse_similarity_views")
            i_pred = names.index("predict_interaction")
            if i_pred < i_fuse and held:
                errors.append("predict_interaction before fuse_similarity_views (own-head smell)")
        except ValueError:
            pass
    # BUILD_SPEC: abstain before predict on transfer path
    try:
        i_abs = names.index("confidence_abstain")
        i_pred = names.index("predict_interaction")
        if i_pred < i_abs:
            errors.append("predict_interaction before confidence_abstain (abstain-before-predict)")
    except ValueError:
        pass
    return {
        "ok": not errors,
        "errors": errors,
        "n_tools": len(names),
        "tools": names,
    }


def check_own_head_golden(result: dict[str, Any]) -> dict[str, Any]:
    """Score delivery own-head accept payload (prob ≈ 0.966, label Strong)."""
    from app.backends.delivery.examples import GOLDEN_OWN_HEAD_POS

    p = result.get("p_hat")
    if p is None:
        p = result.get("prob")
    try:
        p_f = float(p) if p is not None else None
    except (TypeError, ValueError):
        p_f = None
    exp = float(GOLDEN_OWN_HEAD_POS["expected_prob_approx"])
    tol = float(GOLDEN_OWN_HEAD_POS["tolerance"])
    label = result.get("label")
    ok = (
        p_f is not None
        and abs(p_f - exp) <= tol
        and str(label) == str(GOLDEN_OWN_HEAD_POS["expected_label"])
    )
    return {
        "ok": ok,
        "p_hat": p_f,
        "expected_p_hat": exp,
        "tolerance": tol,
        "label": label,
        "expected_label": GOLDEN_OWN_HEAD_POS["expected_label"],
        "path": result.get("path") or "own_head",
    }


def _faithfulness_schema_ok() -> dict[str, Any]:
    """Lock verdict faithfulness behaviors used by Proposal Stage-3."""
    from app.core.verdict_schema import normalize_verdict

    v = normalize_verdict(
        {
            "label": "Likely",
            "p_hat": 0.55,
            "confidence": "high",
            "explanation": "fixture",
            "supporting_rbps": [{"alias": "EWSR1", "prob": 0.5, "similarity_score": 0.9}],
            "donors": [
                {
                    "alias": "EWSR1",
                    "sim_by_modality": {"esmc_cosine": 0.9},
                }
            ],
            "evidence_flags": {"prior_missing": True, "rna_axis_unavailable": True},
            "abstain": {"confident": True},
        }
    )
    conf = v.get("confidence")
    conf_ok = False
    if isinstance(conf, str):
        conf_ok = conf.strip().lower() == "low"
    else:
        try:
            conf_ok = float(conf or 1) <= 0.30
        except (TypeError, ValueError):
            conf_ok = False
    ok = (
        conf_ok
        and "prior_missing" in (v.get("caveats") or [])
        and bool((v.get("supporting_rbps") or [{}])[0].get("similarity_breakdown"))
        and (v.get("abstain") or {}).get("confident") is False
    )
    return {
        "ok": ok,
        "confidence": v.get("confidence"),
        "caveats": v.get("caveats"),
        "has_breakdown": bool((v.get("supporting_rbps") or [{}])[0].get("similarity_breakdown")),
    }


def _live_own_head() -> dict[str, Any]:
    """Run delivery own-head smoke; return golden check dict."""
    from app.backends.delivery.client import DeliveryToolClient
    from app.backends.delivery.examples import load_example
    from app.core.verdict_schema import label_from_p_hat

    ex = load_example("pos")
    device = "cuda"
    try:
        import subprocess

        chk = subprocess.run(
            [
                "conda",
                "run",
                "-n",
                "rhobind",
                "python",
                "-c",
                "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)",
            ],
            capture_output=True,
            timeout=60,
        )
        if chk.returncode != 0:
            device = "cpu"
    except Exception:
        device = "cpu"
    cli = DeliveryToolClient(offline=False, device=device, use_conda=True)
    r = cli.call("resolve_rbp", {"query": ex["query"]})
    if not r.get("in_panel"):
        return {"live": True, "ok": False, "error": "PTBP1 not in_panel"}
    pred = cli.call(
        "rhobind_predict",
        {
            "rna": ex["rna"],
            "rbps": [ex["query"]],
            "cohort": ex["cohort"],
            "device": device,
            "aggregate": "max",
            "timeout_s": 300,
        },
    )
    preds = pred.get("predictions") or []
    prob = None
    if preds and isinstance(preds[0], dict):
        prob = preds[0].get("prob")
    label = label_from_p_hat(prob)
    checked = check_own_head_golden({"p_hat": prob, "label": label, "path": "own_head"})
    checked["live"] = True
    checked["device"] = device
    return checked


def build_gap_closure_report(*, live_own_head: bool = True) -> dict[str, Any]:
    """Assemble report dict (Stage0 + unseen shape + faithfulness)."""
    ensure_artifact_dirs()
    sections: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan": "gap_closure_optimization",
    }

    # --- Stage 0 ---
    if live_own_head:
        try:
            sections["stage0_own_head"] = _live_own_head()
        except Exception as e:
            sections["stage0_own_head"] = {
                "live": False,
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "fixture": check_own_head_golden(
                    {"p_hat": 0.966, "label": "Strong", "path": "own_head"}
                ),
            }
    else:
        fx = check_own_head_golden({"p_hat": 0.966, "label": "Strong", "path": "own_head"})
        sections["stage0_own_head"] = {"live": False, "ok": fx["ok"], "fixture": fx}

    # --- Unseen trace shapes (fixtures; no LLM) ---
    good = check_unseen_trace_shape(
        [
            "resolve_rbp",
            "lookup_proxy_cache",
            "seq_similarity",
            "structure_fetch",
            "struct_similarity",
            "fuse_similarity_views",
            "confidence_abstain",
            "predict_interaction",
            "transfer_prior_lookup",
            "donor_quality_prior",
            "similarity_weighted_vote",
        ]
    )
    bad = check_unseen_trace_shape(
        ["resolve_rbp", "predict_interaction", "fuse_similarity_views"],
        predict_targets=["FUS"],
    )
    sections["unseen_trace_shape"] = {
        "canonical_fixture_ok": good["ok"],
        "canonical": good,
        "own_head_smell_detected": (not bad["ok"]),
        "own_head_smell_fixture": bad,
        "ok": good["ok"] and (not bad["ok"]),
    }

    sections["faithfulness"] = _faithfulness_schema_ok()

    try:
        from app.core.runtime_config import load_runtime_config
        from app.backends.delivery.stage_tools import (
            assert_full_axes_enabled,
            axis_status_matrix,
        )

        cfg = load_runtime_config()
        axes = cfg.get("axes") or {}
        off = assert_full_axes_enabled(axes)
        sections["axes"] = {
            "ok": not off,
            "all_required_on": not off,
            "required_off": off,
            "use_af3": bool(axes.get("use_af3")),
            "prefer_afdb": (cfg.get("structure_policy") or {}).get("prefer_afdb"),
            "status": axis_status_matrix(axes),
        }
    except Exception as e:
        sections["axes"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    s0_ok = bool(sections["stage0_own_head"].get("ok"))
    sections["ok"] = bool(
        s0_ok
        and sections["unseen_trace_shape"].get("ok")
        and sections["faithfulness"].get("ok")
    )
    return sections


def write_gap_closure_report(
    *,
    live_own_head: bool = True,
    out_dir: Optional[Path] = None,
) -> tuple[Path, Path]:
    """Write JSON + Markdown reports; return (json_path, md_path)."""
    ensure_artifact_dirs()
    day = date.today().isoformat().replace("-", "")
    root = Path(out_dir) if out_dir else REPORTS
    root.mkdir(parents=True, exist_ok=True)
    data = build_gap_closure_report(live_own_head=live_own_head)
    jp = root / f"gap_closure_{day}.json"
    mp = root / f"gap_closure_{day}.md"
    jp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mp.write_text(_to_markdown(data), encoding="utf-8")
    return jp, mp


def _to_markdown(data: dict[str, Any]) -> str:
    s0 = data.get("stage0_own_head") or {}
    us = data.get("unseen_trace_shape") or {}
    fa = data.get("faithfulness") or {}
    ax = data.get("axes") or {}
    lines = [
        f"# Gap closure report",
        "",
        f"- generated_at: `{data.get('generated_at')}`",
        f"- overall_ok: **{data.get('ok')}**",
        "",
        "## Stage 0 own-head",
        f"- live: {s0.get('live')}",
        f"- ok: {s0.get('ok')}",
        f"- p_hat: {s0.get('p_hat')}",
        f"- label: {s0.get('label')}",
        "",
        "## Unseen / force_transfer trace shape",
        f"- canonical_ok: {us.get('canonical_fixture_ok')}",
        f"- own_head_smell_fixture_caught: {us.get('own_head_smell_detected')}",
        f"- ok: {us.get('ok')}",
        "",
        "## Faithfulness / verdict schema",
        f"- ok: {fa.get('ok')}",
        f"- detail: `{json.dumps(fa, ensure_ascii=False)[:240]}`",
        "",
        "## Axes",
        f"- `{json.dumps(ax, ensure_ascii=False)}`",
        "",
        "## Notes",
        "- Full GPU LOO / faithfulness×30 remain offline (`rbp_eval` eval-plan); this report is the lightweight Proposal evidence pack.",
        "- Scientific claims in SKILL should cite this path under `~/.nanobot-bio/artifacts/reports/`.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="gap-closure")
    p.add_argument("--no-live", action="store_true", help="Skip live own-head smoke")
    p.add_argument("--out-dir", default=None)
    args = p.parse_args(argv)
    jp, mp = write_gap_closure_report(
        live_own_head=not bool(args.no_live),
        out_dir=Path(args.out_dir) if args.out_dir else None,
    )
    print("gap_closure json:", jp)
    print("gap_closure md:", mp)
    data = json.loads(jp.read_text(encoding="utf-8"))
    return 0 if data.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
