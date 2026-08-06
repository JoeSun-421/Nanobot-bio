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
        "rbp_eval.evolve.runner.run_scored_loo_val_batch (default) | "
        "run_loo_val_batch (--retrieval-only)."
    )


def run_scored_loo_val_batch(
    *,
    rbps: Optional[list[str]] = None,
    top_k: int = 5,
    cohort: str = "K562",
    max_seqs: int = 64,
    device: str = "cuda",
    trace_path: str | Path | None = None,
    with_retrieval_hits: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, list[list[dict[str, Any]]]], list[dict[str, Any]]]:
    """Hide-own-head scored LOO val: real donor probs → ``{p_hat,y}`` + transfer results.

    Returns ``(results, held_to_hit_lists, scored_labels)``.
    """
    from app.backends.delivery.env import apply_delivery_env, resolve_delivery_paths
    from app.core.paths import report_path
    from app.core.verdict_schema import normalize_verdict
    from rbp_eval.loo.heavy_loo import (
        MEDOIDS,
        pick_donors,
        test_fasta_for,
    )
    from rbp_eval.loo.loo_eval import load_transfer_matrix, resolve_loo_csvs
    from rbp_eval.loo.batch_score_held import run_batch_score_subprocess

    apply_delivery_env()
    helds = list(rbps) if rbps else list(MEDOIDS)
    paths = resolve_delivery_paths()
    delivery = Path(paths["delivery_root"])
    release = Path(paths.get("rhobind_release") or (delivery / "release" / "rhobind_release_v1"))
    _summary_path, metrics_path = resolve_loo_csvs()
    matrix = load_transfer_matrix(metrics_path) if metrics_path and metrics_path.is_file() else {}

    held_hits: dict[str, list[list[dict[str, Any]]]] = {}
    if with_retrieval_hits:
        try:
            _ret_results, held_hits = run_loo_val_batch(
                top_k=top_k,
                trace_path=trace_path,
                with_esm=False,
            )
            # Restrict to requested helds
            held_hits = {k: v for k, v in held_hits.items() if k in set(helds)}
        except Exception:
            held_hits = {}

    results: list[dict[str, Any]] = []
    scored_labels: list[dict[str, Any]] = []
    heavy_rows: list[dict[str, Any]] = []

    for alias in helds:
        donors = pick_donors(alias, matrix, top_k) if matrix else []
        fasta = test_fasta_for(alias, cohort, delivery)
        row: dict[str, Any]
        if fasta is None or not donors:
            row = {
                "held_rbp": alias,
                "ok": False,
                "reason": "missing_fasta_or_donors",
                "donors": donors,
            }
            heavy_rows.append(row)
            results.append(
                {
                    "query": {"alias": alias},
                    "mode": "transfer",
                    "donors": [{"alias": d} for d in donors],
                    "errors": [row.get("reason")],
                    "verdict": normalize_verdict(
                        {
                            "label": "No",
                            "p_hat": None,
                            "confidence": "low",
                            "explanation": f"scored LOO skipped: {row.get('reason')}",
                            "supporting_rbps": [],
                        }
                    ),
                }
            )
            continue

        # Prefer batch donor scoring (encode-once); fall back to heavy_loo per held
        scored = run_batch_score_subprocess(
            held=alias,
            cohort=cohort,
            fasta=fasta,
            release=release,
            foreigns=donors,
            max_seqs=max_seqs,
            device=device,
            batch_size=64,
            seed=42,
            donors_only=True,
        )
        pairs: list[dict[str, Any]] = []
        recovered = None
        own_ceil = None
        if scored.get("ok") and scored.get("pairs"):
            pairs = [
                {
                    "p_hat": float(p["p_hat"]),
                    "y": int(p["y"]),
                    "score": float(p.get("score", p["p_hat"])),
                }
                for p in scored["pairs"]
            ]
            recovered = scored.get("recovered_auprc")
            own_ceil = scored.get("own_full_auprc")
            donors = list(scored.get("donors") or donors)
        else:
            from rbp_eval.loo.heavy_loo import run_one_held

            one = run_one_held(
                alias, cohort=cohort, top_k=top_k, max_seqs=max_seqs, device=device
            )
            heavy_rows.append(one)
            if one.get("ok"):
                pairs = [
                    {"p_hat": float(p["score"]), "y": int(p["y"]), "score": float(p["score"])}
                    for p in (one.get("pairs") or [])
                ]
                recovered = one.get("recovered_auprc")
                own_ceil = one.get("own_full_auprc")
                donors = list(one.get("donors") or donors)
            else:
                results.append(
                    {
                        "query": {"alias": alias},
                        "mode": "transfer",
                        "donors": [{"alias": d} for d in donors],
                        "errors": [one.get("reason")],
                        "verdict": normalize_verdict(
                            {
                                "label": "No",
                                "p_hat": None,
                                "confidence": "low",
                                "explanation": f"scored LOO failed: {one.get('reason')}",
                                "supporting_rbps": [],
                            }
                        ),
                    }
                )
                continue

        if not pairs:
            results.append(
                {
                    "query": {"alias": alias},
                    "mode": "transfer",
                    "donors": [{"alias": d} for d in donors],
                    "errors": ["no_scored_pairs"],
                    "verdict": normalize_verdict(
                        {
                            "label": "No",
                            "p_hat": None,
                            "confidence": "low",
                            "explanation": "scored LOO produced no pairs",
                            "supporting_rbps": [],
                        }
                    ),
                }
            )
            continue

        scored_labels.extend(
            {"p_hat": p["p_hat"], "y": p["y"], "held_rbp": alias} for p in pairs
        )
        mean_p = sum(p["p_hat"] for p in pairs) / len(pairs)
        n_abstain = sum(1 for p in pairs if p.get("p_hat") is None)
        gap = None if own_ceil is None or recovered is None else float(own_ceil) - float(recovered)

        # Ensure hit lists exist for weight retune (matrix prior as similarity)
        if alias not in held_hits or not any(held_hits.get(alias) or []):
            prior_hits = []
            for d in donors:
                auprc = matrix.get((alias, d))
                score = float(auprc) if auprc is not None else 0.5
                prior_hits.append(
                    {
                        "alias": d,
                        "score": score,
                        "metric": "transfer_prior",
                        "sim_by_modality": {
                            "domain_overlap": score,
                            "transfer_prior": score,
                        },
                    }
                )
            held_hits[alias] = [prior_hits]

        heavy_rows.append(
            {
                "held_rbp": alias,
                "ok": True,
                "donors": donors,
                "recovered_auprc": recovered,
                "own_full_auprc": own_ceil,
                "gap_to_own": gap,
                "n_scored": len(pairs),
                "abstain_rate": n_abstain / len(pairs) if pairs else None,
            }
        )
        results.append(
            {
                "query": {"alias": alias},
                "mode": "transfer",
                "donors": [
                    {
                        "alias": d,
                        "score": float(matrix[(alias, d)])
                        if (alias, d) in matrix
                        else None,
                    }
                    for d in donors
                ],
                "errors": [],
                "retrieval": {"transfer_matrix": {"ok": True, "n": len(donors)}},
                "evidence_table": held_hits.get(alias, [[]])[0] if held_hits.get(alias) else [],
                "predictions": [{"alias": d, "prob": mean_p} for d in donors[:1]],
                "loo_metrics": {
                    "recovered_auprc": recovered,
                    "own_full_auprc": own_ceil,
                    "gap_to_ceiling": gap,
                    "n_scored": len(pairs),
                    "abstain_rate": n_abstain / len(pairs) if pairs else 0.0,
                },
                "verdict": normalize_verdict(
                    {
                        "label": "Likely" if mean_p >= 0.5 else "Unlikely",
                        "p_hat": float(mean_p),
                        "confidence": "medium",
                        "explanation": (
                            f"Scored LOO hide-own-head for {alias}: "
                            f"recovered_auprc={recovered} gap={gap}"
                        ),
                        "supporting_rbps": [
                            {
                                "alias": d,
                                "similarity_score": float(matrix[(alias, d)])
                                if (alias, d) in matrix
                                else 0.5,
                                "prob": float(mean_p),
                                "sim_by_modality": {
                                    "transfer_prior": float(matrix[(alias, d)])
                                    if (alias, d) in matrix
                                    else 0.5,
                                    "domain_overlap": float(matrix[(alias, d)])
                                    if (alias, d) in matrix
                                    else 0.5,
                                },
                            }
                            for d in donors
                        ],
                    }
                ),
            }
        )

    # Persist a heavy-LOO-shaped report so promote/evolve LOO gate can find it
    try:
        ok_rows = [r for r in heavy_rows if r.get("ok")]
        mean_rec = (
            sum(float(r["recovered_auprc"]) for r in ok_rows if r.get("recovered_auprc") is not None)
            / len(ok_rows)
            if ok_rows
            else None
        )
        report = {
            "schema": "loo_heavy.v2",
            "protocol": "scored_loo_val_batch",
            "cohort": cohort,
            "top_k": top_k,
            "max_seqs": max_seqs,
            "rbps": helds,
            "rows": heavy_rows,
            "summary": {
                "n_ok": len(ok_rows),
                "n_fail": len(heavy_rows) - len(ok_rows),
                "mean_recovered_auprc": mean_rec,
            },
            "ok": len(ok_rows) >= 1,
        }
        outp = report_path("heavy_loo_report.json")
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        pass

    return results, held_hits, scored_labels


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


