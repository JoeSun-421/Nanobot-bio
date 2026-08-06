# -*- coding: utf-8 -*-
"""P0 tool: ``get_known_rbp_list`` — RhoBind catalogue lookup.

Bridges to delivery registry JSON (~238 headed RBPs). Prefer filtering with
``query`` / ``alias`` / ``uniprot`` so the agent gets one protein (optionally
with AA sequence) instead of a truncated full dump.

Not a neighbour search — use ``seq_similarity`` for similar RBPs. Numbers and
sequences come from delivery / catalogue FASTA only.

CLI examples:
  nanobot-bio agent --message "Is PTBP1 in the RhoBind catalogue? Show UniProt id and AA sequence"
  nanobot-bio agent --query PTBP1 --rna-file path/to/rna.txt
  nanobot-bio doctor
"""

from __future__ import annotations

import asyncio
from typing import Any

from nanobot.agent.tools.core.base import Tool, tool_parameters

from nanobot.agent.tools.rbp.common import (
    dumps,
    err,
    get_delivery_client,
    load_catalogue_sequence,
    ok,
    timed_call,
)


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "include_sequences": {
                "type": "boolean",
                "default": False,
                "description": "If true with query/alias/uniprot, attach AA seq. "
                "Full-catalogue sequences are omitted (too large); use a filter.",
            },
            "query": {
                "type": "string",
                "description": "Filter one RBP by alias or UniProt (preferred).",
            },
            "alias": {"type": "string"},
            "uniprot": {"type": "string"},
            "max_rbps": {
                "type": "integer",
                "default": 50,
                "description": "Cap when listing without filter (default 50).",
            },
        },
        "required": [],
    }
)
class GetKnownRBPListTool(Tool):
    """P0 catalogue lookup — filter by alias/UniProt; not a neighbour search."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "get_known_rbp_list"

    @property
    def description(self) -> str:
        return (
            "Catalogue K (~238 RBPs). Prefer query/alias/uniprot for one protein "
            "(returns sequence). Full dump without filter is truncated — "
            "use seq_similarity(alias=...) for neighbours instead of scraping this list."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(
        self,
        include_sequences: bool = False,
        query: str = "",
        alias: str = "",
        uniprot: str = "",
        max_rbps: int = 50,
        **_: Any,
    ) -> str:
        filt = (query or alias or uniprot or "").strip()

        def _run():
            from nanobot.agent.tools.rbp.common import (
                apply_delivery_env_facade,
                load_rbp_registry_facade,
            )

            get_delivery_client()
            apply_delivery_env_facade()
            reg = load_rbp_registry_facade()
            items = []
            filt_up = filt.upper()
            for up, rec in reg.items():
                if not isinstance(rec, dict):
                    continue
                al = str(rec.get("alias") or "")
                if filt_up and filt_up not in {up.upper(), al.upper()}:
                    continue
                row: dict[str, Any] = {
                    "rbp_id": up,
                    "alias": rec.get("alias"),
                    "cohorts": rec.get("cohorts") or [],
                    "head_index": rec.get("head_index") or {},
                    "seq_len": rec.get("seq_len"),
                    "in_panel": bool(rec.get("head_index")),
                }
                # Always attach sequence for filtered single-RBP lookups;
                # for full lists only when explicitly requested AND small cap.
                want_seq = bool(filt) or (
                    include_sequences and (max_rbps or 50) <= 5
                )
                if want_seq or (include_sequences and filt):
                    seq = load_catalogue_sequence(up) or load_catalogue_sequence(al)
                    if seq:
                        row["sequence"] = seq
                        row["seq_len"] = len(seq)
                items.append(row)
                if not filt and len(items) >= max(1, int(max_rbps or 50)):
                    break

            out: dict[str, Any] = {
                "count": len(items),
                "total_catalogue": len(reg),
                "rbps": items,
                "filtered": bool(filt),
            }
            if not filt and include_sequences:
                out["note"] = (
                    "Full-catalogue AA sequences omitted; "
                    "call again with query/alias/uniprot to get one sequence, "
                    "or use seq_similarity(alias=...)."
                )
            if filt and not items:
                # Still try FASTA-only (matched by resolve but not registry key form)
                seq = load_catalogue_sequence(filt)
                if seq:
                    out["rbps"] = [
                        {
                            "rbp_id": filt,
                            "alias": filt,
                            "sequence": seq,
                            "seq_len": len(seq),
                            "cohorts": [],
                            "head_index": {},
                            "in_panel": False,
                            "note": "sequence from catalogue FASTA; not in panel registry",
                        }
                    ]
                    out["count"] = 1
            return out

        value, ms, error = await asyncio.to_thread(lambda: timed_call(_run))
        if error:
            return dumps(err(error, ms))
        return dumps(ok(value, ms))
