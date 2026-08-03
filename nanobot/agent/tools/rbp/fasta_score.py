# -*- coding: utf-8 -*-
"""score_binding_fasta — allowlisted FASTA path → batch own-head scores + AUPRC."""

from __future__ import annotations

import asyncio
import csv
import os
import random
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from nanobot.agent.tools.core.base import Tool, tool_parameters

from nanobot.agent.tools.rbp.common import dumps, err, get_delivery_client, ok, resolve_device
from nanobot.agent.tools.rbp.path_guard import resolve_allowed_path


def parse_fasta_records(path: Path) -> list[tuple[str, str]]:
    """Return list of (header_without_gt, sequence)."""
    out: list[tuple[str, str]] = []
    header: Optional[str] = None
    buf: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    out.append((header, "".join(buf)))
                header, buf = line[1:], []
            else:
                buf.append(line.strip())
    if header is not None:
        out.append((header, "".join(buf)))
    return out


def label_of(header: str) -> int:
    return 0 if (header or "").startswith("NEG") else 1


def _artifacts_csv_dir() -> Path:
    try:
        from app.core.paths import ensure_artifact_dirs
        from app.core import paths as P

        ensure_artifact_dirs()
        d = getattr(P, "REPORTS_CSV", None) or (P.ARTIFACTS / "reports" / "csv")
        d = Path(d)
        d.mkdir(parents=True, exist_ok=True)
        return d
    except Exception:
        d = Path("artifacts/reports/csv")
        d.mkdir(parents=True, exist_ok=True)
        return d


def _release_dir() -> Optional[Path]:
    try:
        from nanobot.agent.tools.rbp.common import ensure_nanobot_bio_on_path

        ensure_nanobot_bio_on_path()
        from app.backends.delivery.env import resolve_delivery_paths

        p = Path(resolve_delivery_paths()["rhobind_release"]).expanduser()
        return p if p.is_dir() else None
    except Exception:
        raw = os.environ.get("RHOBIND_RELEASE")
        if not raw:
            return None
        p = Path(raw).expanduser()
        return p if p.is_dir() else None


def _rhobind_python() -> Optional[Path]:
    try:
        from app.backends.delivery.env import conda_env_python

        py = conda_env_python("rhobind")
        if py and Path(py).is_file():
            return Path(py)
    except Exception:
        pass
    return None


