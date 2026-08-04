# -*- coding: utf-8 -*-
"""Batch-score one held RBP's test FASTA against all (or selected) heads.

Designed to run inside the ``rhobind`` conda env (torch + release package).
Encode each sequence batch once, then apply every head — far faster than
per-RNA ``rhobind_predict`` subprocess loops.

Usage (inside rhobind env)::

    python -m rbp_eval.loo.batch_score_held \\
        --release $RHOBIND_RELEASE --cohort K562 --held PTBP1 \\
        --fasta .../PTBP1/test.fasta --max-seqs 256 --out /tmp/held.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from pathlib import Path
from typing import Any, Optional


def _average_precision(y_true: list[int], y_score: list[float]) -> float:
    try:
        from sklearn.metrics import average_precision_score

        return float(average_precision_score(y_true, y_score))
    except Exception:
        pairs = sorted(zip(y_score, y_true), key=lambda t: t[0], reverse=True)
        hits = 0
        ap_sum = 0.0
        pos = sum(y_true)
        if pos == 0:
            return 0.0
        for i, (_s, y) in enumerate(pairs, start=1):
            if y:
                hits += 1
                ap_sum += hits / i
        return ap_sum / pos


def _auroc(y_true: list[int], y_score: list[float]) -> float:
    try:
        from sklearn.metrics import roc_auc_score

        if len(set(y_true)) < 2:
            return float("nan")
        return float(roc_auc_score(y_true, y_score))
    except Exception:
        pos = [s for s, y in zip(y_score, y_true) if y == 1]
        neg = [s for s, y in zip(y_score, y_true) if y == 0]
        if not pos or not neg:
            return float("nan")
        wins = 0.0
        for p in pos:
            for n in neg:
                if p > n:
                    wins += 1.0
                elif p == n:
                    wins += 0.5
        return wins / (len(pos) * len(neg))


def parse_fasta_labeled(path: Path) -> list[tuple[str, int]]:
    """Return (dna/rna seq with T, label) — RhoBind expects T not U."""
    text = path.read_text(encoding="utf-8", errors="replace")
    entries: list[tuple[str, int]] = []
    header = ""
    seq_parts: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if header and seq_parts:
                seq = "".join(seq_parts).upper().replace("U", "T")
                lab = 0 if header.upper().startswith(">NEG") else 1
                entries.append((seq, lab))
            header = line
            seq_parts = []
        else:
            seq_parts.append(line.strip())
    if header and seq_parts:
        seq = "".join(seq_parts).upper().replace("U", "T")
        lab = 0 if header.upper().startswith(">NEG") else 1
        entries.append((seq, lab))
    return entries


def subsample(
    entries: list[tuple[str, int]],
    max_seqs: int,
    *,
    seed: int = 42,
) -> list[tuple[str, int]]:
    if max_seqs <= 0 or len(entries) <= max_seqs:
        return entries
    pos = [e for e in entries if e[1] == 1]
    neg = [e for e in entries if e[1] == 0]
    rng = random.Random(seed)
    half = max(1, max_seqs // 2)
    take_pos = pos if len(pos) <= half else rng.sample(pos, half)
    rem = max_seqs - len(take_pos)
    take_neg = neg if len(neg) <= rem else rng.sample(neg, rem)
    out = take_pos + take_neg
    rng.shuffle(out)
    return out


def resolve_release_paths(release: Path, cohort: str) -> dict[str, Path]:
    release = Path(release).expanduser().resolve()
    c = cohort.lower()
    if c == "hepg2":
        ckpt = release / "checkpoints" / "rhobind_hepg2_mt_all118_cutoff08.ckpt"
        hi = release / "checkpoints" / "head_index_hepg2.json"
    else:
        ckpt = release / "checkpoints" / "rhobind_k562_mt_all118_cutoff08.ckpt"
        hi = release / "checkpoints" / "head_index_k562.json"
    return {"release": release, "checkpoint": ckpt, "head_index": hi}


def predict_all_heads(
    model: Any,
    seqs: list[str],
    *,
    device: str,
    batch_size: int = 64,
    max_len: int = 128,
) -> Any:
    """Encode once per batch; return probs array shape [n_seq, n_tasks]."""
    import numpy as np
    import torch

    model.eval()
    n_tasks = len(model.heads)
    chunks: list[Any] = []
    with torch.no_grad():
        for i in range(0, len(seqs), batch_size):
            batch = seqs[i : i + batch_size]
            enc = model.encoder.tokenize(batch, max_len=max_len)
            enc = {k: v.to(device) for k, v in enc.items()}
            hs, mask = model.encoder(**enc)
            cols = []
            for tid in range(n_tasks):
                logit = model.heads[tid](hs, mask).squeeze(-1)
                cols.append(torch.sigmoid(logit).float().cpu())
            # [n_batch, n_tasks]
            chunks.append(torch.stack(cols, dim=1).numpy())
    return np.concatenate(chunks, axis=0) if chunks else np.zeros((0, n_tasks))


def score_held_fasta(
    *,
    release: Path,
    cohort: str,
    held: str,
    fasta: Path,
    foreigns: Optional[list[str]] = None,
    max_seqs: int = 256,
    device: str = "cuda",
    batch_size: int = 64,
    seed: int = 42,
) -> dict[str, Any]:
    """Score held FASTA with all heads; return metrics rows + summary."""
    import torch

    paths = resolve_release_paths(release, cohort)
    if not paths["checkpoint"].is_file():
        return {"ok": False, "reason": f"missing checkpoint {paths['checkpoint']}"}
    if not paths["head_index"].is_file():
        return {"ok": False, "reason": f"missing head_index {paths['head_index']}"}
    if not Path(fasta).is_file():
        return {"ok": False, "reason": f"missing fasta {fasta}"}

    sys.path.insert(0, str(paths["release"]))
    from rhobind.model import load_rhobind  # type: ignore  # noqa: E402

    entries = parse_fasta_labeled(Path(fasta))
    used = subsample(entries, max_seqs, seed=seed)
    if len(used) < 4 or sum(y for _, y in used) == 0:
        return {"ok": False, "reason": f"insufficient labeled seqs for {held}"}

    seqs = [s for s, _ in used]
    labels = [y for _, y in used]
    dev = device if (device == "cpu" or torch.cuda.is_available()) else "cpu"
    model, hi = load_rhobind(
        paths["checkpoint"], paths["head_index"], device=dev
    )
    alias_to_head: dict[str, int] = dict(hi.get("alias_to_head") or {})
    order: list[str] = list(hi.get("order") or [])
    if not order and alias_to_head:
        # reconstruct order by head index
        rev = sorted(alias_to_head.items(), key=lambda kv: kv[1])
        order = [a for a, _ in rev]

    probs = predict_all_heads(
        model, seqs, device=dev, batch_size=batch_size
    )

    want = list(foreigns) if foreigns is not None else [a for a in order if a != held]
    metrics_rows: list[dict[str, str]] = []
    foreign_auprcs: list[tuple[str, float]] = []
    per_alias_probs: dict[str, list[float]] = {}

    for alias in want + ([held] if held not in want else []):
        tid = alias_to_head.get(alias)
        if tid is None or tid >= probs.shape[1]:
            continue
        scores = [float(probs[i, tid]) for i in range(len(labels))]
        per_alias_probs[alias] = scores
        if alias == held:
            continue
        if sum(labels) == 0:
            continue
        ap = _average_precision(labels, scores)
        ar = _auroc(labels, scores)
        foreign_auprcs.append((alias, ap))
        metrics_rows.append(
            {
                "held_rbp": held,
                "foreign_rbp": alias,
                "auprc": f"{ap:.5f}",
                "auroc": f"{ar:.5f}" if math.isfinite(ar) else "",
            }
        )

    if not metrics_rows:
        return {"ok": False, "reason": f"no foreign AUPRC for {held}"}

    foreign_auprcs.sort(key=lambda t: t[1], reverse=True)
    best_f, best_a = foreign_auprcs[0]
    mean_a = sum(a for _, a in foreign_auprcs) / len(foreign_auprcs)
    own_a = None
    if held in per_alias_probs:
        own_a = _average_precision(labels, per_alias_probs[held])

    summary = {
        "held_rbp": held,
        "n_in_train": str(len(want)),
        "own_full_auprc": "" if own_a is None else f"{own_a:.5f}",
        "best_foreign_rbp": best_f,
        "best_foreign_auprc": f"{best_a:.5f}",
        "mean_foreign_auprc": f"{mean_a:.5f}",
        "single_task_auprc": "",
        "gap_full_minus_best_foreign": "" if own_a is None else f"{own_a - best_a:.5f}",
        "median_rest_delta_auprc": "",
        "mean_rest_delta_auprc": "",
    }
    return {
        "ok": True,
        "held_rbp": held,
        "cohort": cohort,
        "n_used": len(used),
        "n_foreign_scored": len(metrics_rows),
        "metrics_rows": metrics_rows,
        "summary": summary,
        "labels": labels,
        "own_probs": per_alias_probs.get(held),
        "donor_probs": {a: per_alias_probs[a] for a in want if a in per_alias_probs},
        "test_fasta": str(fasta),
        "device": dev,
    }


def score_donors_on_fasta(
    *,
    release: Path,
    cohort: str,
    held: str,
    fasta: Path,
    donors: list[str],
    max_seqs: int = 64,
    device: str = "cuda",
    batch_size: int = 64,
    seed: int = 42,
    aggregate: str = "max",
) -> dict[str, Any]:
    """Score held FASTA with donor heads only; return per-seq fused p_hat + labels."""
    full = score_held_fasta(
        release=release,
        cohort=cohort,
        held=held,
        fasta=fasta,
        foreigns=list(donors),
        max_seqs=max_seqs,
        device=device,
        batch_size=batch_size,
        seed=seed,
    )
    if not full.get("ok"):
        return full
    labels: list[int] = list(full["labels"])
    donor_probs: dict[str, list[float]] = full.get("donor_probs") or {}
    pairs: list[dict[str, Any]] = []
    for i, y in enumerate(labels):
        vals = [donor_probs[d][i] for d in donors if d in donor_probs and i < len(donor_probs[d])]
        if not vals:
            continue
        if aggregate == "mean":
            p = sum(vals) / len(vals)
        else:
            p = max(vals)
        pairs.append({"p_hat": float(p), "y": int(y), "score": float(p)})
    ys = [p["y"] for p in pairs]
    ss = [p["p_hat"] for p in pairs]
    recovered = _average_precision(ys, ss) if ys and sum(ys) > 0 else None
    own_a = None
    if full.get("own_probs") and labels:
        own_a = _average_precision(labels, list(full["own_probs"]))
    return {
        "ok": True,
        "held_rbp": held,
        "donors": list(donors),
        "pairs": pairs,
        "n_scored": len(pairs),
        "recovered_auprc": recovered,
        "own_full_auprc": own_a,
        "gap_to_ceiling": None
        if recovered is None or own_a is None
        else float(own_a) - float(recovered),
        "n_used": full.get("n_used"),
        "test_fasta": full.get("test_fasta"),
    }


def _rhobind_python() -> str:
    return (
        os.environ.get("RHOBIND_PYTHON")
        or os.environ.get("RBP_RHOBIND_PYTHON")
        or ""
    ).strip()


def run_batch_score_subprocess(
    *,
    held: str,
    cohort: str,
    fasta: Path,
    release: Path,
    foreigns: Optional[list[str]] = None,
    max_seqs: int = 256,
    device: str = "cuda",
    batch_size: int = 64,
    seed: int = 42,
    out_json: Optional[Path] = None,
    donors_only: bool = False,
) -> dict[str, Any]:
    """Invoke this module in rhobind env; return parsed JSON report."""
    import subprocess
    import tempfile

    py = _rhobind_python()
    if not py:
        # Prefer conda run
        conda = os.environ.get("CONDA_EXE") or "conda"
        cmd_prefix = [conda, "run", "-n", "rhobind", "--no-capture-output", "python"]
    else:
        cmd_prefix = [py]

    pkg_root = Path(__file__).resolve().parents[2]  # nanobot-bio
    out_path = Path(out_json) if out_json else Path(
        tempfile.mkstemp(prefix=f"loo_held_{held}_", suffix=".json")[1]
    )
    cmd = [
        *cmd_prefix,
        "-m",
        "rbp_eval.loo.batch_score_held",
        "--release",
        str(release),
        "--cohort",
        cohort,
        "--held",
        held,
        "--fasta",
        str(fasta),
        "--max-seqs",
        str(max_seqs),
        "--device",
        device,
        "--batch-size",
        str(batch_size),
        "--seed",
        str(seed),
        "--out",
        str(out_path),
    ]
    if foreigns:
        for f in foreigns:
            cmd.extend(["--foreign", f])
    if donors_only:
        cmd.append("--donors-only")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(pkg_root) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    proc = subprocess.run(
        cmd,
        cwd=str(pkg_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=7200,
    )
    if proc.returncode != 0 and not out_path.is_file():
        return {
            "ok": False,
            "reason": (
                f"batch_score_held failed rc={proc.returncode}: "
                f"{(proc.stderr or proc.stdout or '')[-800:]}"
            ),
        }
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "reason": f"failed to read batch score output: {e}; stderr={(proc.stderr or '')[-400:]}",
        }
    return data


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Batch LOO held×all-heads scorer")
    ap.add_argument("--release", required=True)
    ap.add_argument("--cohort", default="K562")
    ap.add_argument("--held", required=True)
    ap.add_argument("--fasta", required=True)
    ap.add_argument("--foreign", action="append", default=None)
    ap.add_argument("--max-seqs", type=int, default=256)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--donors-only",
        action="store_true",
        help="With --foreign: also emit fused donor pairs (for scored val)",
    )
    args = ap.parse_args(argv)

    if args.donors_only and args.foreign:
        report = score_donors_on_fasta(
            release=Path(args.release),
            cohort=args.cohort,
            held=args.held,
            fasta=Path(args.fasta),
            donors=list(args.foreign),
            max_seqs=int(args.max_seqs),
            device=str(args.device),
            batch_size=int(args.batch_size),
            seed=int(args.seed),
        )
    else:
        report = score_held_fasta(
            release=Path(args.release),
            cohort=args.cohort,
            held=args.held,
            fasta=Path(args.fasta),
            foreigns=list(args.foreign) if args.foreign else None,
            max_seqs=int(args.max_seqs),
            device=str(args.device),
            batch_size=int(args.batch_size),
            seed=int(args.seed),
        )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Drop bulky per-seq arrays from matrix expand outputs unless donors-only
    slim = dict(report)
    if not args.donors_only:
        slim.pop("labels", None)
        slim.pop("own_probs", None)
        slim.pop("donor_probs", None)
    out.write_text(json.dumps(slim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": slim.get("ok"), "out": str(out), "held": args.held}, ensure_ascii=False))
    return 0 if slim.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
