# -*- coding: utf-8 -*-
"""
Evaluation package runner — rbp_eval/evolve/runner.py

Batch-run validation queries, write JSONL traces (AgentHook-compatible),
feed the self-evolution evaluator.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]  # nanobot-bio
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.core.paths import DEFAULT_EVAL_TRACE, DEFAULT_VAL_BATCH, ensure_artifact_dirs
from rbp_eval.runtime.hooks import JsonlTraceHook

ensure_artifact_dirs()

DEFAULT_VAL_RBPS = [
    "NSUN2",
    "FXR2",
    "HNRNPUL1",
    "EEF2",
    "PTBP1",
    "CPSF6",
    "DHX30",
    "DDX51",
    "DROSHA",
    "RPS6",
]


def load_default_val_cases(
    *,
    rna: Optional[str] = None,
    force_transfer: bool = True,
) -> list[dict[str, Any]]:
    """Build D_val-style cases from delivery LOO hold-out list + sample RNA."""
    from app.backends.delivery.env import apply_delivery_env, delivery_root

    apply_delivery_env()
    ex = delivery_root() / "agent" / "examples"
    if rna is None:
        rna_path = ex / "sample_rna_pos.txt"
        rna = rna_path.read_text(encoding="utf-8").strip() if rna_path.is_file() else "AUGC" * 40

    cases = []
    for alias in DEFAULT_VAL_RBPS:
        cases.append(
            {
                "target_name": alias,
                "query": alias,
                "rna": rna,
                "force_transfer": force_transfer,
                "offline": True,
                "cohort": "K562",
            }
        )
    return cases


def run_batch(
    cases: Iterable[dict[str, Any]],
    *,
    trace_path: str | Path | None = None,
    offline: bool = True,
    device: str = "auto",
    config: Optional[dict[str, Any]] = None,
    use_evolved_config: bool = True,
) -> list[dict[str, Any]]:
    """Removed with core.pipeline — product path is Nanobot.run only."""
    raise RuntimeError(
        "Fixed pipeline batch runner removed. "
        "Use: rbp-agent own-head | rbp-agent agent --example pos | "
        "rbp_eval.evolve.runner.run_loo_val_batch (retrieval-only for weight retune)."
    )


def _safe_hits(out: Any) -> list[dict[str, Any]]:
    if not isinstance(out, dict):
        return []
    # unwrap error
    if out.get("error") or (out.get("ok") is False and "hits" not in out):
        return []
    hits = out.get("hits")
    if isinstance(hits, list):
        return [h for h in hits if isinstance(h, dict)]
    return []


def run_loo_val_batch(
    *,
    top_k: int = 5,
    trace_path: str | Path | None = None,
    offline: bool = True,
    with_esm: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, list[list[dict[str, Any]]]]]:
    """
    LOO-style val (retrieval-only): multi-view hits per held RBP for weight retune.

    Always runs ``domain_architecture``. Optionally ``esm_similarity`` (RAM-heavy).
    Does **not** run RhoBind; prediction stays on the Nanobot agent path.
    """
    from app.backends.delivery.client import DeliveryToolClient
    from app.backends.delivery.env import apply_delivery_env
    from app.core.verdict_schema import normalize_verdict
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

    apply_delivery_env()
    # use_conda for ESM path when requested; domain can run without
    client = DeliveryToolClient(
        offline=offline,
        device="cpu",
        use_conda=bool(with_esm),
    )
    cases = load_default_val_cases(force_transfer=True)
    held_hits: dict[str, list[list[dict[str, Any]]]] = {}
    tp = Path(trace_path or DEFAULT_EVAL_TRACE)
    if not tp.is_absolute():
        tp = ROOT / tp
    hook = JsonlTraceHook(tp, session_key="rbp:eval")
    results: list[dict[str, Any]] = []
    axes_used_global: set[str] = set()

    for i, case in enumerate(cases):
        alias = case["query"]
        hook.push_event({"type": "query_start", "index": i, "case_keys": list(case.keys())})
        lists: list[list[dict[str, Any]]] = []
        retrieval: dict[str, Any] = {}
        axes_used: list[str] = []

        # Domain axis (cheap, no GPU)
        try:
            dom = client.call(
                "domain_architecture",
                {"alias": alias, "top_k": top_k * 2, "network": False},
            )
            dom_hits = _safe_hits(dom)
            if not dom_hits and isinstance(dom, dict) and dom.get("error"):
                retrieval["domain"] = {"ok": False, "error": str(dom.get("error"))[:300]}
            else:
                retrieval["domain"] = {"ok": bool(dom_hits), "n": len(dom_hits)}
                if dom_hits:
                    lists.append(dom_hits)
                    axes_used.append("domain")
                    axes_used_global.add("domain")
        except Exception as e:
            retrieval["domain"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

        # ESM axis (optional): delivery esm_embed requires AA `sequence` (alias alone fails)
        if with_esm:
            try:
                import os

                from nanobot.agent.tools.rbp.common import load_catalogue_sequence

                seq = load_catalogue_sequence(alias) or ""
                uniprot = None
                if not seq:
                    res = client.call("resolve_rbp", {"query": alias})
                    if isinstance(res, dict):
                        seq = str(res.get("sequence") or "")
                        uniprot = res.get("uniprot")
                if not seq:
                    retrieval["esm_similarity"] = {
                        "ok": False,
                        "error": f"no AA sequence for {alias}",
                    }
                else:
                    dev = os.environ.get("RHOBIND_DEVICE", "cpu")
                    if dev == "auto":
                        dev = "cuda"
                    if dev not in ("cuda", "cpu"):
                        dev = "cpu"
                    payload: dict[str, Any] = {
                        "sequence": seq,
                        "encoder": "esmc",
                        "device": dev,
                        "top_k": top_k * 2,
                    }
                    if uniprot:
                        payload["uniprot"] = uniprot
                    esm = client.call("esm_similarity", payload)
                    esm_hits = _safe_hits(esm)
                    if esm_hits:
                        lists.append(esm_hits)
                        axes_used.append("esm")
                        axes_used_global.add("esm")
                        retrieval["esm_similarity"] = {"ok": True, "n": len(esm_hits)}
                    else:
                        err = ""
                        if isinstance(esm, dict):
                            err = str(
                                esm.get("error")
                                or esm.get("reason")
                                or ""
                            )[:300]
                        retrieval["esm_similarity"] = {
                            "ok": False,
                            "error": err or "no hits",
                        }
            except Exception as e:
                retrieval["esm_similarity"] = {
                    "ok": False,
                    "error": f"{type(e).__name__}: {e}"[:300],
                }

        donors = fuse_rbp_hits(
            lists,
            top_k=top_k,
            exclude_aliases={alias},
            use_rank_normalize=True,
            tau_drop=0.30,
        ) if lists else []
        # fallback: raw domain top_k
        if not donors and lists:
            flat = []
            for lst in lists:
                flat.extend(lst)
            donors = flat[:top_k]

        held_hits[alias] = lists if lists else [[]]
        out = {
            "query": {"alias": alias},
            "mode": "retrieval_only",
            "donors": donors,
            "errors": [],
            "retrieval": retrieval,
            "axes_used": axes_used,
            "evidence_table": [
                {
                    "alias": d.get("alias"),
                    "uniprot": d.get("uniprot"),
                    "score": d.get("score"),
                    "sim_by_modality": d.get("sim_by_modality") or {},
                }
                for d in donors
            ],
        }
        out["verdict"] = normalize_verdict(
            {
                "label": "No",
                "p_hat": None,
                "confidence": "low",
                "explanation": (
                    f"Retrieval-only LOO stub for {alias} "
                    f"(axes={axes_used}, n_donors={len(donors)}); "
                    "score via Nanobot agent."
                ),
                "supporting_rbps": [
                    {
                        "alias": h.get("alias"),
                        "rbp_id": h.get("uniprot"),
                        "similarity_score": h.get(
                            "vote_similarity", h.get("score")
                        ),
                        "fused_score": h.get("score"),
                        "prob": None,
                    }
                    for h in donors
                ],
            }
        )
        hook.push_event(
            {
                "type": "query_end",
                "index": i,
                "query": {"alias": alias},
                "alias": alias,
                "mode": out["mode"],
                "donors": out["donors"],
                "verdict": out["verdict"],
                "errors": out["errors"],
                "axes_used": axes_used,
            }
        )
        results.append(out)

    # annotate first result with global axes for report consumers
    if results:
        results[0]["axes_used_global"] = sorted(axes_used_global)
    return results, held_hits


def load_traces(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.is_file():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: python -m rbp_eval.evolve.runner [--evolve]"""
    import argparse

    from rbp_eval.evolve.orchestrator import run_self_evolution, summarize_verdicts

    ap = argparse.ArgumentParser(description="Batch val runner + optional self-evolution")
    ap.add_argument("--evolve", action="store_true", help="Run self-evolution after batch")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--with-esm", action="store_true")
    ap.add_argument(
        "--trace",
        default=str(DEFAULT_EVAL_TRACE),
        help="JSONL trace path",
    )
    ap.add_argument("--out", default=str(DEFAULT_VAL_BATCH))
    args = ap.parse_args(argv)

    results, held_hits = run_loo_val_batch(
        top_k=args.top_k, trace_path=args.trace, with_esm=bool(args.with_esm)
    )
    summary = summarize_verdicts(results)
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"summary": summary, "n": len(results), "results": results},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print("summary:", json.dumps(summary, ensure_ascii=False))
    print("wrote", out_path)

    if args.evolve:
        traces = load_traces(args.trace)
        report = run_self_evolution(
            results,
            held_to_hit_lists=held_hits,
            traces=traces,
            top_k=args.top_k,
            write_config=True,
        )
        print("self-evolution:", json.dumps(report.to_dict(), indent=2, ensure_ascii=False)[:2000])
        print("evolved_config:", report.evolved_config_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
