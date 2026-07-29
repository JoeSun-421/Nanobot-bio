# -*- coding: utf-8 -*-
"""Light scientific eval of self-evolution: train/test split on LOO medoids.

Retunes fusion/abstain on a train half, scores mean LOO transfer AUPRC on the
held-out half for defaults vs retuned (vs optional live evolved.yaml). Reduces
same-matrix leakage vs scoring on the full set used for retune.

Does **not** recompute RhoBind; still CSV lookup.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.paths import PACKAGE_ROOT, REPORTS_JSON, REPORTS_MD, ensure_artifact_dirs
from rbp_eval.scoring.fuse_hits import DEFAULT_WEIGHTS, fuse_rbp_hits
from rbp_eval.evolve.runner import DEFAULT_VAL_RBPS

DEFAULT_OUT = REPORTS_JSON / "evolve_eval_report.json"
DEFAULT_MD = REPORTS_MD / "evolve_eval_report.md"
DEFAULT_DECISION = REPORTS_JSON / "evolve_eval_decision.json"
ABSTAIN_BAND = (0.05, 0.55)
DEFAULT_SEED = 42


def split_val_rbps(
    rbps: Optional[list[str]] = None,
    *,
    n_test: int = 5,
    seed: int = DEFAULT_SEED,
) -> tuple[list[str], list[str]]:
    """Deterministic train/test split of LOO medoid aliases."""
    pool = list(rbps or DEFAULT_VAL_RBPS)
    rng = random.Random(int(seed))
    shuffled = pool[:]
    rng.shuffle(shuffled)
    n_test = max(1, min(int(n_test), len(shuffled) - 1)) if len(shuffled) > 1 else len(shuffled)
    test = sorted(shuffled[:n_test])
    train = sorted(shuffled[n_test:])
    if not train and test:
        # edge: single item → train=test
        train = list(test)
    return train, test


def _subset_hits(
    held_to_hit_lists: dict[str, list[list[dict[str, Any]]]],
    aliases: list[str],
) -> dict[str, list[list[dict[str, Any]]]]:
    return {a: held_to_hit_lists[a] for a in aliases if a in held_to_hit_lists}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _default_abstain() -> dict[str, float]:
    base = _load_yaml(PACKAGE_ROOT / "config" / "defaults.yaml")
    return dict(base.get("abstain_thresholds") or {"fused": 0.45})


def _default_weights() -> dict[str, float]:
    base = _load_yaml(PACKAGE_ROOT / "config" / "defaults.yaml")
    return {**DEFAULT_WEIGHTS, **(base.get("fusion_weights") or {})}


def _live_evolved_knobs() -> tuple[dict[str, float], dict[str, float]]:
    cfg = _load_yaml(PACKAGE_ROOT / "config" / "evolved.yaml")
    if not cfg.get("evolved"):
        return {}, {}
    w = {**_default_weights(), **(cfg.get("fusion_weights") or {})}
    ab = {**_default_abstain(), **(cfg.get("abstain_thresholds") or {})}
    return w, ab


def score_policy_on_held(
    held_to_hit_lists: dict[str, list[list[dict[str, Any]]]],
    matrix: dict[tuple[str, str], float],
    *,
    weights: dict[str, float],
    abstain_thresholds: Optional[dict[str, float]] = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Mean LOO transfer AUPRC of fused donors; optional fused abstain gate."""
    thr = {**_default_abstain(), **(abstain_thresholds or {})}
    fused_t = float(thr.get("fused", 0.45))
    rows: list[dict[str, Any]] = []
    scored: list[float] = []
    bests: list[float] = []
    n_abs = 0
    n_held = len(held_to_hit_lists)

    for held, lists in held_to_hit_lists.items():
        donors = fuse_rbp_hits(
            lists,
            weights=weights,
            top_k=top_k,
            exclude_aliases={held},
            use_rank_normalize=True,
        )
        if not donors:
            n_abs += 1
            rows.append(
                {
                    "held_rbp": held,
                    "abstained": True,
                    "reason": "no_donors",
                    "policy_mean_auprc": None,
                    "policy_best_auprc": None,
                    "donors": [],
                }
            )
            continue
        best = donors[0]
        metric = str(best.get("metric") or "fused")
        t = float(thr.get(metric, fused_t))
        if float(best.get("score") or 0.0) < t:
            n_abs += 1
            rows.append(
                {
                    "held_rbp": held,
                    "abstained": True,
                    "reason": f"best_{metric}<{t}",
                    "best_score": best.get("score"),
                    "policy_mean_auprc": None,
                    "policy_best_auprc": None,
                    "donors": [d.get("alias") for d in donors],
                }
            )
            continue
        vals = []
        for d in donors:
            a = matrix.get((held, str(d.get("alias"))))
            if a is not None:
                vals.append(float(a))
        if not vals:
            rows.append(
                {
                    "held_rbp": held,
                    "abstained": False,
                    "reason": "no_loo_cells",
                    "policy_mean_auprc": None,
                    "policy_best_auprc": None,
                    "donors": [d.get("alias") for d in donors],
                }
            )
            continue
        mean_a = sum(vals) / len(vals)
        best_a = max(vals)
        scored.append(mean_a)
        bests.append(best_a)
        rows.append(
            {
                "held_rbp": held,
                "abstained": False,
                "policy_mean_auprc": round(mean_a, 6),
                "policy_best_auprc": round(best_a, 6),
                "donors": [d.get("alias") for d in donors],
                "best_fused_score": best.get("score"),
            }
        )

    abstain_rate = (n_abs / n_held) if n_held else 0.0
    lo, hi = ABSTAIN_BAND
    return {
        "n_held": n_held,
        "n_scored": len(scored),
        "n_abstained": n_abs,
        "abstain_rate": round(abstain_rate, 4),
        "abstain_in_band": lo - 1e-9 <= abstain_rate <= hi + 1e-9,
        "mean_policy_mean_auprc": (
            round(sum(scored) / len(scored), 6) if scored else None
        ),
        "mean_policy_best_auprc": (
            round(sum(bests) / len(bests), 6) if bests else None
        ),
        "rows": rows,
    }


