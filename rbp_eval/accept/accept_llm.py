# -*- coding: utf-8 -*-
"""Strict acceptance: product path must be nanobot_llm; capture LLM touchpoint evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def run_accept_llm(
    *,
    run_catalogue: bool = True,
    run_unseen: bool = True,
    strict: bool = True,
) -> dict[str, Any]:
    from app.backends.delivery.examples import own_head_prompt
    from app.core.paths import SESSIONS, ensure_artifact_dirs, report_path
    from app.integrate import RBPAgent

    ensure_artifact_dirs()
    agent = RBPAgent(prefer_nanobot_llm=True, allow_fallback=False)
    runs: list[dict[str, Any]] = []
    touchpoints = {
        "stage1_function_or_donor": False,
        "stage3_explanation": False,
        "abstain_before_predict": False,
        "parallel_or_dual_seq": False,
        "llm_commit_proxies": False,
        "evidence": {},
    }

    def _clear_session(case: str) -> None:
        """Delete any persisted session for this case so the LLM exercises tools
        fresh instead of short-circuiting on a cached prior verdict
        (``ephemeral=True`` does not discard pre-existing session memory)."""
        try:
            # Dated layout: sessions/YYYY-MM-DD/… plus any leftover flat files.
            for p in (
                *SESSIONS.glob(f"accept-llm_{case}*.jsonl"),
                *SESSIONS.glob(f"*/accept-llm_{case}*.jsonl"),
            ):
                p.unlink(missing_ok=True)
        except Exception:
            pass

    def _one(case: str, message: str, *, expect_stage1: bool) -> None:
        _clear_session(case)
        try:
            result = agent.run_sync(
                message,
                ephemeral=True,
                session_key=f"accept-llm:{case}",
            )
            mode = result.mode
            verdict = result.verdict if isinstance(result.verdict, dict) else {}
            tools = list(result.tools_used or [])
            if not tools:
                for ev in result.traces or []:
                    if isinstance(ev, dict) and ev.get("tool"):
                        tools.append(str(ev.get("tool")))
            expl = str(verdict.get("explanation") or "")
            if expl.strip():
                touchpoints["stage3_explanation"] = True
            stage1_tools = {
                "fuse_similarity_views",
                "commit_proxy_candidates",
                "get_func_annotation",
                "function_category",
                "seq_similarity",
                "rna_blastn",
                "struct_similarity",
                "domain_architecture",
                "pdb_metadata",
                "structure_consensus",
                "check_near_known",
                "confidence_abstain",
            }
            hit = sorted(stage1_tools.intersection(tools))
            if expect_stage1 and hit:
                touchpoints["stage1_function_or_donor"] = True
            if expect_stage1:
                if "confidence_abstain" in tools and "predict_interaction" in tools:
                    if tools.index("confidence_abstain") < tools.index(
                        "predict_interaction"
                    ):
                        touchpoints["abstain_before_predict"] = True
                if "commit_proxy_candidates" in tools:
                    touchpoints["llm_commit_proxies"] = True
                if "seq_similarity" in tools or "rna_blastn" in tools:
                    touchpoints["parallel_or_dual_seq"] = True
            ok_mode = (mode == "nanobot_llm") if strict else True
            runs.append(
                {
                    "case": case,
                    "mode": mode,
                    "ok_mode": ok_mode,
                    "tools_used": tools,
                    "has_explanation": bool(expl.strip()),
                    "stage1_tools_hit": hit,
                    "p_hat": verdict.get("p_hat"),
                    "error": result.error,
                }
            )
            touchpoints["evidence"][f"{case}_tools"] = tools
            touchpoints["evidence"][f"{case}_explanation_len"] = len(expl)
        except Exception as e:
            runs.append(
                {
                    "case": case,
                    "ok_mode": False,
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    if run_catalogue:
        _one("catalogue_own_head", own_head_prompt("pos"), expect_stage1=False)

    if run_unseen:
        msg = (
            "Does this RNA interact with RBP FUS (UniProt P35637) in cohort K562?\n"
            "RNA: AUUUAUUUAUUUAUUUAUUUAUUUAUUUAUUUAUUUAUUUAUUUAUUUAUUUAUUUAUUUAUUUA\n"
            "FUS may be unseen or near-known — call check_near_known; if not near, "
            "characterize → parallel retrieve (seq_similarity dual-axis) → "
            "fuse_similarity_views → confidence_abstain → predict donors → integrate. "
            "Use rna_blastn for optional RNA-side peaks evidence when PEAKS_DB is "
            "available; skip the RNA axis otherwise. Call get_func_annotation once. "
            "End with one JSON verdict."
        )
        _one("unseen_transfer", msg, expect_stage1=True)

    modes_ok = all(bool(r.get("ok_mode")) for r in runs) if runs else False
    tp_ok = bool(touchpoints["stage3_explanation"])
    if run_unseen:
        tp_ok = tp_ok and bool(touchpoints["stage1_function_or_donor"])
        if strict:
            tp_ok = tp_ok and bool(touchpoints["abstain_before_predict"])

    report = {
        "schema": "llm_touchpoints_accept.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strict": strict,
        "runs": runs,
        "touchpoints": touchpoints,
        "ok": bool(modes_ok and tp_ok and runs),
        "ok_nanobot_llm": modes_ok,
        "ok_touchpoints": tp_ok,
    }
    out = report_path("llm_touchpoints_accept.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report["path"] = str(out)
    return report
