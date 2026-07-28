# -*- coding: utf-8 -*-
"""P0 tool — seq_similarity → delivery esm_similarity (+ protein_seq_similarity).

Final delivery: always expose dual axes ``hits_emb`` + ``hits_seq`` when
``parallel_retrieve`` is on (default). ``hits`` remains the merged list for
backward-compatible fuse callers.
"""

from __future__ import annotations

import asyncio
from typing import Any

from nanobot.agent.tools.core.base import Tool, tool_parameters

from nanobot.agent.tools.rbp.common import (
    dumps,
    err,
    get_delivery_client,
    looks_like_rna,
    ok,
    resolve_device,
    resolve_protein_sequence,
    timed_call,
)


def _parallel_retrieve_default() -> bool:
    try:
        from nanobot.agent.tools.rbp.common import get_runtime_config

        return bool(get_runtime_config().get("parallel_retrieve", True))
    except Exception:
        return True


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "sequence": {
                "type": "string",
                "description": "Protein AA sequence (≥20). Do NOT pass UniProt/alias here.",
            },
            "target_sequence": {
                "type": "string",
                "description": "Alias of sequence; UniProt/gene IDs are auto-resolved from catalogue.",
            },
            "uniprot": {
                "type": "string",
                "description": "Preferred: load AA seq from catalogue FASTA (e.g. O43251).",
            },
            "alias": {
                "type": "string",
                "description": "Preferred: gene symbol (e.g. RBFOX2) → catalogue FASTA.",
            },
            "query": {
                "type": "string",
                "description": "Alias or UniProt if sequence omitted.",
            },
            "encoder": {"type": "string", "default": "esmc"},
            "device": {
                "type": "string",
                "enum": ["auto", "cuda", "cpu"],
                "default": "auto",
                "description": "Prefer cuda when available (ESM-C / HANDOFF)",
            },
            "top_k": {"type": "integer", "default": 10},
            "also_mmseqs": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Also run protein_seq_similarity (MMseqs). Default true when "
                    "parallel_retrieve is on — yields hits_emb + hits_seq."
                ),
            },
            "parallel_retrieve": {
                "type": "boolean",
                "description": "Override config parallel_retrieve (dual seq axes).",
            },
        },
        "required": [],
    }
)
class SeqSimilarityTool(Tool):
    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "seq_similarity"

    @property
    def description(self) -> str:
        return (
            "Dual-axis sequence similarity vs catalogue: hits_emb (ESM-C) + "
            "hits_seq (MMseqs identity). Prefer alias=/uniprot=. "
            "Pass hits_emb into confidence_abstain; fuse both axes. "
            "Protein AA only; never pass RNA."
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
        raw = (kwargs.get("sequence") or kwargs.get("target_sequence") or "").strip()
        if raw and looks_like_rna(raw):
            return dumps(
                err(
                    "sequence looks like RNA; pass alias/uniprot for the protein, "
                    "or a real AA sequence"
                )
            )
        seq, src = resolve_protein_sequence(kwargs)
        if not seq:
            from nanobot.agent.tools.rbp.common import not_in_catalogue_hint

            ids = [
                str(kwargs.get(k))
                for k in ("alias", "uniprot", "query", "rbp_id")
                if kwargs.get(k)
            ]
            return dumps(
                err(
                    not_in_catalogue_hint(*ids)
                    + " Or pass protein AA `sequence` ≥20 explicitly."
                )
            )

        def _run():
            device = resolve_device(kwargs.get("device"))
            client = get_delivery_client(device=device)
            parallel = kwargs.get("parallel_retrieve")
            if parallel is None:
                parallel = _parallel_retrieve_default()
            also_mmseqs = kwargs.get("also_mmseqs")
            if also_mmseqs is None:
                also_mmseqs = bool(parallel)
            else:
                also_mmseqs = bool(also_mmseqs)

            hits_emb: list[Any] = []
            hits_seq: list[Any] = []
            meta: dict[str, Any] = {
                "sequence_source": src,
                "seq_len": len(seq),
                "parallel_retrieve": bool(parallel),
            }
            esm = client.call(
                "esm_similarity",
                {
                    "sequence": seq,
                    "encoder": kwargs.get("encoder") or "esmc",
                    "device": device,
                    "top_k": int(kwargs.get("top_k") or 10),
                    "uniprot": kwargs.get("uniprot"),
                },
            )
            meta["esm"] = {
                "error": esm.get("error"),
                "script": esm.get("_script"),
                "invocation": esm.get("_invocation"),
            }
            if esm.get("hits"):
                hits_emb = list(esm["hits"])

            run_mmseqs = bool(also_mmseqs) or (not hits_emb and esm.get("error"))
            if run_mmseqs:
                mm = client.call(
                    "protein_seq_similarity",
                    {"sequence": seq, "top_k": int(kwargs.get("top_k") or 10)},
                )
                meta["mmseqs"] = {
                    "error": mm.get("error"),
                    "script": mm.get("_script"),
                }
                if mm.get("hits"):
                    hits_seq = list(mm["hits"])
                    if not hits_emb:
                        meta["fallback"] = "mmseqs"
                        meta["confidence_hint"] = "low"

            hits = list(hits_emb) + list(hits_seq)
            if not hits:
                raise RuntimeError(
                    (meta.get("esm", {}) or {}).get("error")
                    or (meta.get("mmseqs", {}) or {}).get("error")
                    or "no hits (need protein_embed conda / HF weights; do not invent similarity)"
                )
            return {
                "hits": hits,
                "hits_emb": hits_emb,
                "hits_seq": hits_seq,
                "meta": meta,
            }

        value, ms, error = await asyncio.to_thread(lambda: timed_call(_run))
        if error:
            return dumps(err(error, ms))
        return dumps(ok(value, ms))