def _promote_recommendation(
    *,
    delta_auprc: Optional[float],
    tier_a_ok: Optional[bool],
) -> dict[str, Any]:
    if delta_auprc is None:
        return {
            "recommend": "hold",
            "reason": "missing test AUPRC for defaults or retuned",
        }
    if delta_auprc > 0 and tier_a_ok is not False:
        return {
            "recommend": "promote" if tier_a_ok is True else "promote_if_tier_a_green",
            "reason": f"delta_auprc={delta_auprc:.6f} > 0",
        }
    if delta_auprc > 0 and tier_a_ok is False:
        return {
            "recommend": "hold",
            "reason": "positive delta but Tier A gate not green",
        }
    return {
        "recommend": "hold",
        "reason": f"delta_auprc={delta_auprc:.6f} ≤ 0 — keep candidate for human review",
    }


def assemble_report(
    *,
    train: list[str],
    test: list[str],
    defaults_score: dict[str, Any],
    retuned_score: dict[str, Any],
    live_score: Optional[dict[str, Any]],
    weight_retune: dict[str, Any],
    abstain_retune: dict[str, Any],
    seed: int,
    top_k: int,
    tier_a_ok: Optional[bool] = None,
) -> dict[str, Any]:
    d_best = defaults_score.get("mean_policy_best_auprc")
    r_best = retuned_score.get("mean_policy_best_auprc")
    delta = None
    if d_best is not None and r_best is not None:
        delta = round(float(r_best) - float(d_best), 6)
    return {
        "schema": "evolve_eval.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tier": "light_nested_split",
        "seed": seed,
        "top_k": top_k,
        "split": {
            "train_rbps": train,
            "test_rbps": test,
            "n_train": len(train),
            "n_test": len(test),
        },
        "leakage_note": (
            "train/test are LOO medoid halves; scores are CSV transfer lookups, "
            "not instance-level RhoBind AUPRC. Reduces but does not eliminate "
            "optimism vs retuning on the full 10."
        ),
        "weight_retune": {
            "status": weight_retune.get("status"),
            "baseline_score": weight_retune.get("baseline_score"),
            "tuned_score": weight_retune.get("tuned_score"),
            "tuned_weights": weight_retune.get("tuned_weights"),
        },
        "abstain_retune": {
            "status": abstain_retune.get("status"),
            "tuned_thresholds": abstain_retune.get("tuned_thresholds"),
            "tuned": abstain_retune.get("tuned"),
        },
        "test_scores": {
            "defaults": defaults_score,
            "retuned": retuned_score,
            "live_evolved": live_score,
        },
        "delta_auprc": delta,
        "delta_metric": "mean_policy_best_auprc_test(retuned - defaults)",
        "promote": _promote_recommendation(delta_auprc=delta, tier_a_ok=tier_a_ok),
        "gaps": [
            "No --with-esm / structure axis in this light harness",
            "No scored_labels / label-threshold CE",
            "No dark_protein / cross_kingdom fixtures",
            "Heavy force-transfer RhoBind recompute deferred",
            "AF3 runtime deferred (see AF3 status file / AF3_STATUS_FILE)",
        ],
    }


