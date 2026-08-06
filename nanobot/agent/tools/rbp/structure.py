# -*- coding: utf-8 -*-
"""Stage-1 structure tools: Foldseek similarity + optional AF3 prediction.

Tools:

* ``struct_similarity`` — delivery Foldseek (+ optional USalign refine) against
  catalogue AFDB PDBs; prefer ``alias`` / ``uniprot``
* ``predict_structure`` — AF3 (slow/GPU), ≤1 call; prefer AFDB fetch first

Agent-side structure evidence order: AFDB fetch → Foldseek → AF3 ≤1 →
``structure_axis=unavailable``. Failures (including AF3) are disk-cached;
never map a missing/failed structure to similarity 0. Scores (TM / lDDT /
fident) come from delivery only.

CLI examples:
  nanobot-bio doctor
  nanobot-bio agent --message "Foldseek structure neighbours for PTBP1; prefer AFDB before AF3"
  nanobot-bio agent --force-transfer --query SOME_RBP --rna-file path/to/rna.txt
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from nanobot.agent.tools.core.base import Tool, tool_parameters

from nanobot.agent.tools.rbp.common import (
    catalogue_pdb_path,
    dumps,
    err,
    get_delivery_client,
    looks_like_dummy_protein,
    ok,
    resolve_protein_sequence,
    structure_cache_get,
    structure_cache_put,
    timed_call,
)


def _af3_cache_key(seq: str, name: str) -> str:
    return f"af3:{name}:{len(seq)}:{seq[:32]}:{seq[-16:]}"


def _is_colabfold_rate_limit(detail: str, stderr: str = "") -> bool:
    """True when ColabFold / MSA stage hit HTTP 429 or an explicit rate-limit."""
    blob = f"{detail}\n{stderr}".lower()
    if "429" in blob and any(
        tok in blob for tok in ("colabfold", "msa", "too many requests", "rate")
    ):
        return True
    return any(
        tok in blob
        for tok in (
            "http 429",
            "too many requests",
            "colabfold rate",
            "rate limit",
            "ratelimit",
        )
    )


def _classify_af3_failure(detail: str, stderr: str = "") -> str:
    """Map AF3 failures to actionable agent-facing reasons (esp. Blackwell CC 12.0)."""
    blob = f"{detail}\n{stderr}"
    if _is_colabfold_rate_limit(detail, stderr):
        return (
            "af3 failed: ColabFold MSA HTTP 429 (shared public API rate limit). "
            "Not a permanent AF3 failure — wait a few minutes and retry, or pass "
            "msa_path/msa_a3m (precomputed), or use structure_fetch (AFDB) when "
            "UniProt has a model. Do not map to sim=0."
        )
    if any(
        tok in blob
        for tok in (
            "computeCapability not supported",
            "getMMAVersionSafe",
            "ptxas too old",
            "ptxas does not support CC 12",
        )
    ):
        return (
            "af3 failed: GPU compute capability unsupported by bundled "
            "jax/triton (RTX 50-series / CC 12.0). Structure axis unavailable — "
            "continue AFDB/sequence/domain transfer; do not map failure to sim=0. "
            "See docs/guides/AF3_RUNTIME_AND_RELEASE.md."
        )
    # Delivery truncates stderr to the last 2k chars; the Triton assert is often
    # at the *start*, so fall back to host GPU probe on generic failures.
    if "af3 failed" in detail.lower() or not detail.strip():
        try:
            import subprocess

            cap = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=compute_cap",
                    "--format=csv,noheader",
                ],
                text=True,
                timeout=5,
            ).strip().splitlines()[0]
            major = float(cap.split()[0])
            if major >= 12.0:
                return (
                    f"af3 failed: host GPU compute_cap={cap} (Blackwell) is "
                    "incompatible with AF3 env jax 0.4.34 / triton 3.1 — "
                    "structure_axis=unavailable. Prefer AFDB + ESM/domain; "
                    "force confidence=low until AF3 stack is upgraded "
                    "(docs/guides/AF3_RUNTIME_AND_RELEASE.md)."
                )
        except Exception:
            pass
    useful = [
        ln.strip()
        for ln in stderr.splitlines()
        if any(
            k in ln
            for k in ("Error", "error:", "Exception", "FAILED", "Aborted", "Assertion")
        )
    ]
    if useful:
        return f"{detail} | {useful[-1][:200]}"
    return detail or "af3 failed; structure_axis=unavailable"


def _af3_confidence_fields(out: dict[str, Any]) -> dict[str, Any]:
    """Surface AF3 confidence metrics the agent should cite (Abramson et al. 2024)."""
    keys = (
        "mean_plddt",
        "ptm",
        "iptm",
        "ranking_score",
        "structured_core_plddt",
        "fraction_structured",
        "region_plddt",
        "fraction_disordered",
        "has_clash",
    )
    return {k: out.get(k) for k in keys if out.get(k) is not None}


def _usable_structure_path(payload: dict[str, Any] | None) -> bool:
    """True when a payload carries a non-empty structure / pdb path."""
    if not isinstance(payload, dict):
        return False
    for key in ("structure", "pdb_path"):
        val = payload.get(key)
        if val is not None and str(val).strip():
            return True
    return False


def _clear_sticky_structure_unavailable(payload: dict[str, Any] | None = None) -> None:
    """Drop AFDB-miss sticky flags once a usable structure path exists.

    Does not clear AF3 hard-failure flags (``af3_unavailable``) or intentional
    trust flags (``structure_mostly_disordered``, ``structure_low_plddt``, …).
    """
    if payload is not None and not _usable_structure_path(payload):
        return
    try:
        from nanobot.agent.tools.rbp.turn_guards import clear_structure_axis_unavailable

        clear_structure_axis_unavailable()
    except Exception:
        pass


def _surface_af3_success_evidence(value: dict[str, Any]) -> None:
    """On AF3 success: clear sticky axis-unavailable; keep/add trust flags."""
    if not _usable_structure_path(value):
        return
    _clear_sticky_structure_unavailable(value)
    try:
        from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

        trust = value.get("structure_trust")
        if trust and trust != "ok":
            add_evidence_flag(f"structure_{trust}", True)
        rpl = value.get("region_plddt")
        if rpl is not None:
            # region_plddt may be a list of {region, plddt} or a scalar; check min.
            try:
                if isinstance(rpl, list):
                    rvals: list[float] = []
                    for x in rpl:
                        raw = x.get("plddt") if isinstance(x, dict) else x
                        if not isinstance(raw, (int, float, str)):
                            continue
                        rvals.append(float(raw))
                    rmin = min(rvals) if rvals else None
                else:
                    rmin = float(rpl)
                if rmin is not None and rmin < 50:
                    add_evidence_flag("region_plddt_low", True)
            except (TypeError, ValueError):
                pass
    except Exception:
        pass


def _usalign_refine_enabled(kwargs: dict[str, Any]) -> bool:
    """Honor explicit kwargs, else runtime ``axes.struct_align_refine``."""
    if "refine_usalign" in kwargs:
        return bool(kwargs.get("refine_usalign"))
    try:
        from nanobot.agent.tools.rbp.common import get_runtime_config

        axes = get_runtime_config().get("axes") or {}
        return bool(axes.get("struct_align_refine", True))
    except Exception:
        return True


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "pdb_path": {"type": "string"},
            "uniprot": {
                "type": "string",
                "description": "Preferred with alias: resolve AFDB PDB / structure_fetch.",
            },
            "alias": {"type": "string", "description": "Gene symbol, e.g. RBFOX2."},
            "top_k": {"type": "integer", "default": 10},
            "refine_usalign": {
                "type": "boolean",
                "description": (
                    "Refine Foldseek top hits with USalign TM. Default follows "
                    "axes.struct_align_refine (true in product defaults)."
                ),
            },
        },
        "required": [],
    }
)
class StructSimilarityTool(Tool):
    """Stage-1 structure retrieve — Foldseek (+ optional USalign) vs AFDB PDBs."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "struct_similarity"

    @property
    def description(self) -> str:
        return (
            "Structural similarity via Foldseek (+ optional USalign). "
            "Prefer alias+uniprot (e.g. RBFOX2 / O43251); pdb_path optional. "
            "Requires an existing PDB (AFDB). On missing structure return error — "
            "do NOT treat as similarity 0."
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
        def _run():
            client = get_delivery_client()
            pdb = kwargs.get("pdb_path")
            uniprot = (kwargs.get("uniprot") or "").strip()
            alias = (kwargs.get("alias") or "").strip()
            if not pdb:
                local = catalogue_pdb_path(uniprot=uniprot, alias=alias)
                if local is not None:
                    pdb = str(local)
            if not pdb and uniprot:
                sf = client.call("structure_fetch", {"uniprot": uniprot, "alias": alias})
                pdb = sf.get("pdb_path")
                if not pdb:
                    raise RuntimeError(
                        sf.get("error")
                        or "structure_unavailable: no AFDB PDB — "
                        "do not use sim=0; continue sequence-only or try predict_structure once"
                    )
            if not pdb and alias:
                sf = client.call("structure_fetch", {"alias": alias})
                pdb = sf.get("pdb_path")
            if not pdb:
                raise RuntimeError(
                    "structure_unavailable: pdb_path or uniprot/alias with AFDB required; "
                    "not a zero-similarity hit"
                )
            st = client.call(
                "struct_similarity_foldseek",
                {"pdb_path": pdb, "top_k": int(kwargs.get("top_k") or 10)},
            )
            if st.get("error"):
                raise RuntimeError(st["error"])
            hits = list(st.get("hits") or [])
            refined = False
            if _usalign_refine_enabled(kwargs) and hits:
                aliases = [h["alias"] for h in hits[:5] if h.get("alias")]
                usa = client.call(
                    "struct_align_usalign",
                    {"query_pdb": pdb, "targets": aliases},
                )
                if usa.get("hits"):
                    hits = usa["hits"]
                    refined = True
            return {
                "hits": hits,
                "pdb_path": pdb,
                "structure_axis": "ok",
                "usalign_refined": refined,
            }

        value, ms, error = await asyncio.to_thread(lambda: timed_call(_run))
        if error:
            if "structure_unavailable" in str(error):
                try:
                    from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

                    add_evidence_flag("structure_axis_unavailable", True)
                except Exception:
                    pass
            return dumps(
                err(
                    error
                    if "structure_unavailable" in str(error)
                    else f"{error} (structure_axis=unavailable; do not vote with sim=0)",
                    ms,
                )
            )
        # Usable PDB path (and/or hits) recovers the structure axis after AFDB miss.
        if isinstance(value, dict) and (
            _usable_structure_path(value) or value.get("hits")
        ):
            _clear_sticky_structure_unavailable()
        return dumps(ok(value, ms))


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "sequence": {
                "type": "string",
                "description": "Protein AA; omit if alias/uniprot in catalogue.",
            },
            "name": {"type": "string"},
            "uniprot_id": {"type": "string"},
            "alias": {"type": "string"},
            "uniprot": {"type": "string"},
            "regions": {
                "type": "array",
                "description": (
                    "Optional RBD / domain residue ranges [[start,end], ...] "
                    "(1-based or delivery convention). From domain_architecture "
                    "or UniProt features when available."
                ),
                "items": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
            "msa_path": {
                "type": "string",
                "description": (
                    "Optional path to a precomputed a3m MSA. Skips ColabFold "
                    "online MSA (avoids HTTP 429)."
                ),
            },
            "msa_a3m": {
                "type": "string",
                "description": (
                    "Optional a3m MSA string. Skips ColabFold online MSA."
                ),
            },
            "msa_mode": {
                "type": "string",
                "description": (
                    "ColabFold MSA mode when fetching online (default env). "
                    "Ignored if msa_path/msa_a3m is set."
                ),
            },
        },
        "required": [],
    }
)
class PredictStructureTool(Tool):
    """Optional AF3 structure prediction (≤1/turn); never map failure to sim=0."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "predict_structure"

    @property
    def description(self) -> str:
        return (
            "AF3 structure prediction (slow/GPU). Prefer alias/uniprot to load "
            "catalogue sequence. Pass regions=[[start,end],...] from "
            "domain_architecture / RBD features when known. Prefer "
            "structure_fetch / struct_similarity when AFDB PDB exists. "
            "On ColabFold MSA 429: falls back to AFDB when possible; pass "
            "msa_path/msa_a3m to skip online MSA. Call ≤1 time; permanent "
            "failures are disk-cached (429 is not)."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, sequence: str = "", name: str = "", **kwargs: Any) -> str:
        t0 = time.perf_counter()  # A7: real wall-time even on cache hits
        try:
            from nanobot.agent.tools.rbp.turn_guards import blocked_envelope_json

            blocked = blocked_envelope_json(self.name)
            if blocked:
                return blocked
        except Exception:
            pass
        kw = dict(kwargs)
        if sequence:
            kw["sequence"] = sequence
        if name and not kw.get("alias"):
            kw.setdefault("alias", name)
        if looks_like_dummy_protein(sequence or ""):
            return dumps(
                err(
                    "sequence looks invented (poly-X); pass alias/uniprot or a real AA "
                    "sequence, or use structure_fetch / struct_similarity on AFDB"
                )
            )
        seq, src = resolve_protein_sequence(kw)
        if not seq:
            return dumps(
                err(
                    "need alias/uniprot or a real protein AA sequence; "
                    "do not invent sequences; prefer structure_fetch if AFDB exists"
                )
            )
        # If AFDB already has a PDB, prefer that over AF3
        local = catalogue_pdb_path(
            uniprot=str(kw.get("uniprot") or kw.get("uniprot_id") or ""),
            alias=str(kw.get("alias") or name or ""),
        )
        if local is not None:
            afdb_value = {
                "structure": str(local),
                "mean_plddt": None,
                "ptm": None,
                "note": "AFDB PDB already present; skipped AF3",
                "sequence_source": src,
                "structure_axis": "afdb",
                "cache": "skipped_af3",
            }
            _clear_sticky_structure_unavailable(afdb_value)
            return dumps(ok(afdb_value))

        # Honor axes / structure_policy before AF3
        try:
            from nanobot.agent.tools.rbp.common import (
                axis_tool_enabled,
                get_runtime_config,
            )

            allowed, blocking = axis_tool_enabled("predict_structure")
            if not allowed:
                return dumps(
                    err(
                        f"structure_axis=unavailable: AF3 disabled (axis={blocking}); "
                        "continue sequence/domain/RNA; do not vote sim=0"
                    )
                )
            pol = (get_runtime_config().get("structure_policy") or {})
            if pol.get("use_af3_fallback") is False:
                return dumps(
                    err(
                        "structure_axis=unavailable: use_af3_fallback=false and no AFDB PDB; "
                        "continue without structure zeros"
                    )
                )
            # Host AF3 status deferred/broken → clear degrade (not silent 0)
            from app.core.capability_matrix import read_af3_status

            st = (read_af3_status().get("state") or "").strip()
            if st in ("deferred", "broken", "missing", "disabled"):
                return dumps(
                    err(
                        f"structure_axis=unavailable: AF3 host state={st or 'unknown'}; "
                        "AFDB-first failed; continue sequence/domain/RNA (not sim=0)"
                    )
                )
        except Exception:
            pass

        cache_name = str(name or kw.get("uniprot_id") or kw.get("alias") or "query")
        ckey = _af3_cache_key(seq, cache_name)
        cached = structure_cache_get(ckey)
        if cached is not None:
            cached = dict(cached)
            # Do not replay rate-limit failures — they are transient and used to
            # poison the 7-day disk cache, making every retry look "always 429".
            cached_err = str(cached.get("error") or "")
            if (cached.get("ok") is False or cached.get("error")) and _is_colabfold_rate_limit(
                cached_err
            ):
                cached = None
            else:
                cached["cache"] = "hit"
                _hit_ms = (time.perf_counter() - t0) * 1000.0
                if cached.get("ok") is False or cached.get("error"):
                    return dumps(
                        err(
                            _classify_af3_failure(
                                str(
                                    cached.get("error")
                                    or "af3 failed (cached); structure_axis=unavailable"
                                )
                            ),
                            _hit_ms,
                        )
                    )
                _clear_sticky_structure_unavailable(cached)
                return dumps(ok(cached, _hit_ms))

        def _try_afdb_on_msa_429() -> dict[str, Any] | None:
            """Soft-degrade: AFDB structure_fetch when ColabFold MSA is rate-limited."""
            uniprot = str(kw.get("uniprot") or kw.get("uniprot_id") or "").strip()
            alias = str(kw.get("alias") or name or "").strip()
            if not uniprot and not alias:
                return None
            client = get_delivery_client()
            sf_payload: dict[str, Any] = {"allow_download": True}
            if uniprot:
                sf_payload["uniprot"] = uniprot
            if alias:
                sf_payload["alias"] = alias
            try:
                sf = client.call("structure_fetch", sf_payload)
            except Exception:
                return None
            pdb = sf.get("pdb_path") if isinstance(sf, dict) else None
            if not pdb:
                return None
            return {
                "structure": str(pdb),
                "mean_plddt": None,
                "ptm": None,
                "sequence_source": src,
                "structure_axis": "afdb",
                "structure_trust": "afdb_fallback",
                "af3_degraded": "colabfold_msa_429",
                "note": (
                    "AF3 skipped: ColabFold MSA HTTP 429; using AFDB via "
                    "structure_fetch (soft degradation — not an AF3 model)"
                ),
                "afdb_source": sf.get("source"),
                "ok": True,
            }

        def _run():
            client = get_delivery_client(device="cuda")
            payload: dict[str, Any] = {
                "sequence": seq,
                "name": cache_name,
            }
            regions = kw.get("regions")
            if regions is None and kwargs.get("regions") is not None:
                regions = kwargs.get("regions")
            if regions:
                # Coerce [[a,b], ...] of ints for delivery AF3
                clean_regions = []
                for pair in regions:
                    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                        try:
                            clean_regions.append([int(pair[0]), int(pair[1])])
                        except (TypeError, ValueError):
                            continue
                if clean_regions:
                    payload["regions"] = clean_regions
            # Optional precomputed MSA bypasses ColabFold (avoids 429).
            for key in ("msa_path", "msa_a3m", "msa_mode"):
                val = kw.get(key)
                if val:
                    payload[key] = val
            return client.call("structure_predict_af3", payload)

        out, ms, error = await asyncio.to_thread(lambda: timed_call(_run))
        if error:
            detail = _classify_af3_failure(error)
            if _is_colabfold_rate_limit(error):
                fb = await asyncio.to_thread(_try_afdb_on_msa_429)
                if fb is not None:
                    try:
                        from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

                        add_evidence_flag("af3_msa_429_afdb_fallback", True)
                    except Exception:
                        pass
                    _clear_sticky_structure_unavailable(fb)
                    structure_cache_put(ckey, fb)
                    return dumps(ok(fb, ms))
                # Transient — do not poison the 7-day failure cache.
                try:
                    from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

                    add_evidence_flag("af3_unavailable", True)
                    add_evidence_flag("colabfold_msa_429", True)
                except Exception:
                    pass
                return dumps(err(f"{detail} | structure_axis=unavailable", ms))
            payload = {
                "ok": False,
                "error": detail,
                "structure_axis": "unavailable",
                "sequence_source": src,
            }
            structure_cache_put(ckey, payload)
            try:
                from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

                add_evidence_flag("af3_unavailable", True)
            except Exception:
                pass
            return dumps(err(f"{detail} | structure_axis=unavailable", ms))
        if not isinstance(out, dict):
            return dumps(err("AF3 returned no payload | structure_axis=unavailable", ms))
        if out.get("error") or out.get("ok") is False:
            raw_err = str(out.get("error") or "AF3 failed")
            stderr = str(out.get("stderr") or "")
            detail = _classify_af3_failure(raw_err, stderr)
            if _is_colabfold_rate_limit(raw_err, stderr):
                fb = await asyncio.to_thread(_try_afdb_on_msa_429)
                if fb is not None:
                    try:
                        from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

                        add_evidence_flag("af3_msa_429_afdb_fallback", True)
                    except Exception:
                        pass
                    _clear_sticky_structure_unavailable(fb)
                    structure_cache_put(ckey, fb)
                    return dumps(ok(fb, ms))
                try:
                    from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

                    add_evidence_flag("af3_unavailable", True)
                    add_evidence_flag("colabfold_msa_429", True)
                except Exception:
                    pass
                return dumps(err(detail, ms))
            payload = {
                "ok": False,
                "error": detail,
                "structure_axis": "unavailable",
                "sequence_source": src,
            }
            structure_cache_put(ckey, payload)
            try:
                from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

                add_evidence_flag("af3_unavailable", True)
            except Exception:
                pass
            return dumps(err(detail, ms))
        value = {
            "structure": out.get("structure"),
            "sequence_source": src,
            "structure_axis": "af3",
            "ok": True,
            **_af3_confidence_fields(out),
        }
        # Soft trust flags for the LLM (do not invent numbers)
        mean_p = value.get("mean_plddt")
        if mean_p is not None and float(mean_p) < 50:
            value["structure_trust"] = "low_plddt"
        elif value.get("has_clash") not in (None, 0, 0.0, False):
            value["structure_trust"] = "clash"
        elif value.get("fraction_disordered") is not None and float(
            value["fraction_disordered"]
        ) > 0.5:
            value["structure_trust"] = "mostly_disordered"
        else:
            value["structure_trust"] = "ok"
        # Clear sticky AFDB-miss flags; surface intentional trust / region_plddt.
        _surface_af3_success_evidence(value)
        structure_cache_put(ckey, value)
        return dumps(ok(value, ms))