def _score_via_infer(
    *,
    fasta: Path,
    rbp: str,
    cohort: str,
    device: str,
    batch_size: int,
    out_csv: Path,
) -> Optional[dict[str, Any]]:
    """Fast path: release infer.py (loads model once)."""
    release = _release_dir()
    py = _rhobind_python()
    if release is None or py is None:
        return None
    ckpt_name = (
        "rhobind_k562_mt_all118_cutoff08.ckpt"
        if cohort.upper() == "K562"
        else "rhobind_hepg2_mt_all118_cutoff08.ckpt"
    )
    hi_name = (
        "head_index_k562.json" if cohort.upper() == "K562" else "head_index_hepg2.json"
    )
    ckpt = release / "checkpoints" / ckpt_name
    hi = release / "checkpoints" / hi_name
    infer = release / "infer.py"
    if not (ckpt.is_file() and hi.is_file() and infer.is_file()):
        return None
    cmd = [
        str(py),
        str(infer),
        "--checkpoint",
        str(ckpt),
        "--head_index",
        str(hi),
        "--rbp",
        rbp,
        "--fasta",
        str(fasta),
        "--out",
        str(out_csv),
        "--device",
        device,
        "--batch_size",
        str(int(batch_size)),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(release),
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if proc.returncode != 0:
        return {
            "error": (proc.stderr or proc.stdout or "infer.py failed")[:800],
            "engine": "infer.py",
        }
    # Parse metrics line
    auprc = auroc = None
    n = n_pos = None
    for line in (proc.stdout or "").splitlines():
        if "[infer]" in line and "AUPRC=" in line:
            m = re.search(
                r"n=(\d+).*?pos=(\d+).*?AUPRC=([0-9.]+).*?AUROC=([0-9.]+)",
                line,
            )
            if m:
                n, n_pos = int(m.group(1)), int(m.group(2))
                auprc, auroc = float(m.group(3)), float(m.group(4))
            break
    rows = _load_pred_csv(out_csv)
    summary = _summarize_rows(rows, rbp=rbp, cohort=cohort, preds_csv=out_csv)
    summary["engine"] = "infer.py"
    if auprc is not None:
        summary["auprc"] = auprc
        summary["auroc"] = auroc
    if n is not None:
        summary["n"] = n
    if n_pos is not None:
        summary["n_pos"] = n_pos
        summary["n_neg"] = int(summary.get("n") or 0) - n_pos
    return summary


def _load_pred_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(
                {
                    "header": r.get("header") or "",
                    "label": int(r.get("label") or 0),
                    "prob": float(r.get("prob") or 0.0),
                }
            )
    return rows


def _summarize_rows(
    rows: list[dict[str, Any]],
    *,
    rbp: str,
    cohort: str,
    preds_csv: Path,
) -> dict[str, Any]:
    from rbp_eval.scoring.metrics import average_precision, roc_auc

    n = len(rows)
    labels = [int(r["label"]) for r in rows]
    probs = [float(r["prob"]) for r in rows]
    n_pos = sum(labels)
    n_neg = n - n_pos
    pos_probs = [p for p, y in zip(probs, labels) if y == 1]
    neg_probs = [p for p, y in zip(probs, labels) if y == 0]
    auprc = average_precision(probs, labels) if n_pos and n_neg else None
    auroc = roc_auc(probs, labels) if n_pos and n_neg else None

    # Sample hard cases for the LLM (not full file)
    neg_hi = sorted(
        (r for r in rows if int(r["label"]) == 0),
        key=lambda r: float(r["prob"]),
        reverse=True,
    )[:5]
    pos_lo = sorted(
        (r for r in rows if int(r["label"]) == 1),
        key=lambda r: float(r["prob"]),
    )[:5]
    samples = {
        "high_score_neg": [
            {"header": r["header"][:120], "prob": round(float(r["prob"]), 6)}
            for r in neg_hi
        ],
        "low_score_pos": [
            {"header": r["header"][:120], "prob": round(float(r["prob"]), 6)}
            for r in pos_lo
        ],
    }
    return {
        "ok": True,
        "rbp": rbp,
        "cohort": cohort,
        "n": n,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "auprc": None if auprc is None else round(float(auprc), 4),
        "auroc": None if auroc is None else round(float(auroc), 4),
        "mean_prob_pos": (
            None if not pos_probs else round(sum(pos_probs) / len(pos_probs), 6)
        ),
        "mean_prob_neg": (
            None if not neg_probs else round(sum(neg_probs) / len(neg_probs), 6)
        ),
        "preds_csv": str(preds_csv),
        "samples": samples,
        "labeled": bool(n_pos and n_neg),
    }


def _score_via_delivery(
    *,
    records: list[tuple[str, str]],
    rbp: str,
    cohort: str,
    device: str,
    out_csv: Path,
) -> dict[str, Any]:
    """Fallback: one rhobind_predict call per sequence (slower)."""
    client = get_delivery_client(offline=False, device=device, use_conda=True)
    rows: list[dict[str, Any]] = []
    errors = 0
    for header, seq in records:
        lab = label_of(header)
        out = client.call(
            "rhobind_predict",
            {
                "rna": seq,
                "rbps": [rbp],
                "cohort": cohort.upper() if cohort.upper() in ("K562", "HEPG2") else "K562",
                "device": device,
                "aggregate": "max",
                "timeout_s": 300,
            },
        )
        prob = None
        for p in out.get("predictions") or []:
            if str(p.get("alias") or "") == rbp and p.get("prob") is not None:
                prob = float(p["prob"])
                break
        if prob is None:
            errors += 1
            continue
        rows.append({"header": header, "label": lab, "prob": prob})

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["header", "label", "prob"])
        for r in rows:
            w.writerow([r["header"], int(r["label"]), f"{r['prob']:.6f}"])

    summary = _summarize_rows(rows, rbp=rbp, cohort=cohort, preds_csv=out_csv)
    summary["engine"] = "rhobind_predict"
    summary["n_errors"] = errors
    return summary