def report_to_markdown(report: dict[str, Any]) -> str:
    split = report.get("split") or {}
    ts = report.get("test_scores") or {}
    d = ts.get("defaults") or {}
    r = ts.get("retuned") or {}
    live = ts.get("live_evolved")
    promo = report.get("promote") or {}
    lines = [
        "# Self-evolution eval report (light nested split)",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Seed: `{report.get('seed')}` · top_k=`{report.get('top_k')}`",
        f"- Train ({split.get('n_train')}): {', '.join(split.get('train_rbps') or [])}",
        f"- Test ({split.get('n_test')}): {', '.join(split.get('test_rbps') or [])}",
        "",
        f"**Leakage note:** {report.get('leakage_note')}",
        "",
        "## Test metrics",
        "",
        "| Config | mean best AUPRC | mean mean AUPRC | abstain rate | in band |",
        "|--------|-----------------|-----------------|--------------|---------|",
        (
            f"| defaults | {d.get('mean_policy_best_auprc')} | "
            f"{d.get('mean_policy_mean_auprc')} | {d.get('abstain_rate')} | "
            f"{d.get('abstain_in_band')} |"
        ),
        (
            f"| retuned | {r.get('mean_policy_best_auprc')} | "
            f"{r.get('mean_policy_mean_auprc')} | {r.get('abstain_rate')} | "
            f"{r.get('abstain_in_band')} |"
        ),
    ]
    if live:
        lines.append(
            f"| live_evolved | {live.get('mean_policy_best_auprc')} | "
            f"{live.get('mean_policy_mean_auprc')} | {live.get('abstain_rate')} | "
            f"{live.get('abstain_in_band')} |"
        )
    lines += [
        "",
        f"- **delta_auprc** (retuned − defaults, best): `{report.get('delta_auprc')}`",
        f"- **Promote recommendation:** `{promo.get('recommend')}` — {promo.get('reason')}",
        "",
        "## Gaps (next cycle)",
        "",
    ]
    for g in report.get("gaps") or []:
        lines.append(f"- {g}")
    lines.append("")
    return "\n".join(lines)


