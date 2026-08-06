# -*- coding: utf-8 -*-
"""A2: optional phmmer remote-homology axis (wraps the hmmer `phmmer` binary).

This is an OPTIONAL Stage-1 retrieve axis for distant homology — more sensitive
than MMseqs/BLAST for remote protein relationships. It is NOT mounted by default
(adds latency + needs hmmer installed); opt in via ``RBP_PHMMER=1``.

Delivery is untouched: this tool only shells out to the ``phmmer`` binary and
builds a target FASTA from the catalogue registry (same facade the curated
seq_similarity uses).

CLI examples:
  RBP_PHMMER=1 nanobot-bio agent --force-transfer --query SOME_RBP --rna-file path/to/rna.txt
  nanobot-bio doctor
  nanobot-bio chat
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from nanobot.agent.tools.core.base import Tool, tool_parameters
from nanobot.agent.tools.rbp.common import (
    dumps,
    err,
    get_delivery_client,
    looks_like_rna,
    ok,
    resolve_protein_sequence,
    timed_call,
)


def _phmmer_binary() -> str | None:
    return shutil.which("phmmer")


def _catalogue_fasta(client: Any, *, cache_dir: Path) -> Path:
    """Build (and cache) a target FASTA of catalogue RBP sequences.

    Cached under ``cache_dir/catalogue_phmmer_target.fasta``; rebuilt when the
    registry size changes (coarse freshness). Delivery registry is read-only.
    """
    from nanobot.agent.tools.rbp.common import (
        apply_delivery_env_facade,
        load_catalogue_sequence,
        load_rbp_registry_facade,
    )

    apply_delivery_env_facade()
    reg = load_rbp_registry_facade()
    cache_dir.mkdir(parents=True, exist_ok=True)
    fasta = cache_dir / "catalogue_phmmer_target.fasta"
    stamp = cache_dir / "catalogue_phmmer_target.n"
    n = len(reg)
    if fasta.is_file() and stamp.is_file():
        try:
            if int(stamp.read_text().strip()) == n:
                return fasta
        except ValueError:
            pass
    lines: list[str] = []
    for up, rec in reg.items():
        if not isinstance(rec, dict):
            continue
        alias = str(rec.get("alias") or up)
        seq = load_catalogue_sequence(alias) or load_catalogue_sequence(str(up)) or ""
        if not seq or len(seq) < 20:
            continue
        lines.append(f">{alias}_{up}")
        for i in range(0, len(seq), 70):
            lines.append(seq[i : i + 70])
    fasta.write_text("\n".join(lines) + "\n", encoding="utf-8")
    stamp.write_text(str(n), encoding="utf-8")
    return fasta


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "sequence": {"type": "string"},
            "alias": {"type": "string"},
            "uniprot": {"type": "string"},
            "top_k": {"type": "integer", "default": 10},
            "evalue": {"type": "number", "default": 1.0},
        },
        "required": [],
    }
)
class PhmmerSimilarityTool(Tool):
    """Optional Stage-1 remote-homology axis (hmmer phmmer; off unless RBP_PHMMER=1)."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "phmmer_similarity"

    @property
    def description(self) -> str:
        return (
            "OPTIONAL remote-homology axis (phmmer). More sensitive than MMseqs for "
            "distant protein relationships; slow (needs hmmer installed). Default off "
            "(opt in via RBP_PHMMER=1). Protein AA only; never pass RNA."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        try:
            from nanobot.agent.tools.rbp.turn_guards import blocked_envelope_json

            blocked = blocked_envelope_json(self.name)
            if blocked:
                return blocked
        except Exception:
            pass
        bin_path = _phmmer_binary()
        if not bin_path:
            return dumps(
                err(
                    "phmmer binary not found on PATH; install hmmer (conda: "
                    "`conda install -c bioconda hmmer`) or keep this axis off "
                    "(RBP_PHMMER unset)."
                )
            )
        raw = (kwargs.get("sequence") or "").strip()
        if raw and looks_like_rna(raw):
            return dumps(err("sequence looks like RNA; pass a protein AA sequence"))
        seq, src = resolve_protein_sequence(kwargs)
        if not seq or len(seq) < 20:
            return dumps(
                err(
                    "need alias/uniprot or a protein AA sequence ≥20; phmmer cannot "
                    "run on a placeholder"
                )
            )

        top_k = int(kwargs.get("top_k") or 10)
        evalue = float(kwargs.get("evalue") or 1.0)

        def _run() -> dict[str, Any]:
            client = get_delivery_client(offline=True)
            # Cache the target FASTA under the structure cache dir (already on disk).
            from app.core.paths import CACHE, ensure_artifact_dirs

            ensure_artifact_dirs()
            target = _catalogue_fasta(client, cache_dir=CACHE)

            with tempfile.TemporaryDirectory() as td:
                tdp = Path(td)
                query_fa = tdp / "query.fasta"
                query_fa.write_text(f">query\n{seq}\n", encoding="utf-8")
                domtbl = tdp / "out.domtblout"
                cmd = [
                    bin_path,
                    "--noali",
                    "-E", str(evalue),
                    "--domtblout", str(domtbl),
                    str(query_fa),
                    str(target),
                ]
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120
                )
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"phmmer failed (rc={proc.returncode}): "
                        f"{(proc.stderr or proc.stdout or '')[:300]}"
                    )
                hits = _parse_domtblout(domtbl, top_k=top_k)
            return {
                "hits": hits,
                "hits_phmmer": hits,
                "meta": {
                    "sequence_source": src,
                    "seq_len": len(seq),
                    "axis": "phmmer",
                    "evalue": evalue,
                    "n_hits": len(hits),
                },
            }

        out, ms, error = await asyncio.to_thread(lambda: timed_call(_run))
        if error is not None:
            return dumps(err(error, ms))
        if isinstance(out, dict):
            out["latency_ms"] = round(float(ms or 0.0), 3)
        return dumps(ok(out, ms))


def _parse_domtblout(path: Path, *, top_k: int) -> list[dict[str, Any]]:
    """Parse hmmer domtblout into ranked RbpHit-shaped dicts."""
    hits: list[dict[str, Any]] = []
    if not path.is_file():
        return hits
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 23:
            continue
        # target_name acc tlen query_name acc qlen e-value score bias ...
        target_name = parts[0]
        evalue = float(parts[6]) if parts[6] != "-" else None
        score = float(parts[7]) if parts[7] != "-" else None
        # target_name is "<ALIAS>_<UNIPROT>"
        alias = target_name
        uniprot = ""
        if "_" in target_name:
            alias, _, uniprot = target_name.partition("_")
        hits.append(
            {
                "alias": alias,
                "uniprot": uniprot,
                "score": score,
                "evalue": evalue,
                "metric": "phmmer_score",
            }
        )
    hits.sort(key=lambda h: (h.get("evalue") or float("inf")))
    return hits[:top_k]


__all__ = ["PhmmerSimilarityTool"]