def run_fasta_score(
    *,
    path: str | Path,
    rbp: str,
    cohort: str = "K562",
    batch_size: int = 64,
    max_seqs: Optional[int] = None,
    device: Optional[str] = None,
    seed: int = 42,
    prefer_infer: bool = True,
) -> dict[str, Any]:
    """Score an allowlisted FASTA for one in-panel RBP; return metrics summary."""
    alias = (rbp or "").strip()
    if not alias:
        return {"ok": False, "error": "rbp/query required"}
    try:
        fasta = resolve_allowed_path(
            path,
            allowed_suffixes={".fasta", ".fa", ".fna", ".faa"},
        )
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    records = parse_fasta_records(fasta)
    if not records:
        return {"ok": False, "error": f"empty FASTA: {fasta}"}
    if max_seqs is not None and int(max_seqs) > 0 and len(records) > int(max_seqs):
        rng = random.Random(int(seed))
        records = rng.sample(list(records), int(max_seqs))

    dev = resolve_device(device)
    cohort_u = cohort.upper() if str(cohort).upper() in ("K562", "HEPG2") else "K562"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_csv = _artifacts_csv_dir() / f"{alias}_{cohort_u}_fasta_score_{stamp}.csv"

    # Subsample → must use delivery loop (infer.py scores whole file as-is).
    # Full file → prefer infer.py for speed / expected_metrics parity.
    use_infer = prefer_infer and (max_seqs is None or int(max_seqs) <= 0 or int(max_seqs) >= len(parse_fasta_records(fasta)))
    # Re-parse length before subsample for gate:
    n_full = len(parse_fasta_records(fasta)) if max_seqs else len(records)
    if prefer_infer and (max_seqs is None or int(max_seqs) <= 0 or int(max_seqs) >= n_full):
        # Write temp fasta only if we subsampled — else pass original path
        fasta_for_infer = fasta
        if len(records) < n_full:
            use_infer = False
        else:
            use_infer = True
            result = _score_via_infer(
                fasta=fasta_for_infer,
                rbp=alias,
                cohort=cohort_u,
                device=dev,
                batch_size=int(batch_size) or 64,
                out_csv=out_csv,
            )
            if result is not None and result.get("ok"):
                result["path"] = str(fasta)
                return result
            if result is not None and result.get("error") and not result.get("ok"):
                # fall through to delivery
                pass

    # If subsampled or infer unavailable:
    if max_seqs is not None and int(max_seqs) > 0:
        # Write subsampled fasta for clarity / delivery path
        pass
    summary = _score_via_delivery(
        records=records,
        rbp=alias,
        cohort=cohort_u,
        device=dev,
        out_csv=out_csv,
    )
    summary["path"] = str(fasta)
    return summary


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or allowlisted path to a .fasta/.fa file",
            },
            "rbp": {
                "type": "string",
                "description": "RBP alias with a catalogue head (e.g. FXR2)",
            },
            "query": {
                "type": "string",
                "description": "Alias for rbp (same meaning)",
            },
            "cohort": {"type": "string", "default": "K562"},
            "batch_size": {"type": "integer", "default": 64},
            "max_seqs": {
                "type": "integer",
                "description": "Optional subsample cap for quick runs",
            },
            "device": {"type": "string", "default": "auto"},
        },
        "required": ["path"],
    }
)
class ScoreBindingFastaTool(Tool):
    """Batch own-head score for a labeled FASTA path (AUPRC when POS+NEG)."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "score_binding_fasta"

    @property
    def description(self) -> str:
        return (
            "Score an allowlisted FASTA file for one in-panel RBP (own-head). "
            "Paste a local .fasta/.fa path. Headers starting with NEG are negatives; "
            "others positive. Returns AUPRC/AUROC summary + CSV path — does NOT dump "
            "all sequences into chat. Not general read_file."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        path = (kwargs.get("path") or "").strip()
        rbp = (kwargs.get("rbp") or kwargs.get("query") or "").strip()
        if not path:
            return dumps(err("path required"))
        if not rbp:
            return dumps(err("rbp or query required (in-panel alias)"))
        max_seqs = kwargs.get("max_seqs")
        try:
            max_i = int(max_seqs) if max_seqs is not None else None
        except (TypeError, ValueError):
            max_i = None

        def _run() -> dict[str, Any]:
            return run_fasta_score(
                path=path,
                rbp=rbp,
                cohort=str(kwargs.get("cohort") or "K562"),
                batch_size=int(kwargs.get("batch_size") or 64),
                max_seqs=max_i,
                device=kwargs.get("device"),
            )

        out, ms, error = await asyncio.to_thread(
            lambda: __import__(
                "nanobot.agent.tools.rbp.common", fromlist=["timed_call"]
            ).timed_call(_run)
        )
        if error:
            return dumps(err(str(error), ms or 0.0))
        if not isinstance(out, dict):
            return dumps(err("score_binding_fasta returned no payload", ms or 0.0))
        if out.get("ok") is False or out.get("error"):
            return dumps(err(str(out.get("error") or "score failed"), ms or 0.0))
        return dumps(ok(out, ms or 0.0))


__all__ = [
    "ScoreBindingFastaTool",
    "run_fasta_score",
    "parse_fasta_records",
    "label_of",
]