def write_evolve_decision(
    report: dict[str, Any],
    *,
    path: Path | None = None,
) -> Path:
    """Persist the legacy n/delta gate decision; real calibration is separate."""
    split = report.get("split") or {}
    n = int(split.get("n_train") or 0) + int(split.get("n_test") or 0)
    delta = report.get("delta_auprc")
    recommendation = str((report.get("promote") or {}).get("recommend") or "hold")
    promote = (
        n >= 10
        and isinstance(delta, (int, float))
        and float(delta) > 0.0
        and recommendation.startswith("promote")
    )
    payload = {
        "schema": "evolve_decision/v1",
        "generated_at": report.get("generated_at"),
        "decision": "PROMOTE" if promote else "HOLD",
        "n": n,
        "delta_auprc": delta,
        "metric_source": "delivery_loo_csv_proxy",
        "authoritative_promotion_metric": False,
        "reason": (
            "legacy n>=10 and delta_auprc>0 gate passed"
            if promote
            else "legacy gate requires n>=10, delta_auprc>0, and promote recommendation"
        ),
    }
    out = path or DEFAULT_DECISION
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def run_evolve_eval(
    *,
    held_to_hit_lists: Optional[dict[str, list[list[dict[str, Any]]]]] = None,
    matrix: Optional[dict[tuple[str, str], float]] = None,
    seed: int = DEFAULT_SEED,
    n_test: int = 5,
    top_k: int = 5,
    with_esm: bool = False,
    offline: bool = True,
    include_live: bool = True,
    tier_a_ok: Optional[bool] = None,
    out_json: Optional[Path] = None,
    out_md: Optional[Path] = None,
    write: bool = True,
) -> dict[str, Any]:
    """Run nested light evolve eval; optionally fetch hit lists via delivery."""
    from rbp_eval.evolve.retune import (
        _load_loo_matrix,
        retune_abstain_thresholds,
        retune_weights,
    )

    ensure_artifact_dirs()
    if held_to_hit_lists is None:
        from rbp_eval.evolve.runner import run_loo_val_batch

        _results, held_to_hit_lists = run_loo_val_batch(
            top_k=top_k, offline=offline, with_esm=with_esm
        )
    if matrix is None:
        _summary, matrix = _load_loo_matrix()

    aliases = [a for a in DEFAULT_VAL_RBPS if a in held_to_hit_lists]
    if len(aliases) < 2:
        aliases = sorted(held_to_hit_lists.keys())
    train, test = split_val_rbps(aliases, n_test=n_test, seed=seed)
    train_hits = _subset_hits(held_to_hit_lists, train)
    test_hits = _subset_hits(held_to_hit_lists, test)

    base_w = _default_weights()
    base_ab = _default_abstain()

    if train_hits:
        weight_retune = retune_weights(train_hits, base_weights=base_w, top_k=top_k)
    else:
        weight_retune = {"status": "skipped", "reason": "empty train hits", "tuned_weights": base_w}

    tuned_w = dict(base_w)
    if weight_retune.get("status") == "ok":
        tuned_w.update(weight_retune.get("tuned_weights") or {})

    if train_hits:
        abstain_retune = retune_abstain_thresholds(
            train_hits, weights=tuned_w, top_k=top_k
        )
    else:
        abstain_retune = {
            "status": "skipped",
            "reason": "empty train hits",
            "tuned_thresholds": base_ab,
        }

    tuned_ab = dict(base_ab)
    if abstain_retune.get("status") == "ok":
        tuned_ab.update(abstain_retune.get("tuned_thresholds") or {})

    defaults_score = score_policy_on_held(
        test_hits, matrix, weights=base_w, abstain_thresholds=base_ab, top_k=top_k
    )
    retuned_score = score_policy_on_held(
        test_hits, matrix, weights=tuned_w, abstain_thresholds=tuned_ab, top_k=top_k
    )

    live_score = None
    if include_live:
        lw, lab = _live_evolved_knobs()
        if lw:
            live_score = score_policy_on_held(
                test_hits, matrix, weights=lw, abstain_thresholds=lab or base_ab, top_k=top_k
            )

    report = assemble_report(
        train=train,
        test=test,
        defaults_score=defaults_score,
        retuned_score=retuned_score,
        live_score=live_score,
        weight_retune=weight_retune,
        abstain_retune=abstain_retune,
        seed=seed,
        top_k=top_k,
        tier_a_ok=tier_a_ok,
    )

    if write:
        jp = out_json or DEFAULT_OUT
        mp = out_md or DEFAULT_MD
        jp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(report_to_markdown(report), encoding="utf-8")
        decision_path = write_evolve_decision(
            report,
            path=jp.parent / DEFAULT_DECISION.name,
        )
        report["paths"] = {
            "json": str(jp),
            "md": str(mp),
            "decision": str(decision_path),
        }
        jp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Light nested-split self-evolution eval")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--n-test", type=int, default=5)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--with-esm", action="store_true")
    ap.add_argument("--no-live", action="store_true", help="Skip scoring live evolved.yaml")
    ap.add_argument(
        "--tier-a-ok",
        default=None,
        choices=["true", "false"],
        help="Pass Tier A gate result into promote recommendation",
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--md", type=Path, default=DEFAULT_MD)
    args = ap.parse_args(argv)

    tier_a: Optional[bool] = None
    if args.tier_a_ok == "true":
        tier_a = True
    elif args.tier_a_ok == "false":
        tier_a = False

    report = run_evolve_eval(
        seed=args.seed,
        n_test=args.n_test,
        top_k=args.top_k,
        with_esm=bool(args.with_esm),
        include_live=not bool(args.no_live),
        tier_a_ok=tier_a,
        out_json=args.out,
        out_md=args.md,
        write=True,
    )
    print("evolve_eval:", report.get("paths", {}).get("json", args.out))
    print("delta_auprc:", report.get("delta_auprc"))
    print("promote:", json.dumps(report.get("promote"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