def collect_agent_traces(
    results: list[dict[str, Any]],
    *,
    out_path: str | Path | None = None,
    session_key: str = "rbp:collect_agent_traces",
) -> Path:
    """Write rbp_trace/v1 JSONL from scored/retrieval results (no LLM required).

    Emits ``query_end`` (+ optional ``stage1_bypassed``) so attribution / cache
    promotion can consume real structured traces alongside synthetic scored paths.
    """
    from app.core.paths import TRACES
    from rbp_eval.runtime.trace_schema import make_event, validate_event

    path = Path(out_path) if out_path else TRACES / "collect_agent_traces.jsonl"
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for i, r in enumerate(results):
            q = r.get("query") or {}
            if isinstance(q, str):
                q = {"alias": q}
            alias = q.get("alias") or r.get("alias")
            et = r.get("evidence_table") or []
            donors = r.get("donors") or []
            enriched = []
            for d in donors:
                if not isinstance(d, dict):
                    continue
                row = dict(d)
                if not row.get("sim_by_modality"):
                    # Prefer evidence_table row match
                    for e in et:
                        if isinstance(e, dict) and e.get("alias") == row.get("alias"):
                            row["sim_by_modality"] = e.get("sim_by_modality") or {
                                "transfer_prior": e.get("score")
                            }
                            break
                    if not row.get("sim_by_modality") and row.get("score") is not None:
                        row["sim_by_modality"] = {"transfer_prior": row.get("score")}
                enriched.append(row)
            ev = make_event(
                "query_end",
                session_key=session_key,
                index=i,
                query=q,
                alias=alias,
                donors=enriched,
                evidence_table=et,
                fused_similarities=[
                    {
                        "alias": e.get("alias"),
                        "score": e.get("score") or e.get("similarity_score"),
                        "sim_by_modality": e.get("sim_by_modality"),
                    }
                    for e in enriched
                ],
                verdict=r.get("verdict"),
                mode=r.get("mode"),
                stage1_bypassed=bool(
                    (r.get("retrieval") or {}).get("stage1_bypassed")
                    or (r.get("verdict") or {}).get("stage1_bypassed")
                ),
            )
            problems = validate_event(ev)
            if problems:
                ev["schema_warnings"] = problems
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
    return path


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
