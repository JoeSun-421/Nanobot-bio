# -*- coding: utf-8 -*-
"""A/B: delivery LOO matrix vs agent-side expanded copy (accuracy / prior coverage)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from rbp_eval.loo.loo_eval import (  # noqa: E402
    DEFAULT_VAL,
    default_expanded_transfer_dir,
    load_loo_summary,
    load_transfer_matrix,
    resolve_loo_csvs,
)


def _prior_missing_rate(
    matrix: dict[tuple[str, str], float],
    helds: list[str],
    donors_per_held: dict[str, list[str]],
) -> float:
    if not helds:
        return 1.0
    miss = 0
    total = 0
    for h in helds:
        donors = donors_per_held.get(h) or []
        if not donors:
            # count as missing if held has no matrix row at all
            has_any = any(k[0] == h for k in matrix)
            total += 1
            if not has_any:
                miss += 1
            continue
        for d in donors:
            total += 1
            if (h, d) not in matrix:
                miss += 1
    return miss / total if total else 1.0


def _policy_scores(
    matrix: dict[tuple[str, str], float],
    summary: dict[str, dict[str, Any]],
    helds: list[str],
    top_k: int = 5,
) -> dict[str, Any]:
    """Light protocol without live retrieval: top foreign by matrix AUPRC."""
    rows = []
    policy_bests = []
    owns = []
    for held in helds:
        scored = [
            (f, a)
            for (h, f), a in matrix.items()
            if h == held and f != held
        ]
        scored.sort(key=lambda t: t[1], reverse=True)
        donors = [f for f, _ in scored[:top_k]]
        vals = [a for _, a in scored[:top_k]]
        sm = summary.get(held) or {}
        own = float(sm["own_full_auprc"]) if sm.get("own_full_auprc") not in (None, "") else None
        best = max(vals) if vals else None
        mean = sum(vals) / len(vals) if vals else None
        if best is not None:
            policy_bests.append(best)
        if own is not None:
            owns.append(own)
        rows.append(
            {
                "held_rbp": held,
                "donors": donors,
                "policy_best": None if best is None else round(best, 5),
                "policy_mean": None if mean is None else round(mean, 5),
                "own_full_auprc": own,
                "n_measured_donors": len(vals),
                "prior_missing": len(vals) == 0,
            }
        )
    donors_map = {r["held_rbp"]: r["donors"] for r in rows}
    return {
        "rows": rows,
        "mean_policy_best": round(sum(policy_bests) / len(policy_bests), 5) if policy_bests else None,
        "mean_own_full": round(sum(owns) / len(owns), 5) if owns else None,
        "prior_missing_rate": round(_prior_missing_rate(matrix, helds, donors_map), 4),
        "n_held_with_policy": len(policy_bests),
        "n_matrix_pairs": len(matrix),
        "n_summary_held": len(summary),
    }


def _retune_on_matrix(transfer_dir: Path, top_k: int = 5) -> dict[str, Any]:
    """Run fusion weight retune using env-pointed matrix + domain hits when possible."""
    prev = os.environ.get("RBP_LOO_TRANSFER_DIR")
    os.environ["RBP_LOO_TRANSFER_DIR"] = str(transfer_dir)
    try:
        from rbp_eval.evolve.retune import retune_weights
        from rbp_eval.evolve.runner import run_loo_val_batch

        results, held_hits = run_loo_val_batch(top_k=top_k, with_esm=False)
        if not held_hits:
            return {"status": "skipped", "reason": "no held hit lists"}
        out = retune_weights(held_hits, top_k=top_k)
        out["n_val_results"] = len(results)
        return out
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": str(e)}
    finally:
        if prev is None:
            os.environ.pop("RBP_LOO_TRANSFER_DIR", None)
        else:
            os.environ["RBP_LOO_TRANSFER_DIR"] = prev


def run_matrix_ab(
    *,
    expanded_dir: Optional[Path] = None,
    helds: Optional[list[str]] = None,
    top_k: int = 5,
    retune: bool = True,
    out: Optional[Path] = None,
) -> dict[str, Any]:
    from app.core.paths import ensure_artifact_dirs, report_path

    ensure_artifact_dirs()
    helds = list(helds or DEFAULT_VAL)
    expanded_dir = Path(expanded_dir or default_expanded_transfer_dir()).expanduser().resolve()

    base_summary_p, base_metrics_p = resolve_loo_csvs(prefer_delivery=True)
    exp_summary_p, exp_metrics_p = resolve_loo_csvs(transfer_dir=expanded_dir)

    baseline = {
        "status": "missing_csv",
        "paths": {"summary": str(base_summary_p), "metrics": str(base_metrics_p)},
    }
    if base_summary_p.is_file() and base_metrics_p.is_file():
        baseline = {
            "status": "ok",
            "paths": {"summary": str(base_summary_p), "metrics": str(base_metrics_p)},
            **_policy_scores(
                load_transfer_matrix(base_metrics_p),
                load_loo_summary(base_summary_p),
                helds,
                top_k=top_k,
            ),
        }

    expanded = {
        "status": "missing_csv",
        "paths": {"summary": str(exp_summary_p), "metrics": str(exp_metrics_p)},
    }
    if exp_summary_p.is_file() and exp_metrics_p.is_file():
        expanded = {
            "status": "ok",
            "paths": {"summary": str(exp_summary_p), "metrics": str(exp_metrics_p)},
            **_policy_scores(
                load_transfer_matrix(exp_metrics_p),
                load_loo_summary(exp_summary_p),
                helds,
                top_k=top_k,
            ),
        }

    retune_base = {"status": "skipped"}
    retune_exp = {"status": "skipped"}
    if retune and baseline.get("status") == "ok":
        # baseline retune uses delivery via prefer path: temporarily clear env
        prev = os.environ.pop("RBP_LOO_TRANSFER_DIR", None)
        try:
            # Point at delivery parent of metrics
            delivery_transfer = Path(base_metrics_p).parent
            retune_base = _retune_on_matrix(delivery_transfer, top_k=top_k)
        finally:
            if prev is not None:
                os.environ["RBP_LOO_TRANSFER_DIR"] = prev
    if retune and expanded.get("status") == "ok":
        retune_exp = _retune_on_matrix(expanded_dir, top_k=top_k)

    def _delta(a: Any, b: Any) -> Optional[float]:
        if a is None or b is None:
            return None
        try:
            return round(float(a) - float(b), 5)
        except (TypeError, ValueError):
            return None

    delta = {
        "delta_auprc_policy_best": _delta(
            expanded.get("mean_policy_best"), baseline.get("mean_policy_best")
        ),
        "delta_prior_missing_rate": _delta(
            expanded.get("prior_missing_rate"), baseline.get("prior_missing_rate")
        ),
        "delta_retune_loo_auprc": _delta(
            retune_exp.get("tuned_score"), retune_base.get("tuned_score")
        ),
        "delta_matrix_pairs": _delta(
            expanded.get("n_matrix_pairs"), baseline.get("n_matrix_pairs")
        ),
    }
    improved = bool(
        (delta["delta_auprc_policy_best"] or 0) > 0
        or (delta["delta_retune_loo_auprc"] or 0) > 0
    ) and (delta.get("delta_prior_missing_rate") or 0) <= 0

    report = {
        "schema": "loo_matrix_ab.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "helds": helds,
        "top_k": top_k,
        "baseline": baseline,
        "expanded": expanded,
        "retune": {"baseline": retune_base, "expanded": retune_exp},
        "delta": delta,
        "conclusion": {
            "expanded_improves_accuracy_signal": improved,
            "note": (
                "Light matrix lookup + optional retune objective; "
                "does not auto-promote evolved.yaml. "
                "Run heavy-loo / transfer_calibration for RhoBind instance metrics."
            ),
        },
    }

    out_path = Path(out or report_path("loo_matrix_ab.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report["paths"] = {"json": str(out_path)}
    return report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="A/B delivery vs expanded LOO matrix")
    ap.add_argument("--expanded-dir", default=str(default_expanded_transfer_dir()))
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--no-retune", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--held", action="append", default=None)
    args = ap.parse_args(argv)
    report = run_matrix_ab(
        expanded_dir=Path(args.expanded_dir),
        helds=list(args.held) if args.held else None,
        top_k=int(args.top_k),
        retune=not bool(args.no_retune),
        out=Path(args.out) if args.out else None,
    )
    print(json.dumps({k: report[k] for k in ("delta", "conclusion", "paths")}, indent=2))
    return 0 if report.get("baseline", {}).get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
