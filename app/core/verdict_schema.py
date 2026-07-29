# -*- coding: utf-8 -*-
"""Stage-3 verdict JSON schema validation & normalization.

Agent MVP requires every successful run to emit a structured verdict::

    {
      "label": "Strong|Likely|Unlikely|No",
      "p_hat": float,
      "confidence": "high|medium|low" | float,
      "explanation": str,
      "supporting_rbps": [ {...}, ... ]
    }
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

LABELS = ("Strong", "Likely", "Unlikely", "No")
CONFIDENCE_LEVELS = ("high", "medium", "low")
DEFAULT_THRESHOLDS = {"strong": 0.75, "likely": 0.50, "unlikely": 0.25}


def _runtime_thresholds() -> dict[str, float]:
    try:
        from app.core.runtime_config import label_thresholds

        return label_thresholds()
    except Exception:
        return dict(DEFAULT_THRESHOLDS)


def label_from_p_hat(
    p_hat: Optional[float],
    thresholds: Optional[dict[str, float]] = None,
) -> str:
    thr = {**_runtime_thresholds(), **(thresholds or {})}
    if p_hat is None:
        return "No"
    p = float(p_hat)
    if p >= float(thr["strong"]):
        return "Strong"
    if p >= float(thr["likely"]):
        return "Likely"
    if p >= float(thr["unlikely"]):
        return "Unlikely"
    return "No"


_FENCE_OPEN_RE = re.compile(r"```(?:json)?\s*", re.IGNORECASE)


def _balanced_json_slice(s: str, start: int) -> Optional[str]:
    """Return s[start:end] for a balanced {...} object starting at start."""
    if start < 0 or start >= len(s) or s[start] != "{":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _parse_json_object(text: str) -> Optional[dict[str, Any]]:
    """Best-effort parse of a JSON object from LLM text (fences / prose)."""
    if not text or not str(text).strip():
        return None
    s = str(text).strip()
    # Decode common double-encoding: literal \\n / \\" left in the string
    if "\\n" in s or '\\"' in s:
        try:
            s2 = codecs_decode_escapes(s)
            if s2 != s:
                s = s2.strip()
        except Exception:
            pass
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    # ```json ... ```
    m = _FENCE_OPEN_RE.search(s)
    if m:
        brace = s.find("{", m.end())
        slice_ = _balanced_json_slice(s, brace) if brace >= 0 else None
        if slice_:
            try:
                obj = json.loads(slice_)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
    brace = s.find("{")
    slice_ = _balanced_json_slice(s, brace) if brace >= 0 else None
    if slice_:
        try:
            obj = json.loads(slice_)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def codecs_decode_escapes(s: str) -> str:
    """Turn literal ``\\n`` / ``\\\"`` remnants into real characters when safe."""
    if s.count("\\n") < 2 and '\\"' not in s:
        return s
    try:
        return bytes(s, "utf-8").decode("unicode_escape")
    except Exception:
        return s


def _looks_like_embedded_verdict(text: str) -> bool:
    if not isinstance(text, str):
        return False
    t = text.strip()
    if "```" in t:
        return True
    if '"label"' in t and "{" in t and "}" in t:
        return True
    return t.startswith("{") and "label" in t


def _plain_explanation(text: Any) -> str:
    """Force explanation to plain sentences — never nested JSON / fences."""
    if text is None:
        return ""
    if not isinstance(text, str):
        return str(text).strip()
    s = text.strip()
    # Repeatedly peel embedded verdict JSON
    for _ in range(4):
        if not _looks_like_embedded_verdict(s):
            break
        inner = _parse_json_object(s)
        if inner and isinstance(inner.get("explanation"), str):
            s = inner["explanation"].strip()
            continue
        # Strip fence markers even if parse failed
        s = re.sub(r"```(?:json)?", "", s, flags=re.IGNORECASE).replace("```", "").strip()
        break
    # Drop any leftover raw JSON object lines
    if s.startswith("{") and '"label"' in s:
        inner = _parse_json_object(s)
        if inner and isinstance(inner.get("explanation"), str):
            s = inner["explanation"].strip()
    return s


def _unwrap_nested_verdict(raw: dict[str, Any]) -> dict[str, Any]:
    """If LLM stuffed a full verdict JSON into explanation, prefer the inner one."""
    cur = dict(raw)
    for _ in range(4):
        expl = cur.get("explanation")
        if not _looks_like_embedded_verdict(expl if isinstance(expl, str) else ""):
            break
        inner = _parse_json_object(str(expl))
        if not inner or "label" not in inner:
            break
        merged = dict(inner)
        for k in ("mode", "caveats", "near_match", "abstain", "function_reasoning"):
            if k in cur and k not in merged:
                merged[k] = cur[k]
        # Prefer non-empty supporting_rbps from either layer
        outer_sup = cur.get("supporting_rbps") or []
        inner_sup = merged.get("supporting_rbps") or []
        if not inner_sup and outer_sup:
            merged["supporting_rbps"] = outer_sup
        cur = merged
    return cur


def normalize_verdict(
    raw: Any,
    *,
    thresholds: Optional[dict[str, float]] = None,
    default_mode: str = "unknown",
) -> dict[str, Any]:
    """Coerce pipeline/LLM output into the structured verdict object."""
    if raw is None:
        raw = {}
    if isinstance(raw, str):
        parsed = _parse_json_object(raw)
        raw = parsed if parsed is not None else {"explanation": raw, "raw_content": raw}

    if not isinstance(raw, dict):
        raw = {"raw": raw}

    # Nested under "verdict" (pipeline full result)
    if "verdict" in raw and isinstance(raw["verdict"], dict):
        inner = dict(raw["verdict"])
        # Keep useful outer fields for supporting_rbps fallback
        if "evidence_table" in raw and "supporting_rbps" not in inner:
            inner["_evidence_table"] = raw["evidence_table"]
        if raw.get("integration", {}).get("score") is not None and inner.get("p_hat") is None:
            inner["p_hat"] = raw["integration"]["score"]
        if raw.get("mode") and "mode" not in inner:
            inner["mode"] = raw["mode"]
        raw = inner

    # Unwrap double-wrapped ```json / nested verdict inside explanation
    raw = _unwrap_nested_verdict(raw)

    p_hat = raw.get("p_hat")
    if p_hat is None:
        p_hat = raw.get("score")
    if p_hat is not None:
        try:
            p_hat = float(p_hat)
        except (TypeError, ValueError):
            p_hat = None

    label = raw.get("label")
    if label not in LABELS:
        label = label_from_p_hat(p_hat, thresholds)

    # Numeric p_hat only from predictors. Missing predictor → null + hedged label.
    if p_hat is None and label in ("Strong", "Likely", "Unlikely"):
        label = "No"
        conf_forced_low = True
    else:
        conf_forced_low = False

    # Product callers may inject a deterministic evidence confidence. It always
    # wins over LLM prose/numbers and is intentionally independent of p_hat.
    deterministic_conf = raw.get("_deterministic_confidence")
    conf = deterministic_conf if deterministic_conf in CONFIDENCE_LEVELS else raw.get("confidence")
    # Evidence flags from agent / integrate (scores remain tool-sourced)
    evidence_flags = raw.get("evidence_flags") or raw.get("flags") or {}
    if isinstance(evidence_flags, list):
        evidence_flags = {str(x): True for x in evidence_flags}
    prior_missing = bool(
        raw.get("prior_missing")
        or evidence_flags.get("prior_missing")
        or evidence_flags.get("loo_prior_missing")
    )
    structure_unavailable = bool(
        raw.get("structure_unavailable")
        or evidence_flags.get("structure_unavailable")
        or evidence_flags.get("structure_axis_unavailable")
    )
    low_head_coverage = bool(evidence_flags.get("low_head_coverage"))
    domain_empty = bool(
        raw.get("domain_empty") or evidence_flags.get("domain_empty")
    )
    single_donor_transfer = bool(
        raw.get("single_donor_transfer")
        or evidence_flags.get("single_donor_transfer")
    )
    no_headed_donors = bool(
        raw.get("no_headed_donors")
        or evidence_flags.get("no_headed_donors")
    )
    fragile_single_donor = single_donor_transfer and (
        prior_missing or domain_empty
    )
    force_low_evidence = (
        prior_missing
        or structure_unavailable
        or low_head_coverage
        or fragile_single_donor
        or no_headed_donors
        or bool(evidence_flags.get("ood"))
        or bool(evidence_flags.get("selective_abstain"))
        or bool(evidence_flags.get("sequence_only"))
    )

    # Stage-3 evidence checklist (≥2 failures → confidence=low); Proposal faithfulness.
    checklist_n = raw.get("checklist_failures")
    if checklist_n is None:
        checklist_n = evidence_flags.get("checklist_failures")
    try:
        checklist_n_i = int(checklist_n) if checklist_n is not None else None
    except (TypeError, ValueError):
        checklist_n_i = None
    if checklist_n_i is None:
        # Count well-known failure flags when agent did not supply an explicit count.
        flag_fails = 0
        for key in (
            "structure_unavailable",
            "structure_axis_unavailable",
            "prior_missing",
            "loo_prior_missing",
            "domain_empty",
            "kingdom_mismatch",
            "rna_axis_unavailable",
            "sequence_only",
            "low_head_coverage",
            "ood",
            "selective_abstain",
        ):
            if evidence_flags.get(key) or raw.get(key):
                flag_fails += 1
        if structure_unavailable:
            flag_fails = max(flag_fails, 1 if not evidence_flags else flag_fails)
        checklist_n_i = flag_fails
    if checklist_n_i >= 2:
        force_low_evidence = True

    if no_headed_donors:
        p_hat = None
        label = "No"
        conf_forced_low = True
    elif fragile_single_donor and label == "Strong":
        label = "Likely"

    if conf_forced_low or force_low_evidence:
        conf = "low"
    elif conf is None:
        conf = "low" if p_hat is None else (
            "high" if str(raw.get("mode") or default_mode) == "own_head" else "medium"
        )
    if isinstance(conf, (int, float)):
        c = float(conf)
        conf = "high" if c >= 0.75 else ("medium" if c >= 0.45 else "low")
    elif isinstance(conf, str):
        token = conf.strip().lower().split()[0] if conf.strip() else "low"
        token = token.strip(".,;:()")
        if deterministic_conf in CONFIDENCE_LEVELS:
            conf = deterministic_conf
        elif force_low_evidence:
            conf = "low"
        elif token in ("high", "hi"):
            conf = "high"
        elif token in ("medium", "med", "moderate", "mid"):
            conf = "medium"
        elif token in ("low", "weak"):
            conf = "low"
        else:
            conf = "low" if p_hat is None else "medium"

    supporting = raw.get("supporting_rbps") or raw.get("supporting_RBPs") or []
    if not supporting and isinstance(raw.get("_evidence_table"), list):
        supporting = []
        for row in raw["_evidence_table"][:5]:
            supporting.append(
                {
                    "rbp_id": row.get("uniprot") or row.get("alias"),
                    "alias": row.get("alias"),
                    "prob": row.get("prob"),
                    "similarity_score": row.get("fused_similarity"),
                }
            )
    # LLM sometimes returns ["PTBP1", ...] — coerce to objects
    if isinstance(supporting, list):
        norm_sup = []
        for item in supporting:
            if isinstance(item, str):
                norm_sup.append({"rbp_id": item, "alias": item})
            elif isinstance(item, dict):
                norm_sup.append(item)
        supporting = norm_sup

    explanation = _plain_explanation(raw.get("explanation") or raw.get("summary") or "")
    if not explanation:
        explanation = (
            f"Verdict {label} with p_hat={p_hat}. "
            f"Mode={raw.get('mode') or default_mode}. "
            "Ground explanations in tool outputs when available."
        )
    # Absolute guard: never ship fences / nested JSON in explanation
    explanation = _plain_explanation(explanation)
    if "```" in explanation or (explanation.lstrip().startswith("{") and '"label"' in explanation):
        # Last resort: keep only the first prose sentence-like chunk
        explanation = re.split(r"```|\{", explanation, maxsplit=1)[0].strip() or (
            f"Own-head/transfer path finished with label={label}, p_hat={p_hat}."
        )

    out = {
        "label": label,
        "p_hat": p_hat,
        "confidence": conf,
        "explanation": explanation,
        "supporting_rbps": supporting if isinstance(supporting, list) else [],
    }
    # optional extras (not required by schema)
    for k in (
        "mode",
        "score_source",
        "score_kind",
        "score_disclaimer",
        "score_provenance",
        "caveats",
        "near_match",
        "abstain",
        "function_reasoning",
        "prior_missing",
        "structure_unavailable",
        "evidence_flags",
    ):
        if raw.get(k) is not None:
            out[k] = raw[k]
    if force_low_evidence and "prior_missing" not in out and prior_missing:
        out["prior_missing"] = True
    if force_low_evidence and "structure_unavailable" not in out and structure_unavailable:
        out["structure_unavailable"] = True

    # Faithfulness helpers: surface caveats + modality breakdown for Stage-3 audits
    # B3: exhaustive soft-failure sources — every one must surface into caveats when
    # its evidence flag is set (AF3 missing / structure soft-fail / literature offline
    # / mmseqs segfault / low region plddt / axis skipped).
    caveat_keys = (
        "prior_missing",
        "loo_prior_missing",
        "structure_unavailable",
        "structure_axis_unavailable",
        "rna_axis_unavailable",
        "domain_empty",
        "kingdom_mismatch",
        "sequence_only",
        "af3_unavailable",
        "af3_axis_skipped",
        "structure_low_plddt",
        "structure_clash",
        "structure_mostly_disordered",
        "region_plddt_low",
        "literature_unavailable",
        "mmseqs_segfall",
        "low_head_coverage",
        "single_donor_transfer",
        "no_headed_donors",
        "near_match_donor_no_head",
        "ood",
        "selective_abstain",
    )
    caveats = out.get("caveats")
    if not isinstance(caveats, list):
        caveats = []
    for key in caveat_keys:
        if (evidence_flags.get(key) or raw.get(key)) and key not in caveats:
            caveats.append(key)
    if caveats:
        out["caveats"] = caveats

    # Propagate donor modality maps onto supporting_rbps.similarity_breakdown
    donors = raw.get("donors") if isinstance(raw.get("donors"), list) else []
    donor_by_alias: dict[str, dict] = {}
    for d in donors:
        if not isinstance(d, dict):
            continue
        for key in ("alias", "rbp_id", "uniprot"):
            if d.get(key):
                donor_by_alias[str(d.get(key)).upper()] = d
    for item in out.get("supporting_rbps") or []:
        if not isinstance(item, dict):
            continue
        if item.get("similarity_breakdown"):
            continue
        alias = str(item.get("alias") or item.get("rbp_id") or "").upper()
        donor = donor_by_alias.get(alias)
        if donor and isinstance(donor.get("sim_by_modality"), dict):
            item["similarity_breakdown"] = dict(donor["sim_by_modality"])

    abstain = out.get("abstain")
    if force_low_evidence:
        if not isinstance(abstain, dict):
            abstain = {}
        abstain = dict(abstain)
        abstain["confident"] = False
        out["abstain"] = abstain
    return out


def confidence_from_evidence(
    *,
    mode: str,
    p_hat: Optional[float],
    evidence_flags: Optional[dict[str, Any]] = None,
    provenance: Optional[dict[str, Any]] = None,
) -> str:
    """Deterministic evidence/OOD confidence, never a transform of score size."""
    if p_hat is None:
        return "low"
    if mode == "own_head":
        return "high"

    flags = dict(evidence_flags or {})
    prov = dict(provenance or {})
    aggregation = prov.get("aggregation") if isinstance(prov.get("aggregation"), dict) else {}
    terms = aggregation.get("terms") if isinstance(aggregation.get("terms"), list) else []
    predictions = prov.get("predictions") if isinstance(prov.get("predictions"), list) else []
    n_donors = len(terms) or sum(
        1 for row in predictions if isinstance(row, dict) and row.get("prob") is not None
    )

    points = 0
    if n_donors >= 3:
        points += 2
    elif n_donors >= 2:
        points += 1
    if n_donors and int(aggregation.get("n_transfer_priors") or 0) >= n_donors:
        points += 1
    if n_donors and int(aggregation.get("n_donor_quality") or 0) >= n_donors:
        points += 1
    if flags.get("structure_evidence_available"):
        points += 1
    if flags.get("modality_agreement"):
        points += 1

    severe = any(
        flags.get(k)
        for k in (
            "low_head_coverage",
            "sequence_only",
            "predict_failed",
            "ood",
        )
    )
    # literature_unavailable is caveat-only: surface in caveats, do not deduct points.
    failures = sum(
        bool(flags.get(k))
        for k in (
            "prior_missing",
            "loo_prior_missing",
            "structure_unavailable",
            "structure_axis_unavailable",
            "domain_empty",
            "rna_axis_unavailable",
        )
    )
    points -= min(failures, 2)
    if severe or points <= 0:
        return "low"
    # Transfer high-confidence thresholds have not yet been fitted on a
    # sufficiently large held-out coverage-risk set. Cap deterministic
    # transfer confidence at medium; exact own-head remains high above.
    return "medium"


def validate_verdict(v: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (ok, errors). MVP requires all five fields present and typed."""
    errors: list[str] = []
    if not isinstance(v, dict):
        return False, ["verdict is not a dict"]
    if v.get("label") not in LABELS:
        errors.append(f"label must be one of {LABELS}, got {v.get('label')!r}")
    ph = v.get("p_hat")
    if ph is not None:
        try:
            float(ph)
        except (TypeError, ValueError):
            errors.append("p_hat must be float or null")
    else:
        # allow null p_hat only if label is No (tools failed)
        if v.get("label") != "No":
            errors.append("p_hat is null but label is not No")
    if not v.get("explanation") or not str(v.get("explanation")).strip():
        errors.append("explanation missing")
    if "supporting_rbps" not in v:
        errors.append("supporting_rbps missing")
    elif not isinstance(v["supporting_rbps"], list):
        errors.append("supporting_rbps must be a list")
    if "confidence" not in v:
        errors.append("confidence missing")
    return (len(errors) == 0), errors


def extract_verdict_from_content(content: str) -> dict[str, Any]:
    """Parse LLM prose or pure JSON into a normalized verdict."""
    return normalize_verdict(content)


def normalize_verdict_with_turn_state(
    content_or_raw: Any,
    *,
    thresholds: Optional[dict[str, float]] = None,
    default_mode: str = "unknown",
) -> dict[str, Any]:
    """B3: normalize a verdict AND merge per-turn evidence flags from turn_guards.

    The agent accumulates soft-failure flags (literature offline, AF3 unavailable,
    structure low-plddt, axis skipped, …) in ``turn_guards._EVIDENCE_FLAGS`` as
    tools execute. The LLM's emitted verdict JSON does not carry these, so without
    this merge they never reach ``caveats``. This helper pulls them in before
    normalization so every soft-failure surfaces (evidence-completeness audit).
    """
    # Parse to a raw dict first (reuse the same parsing normalize_verdict would).
    if isinstance(content_or_raw, str):
        parsed = _parse_json_object(content_or_raw)
        raw: dict[str, Any] = parsed if parsed is not None else {
            "explanation": content_or_raw,
            "raw_content": content_or_raw,
        }
    elif content_or_raw is None:
        raw = {}
    elif isinstance(content_or_raw, dict):
        raw = dict(content_or_raw)
    else:
        raw = {"raw": content_or_raw}

    try:
        from nanobot.agent.tools.rbp.turn_guards import authoritative_score, evidence_flags

        turn_flags = evidence_flags() or {}
        score_authority = authoritative_score()
    except Exception:
        turn_flags = {}
        score_authority = None

    if turn_flags:
        existing = raw.get("evidence_flags") or raw.get("flags") or {}
        if isinstance(existing, list):
            existing = {str(x): True for x in existing}
        if not isinstance(existing, dict):
            existing = {}
        # Turn-state flags win only when not already explicitly set by the caller.
        merged = {**turn_flags, **{k: v for k, v in existing.items() if v is not None}}
        raw["evidence_flags"] = merged

    # Absolute numeric boundary: the LLM-returned p_hat/score is ignored. Only a
    # value stored by predict_interaction (RhoBind or delivery vote) may ship.
    if score_authority is None:
        raw["p_hat"] = None
        raw.pop("score", None)
        raw["_deterministic_confidence"] = "low"
        raw["score_source"] = "unavailable"
    else:
        raw["p_hat"] = score_authority.get("p_hat")
        raw.pop("score", None)
        raw["mode"] = score_authority.get("mode") or default_mode
        raw["score_source"] = score_authority.get("source")
        # Authoritative score metadata wins over any LLM-supplied labels.
        if score_authority.get("score_kind") is not None:
            raw["score_kind"] = score_authority.get("score_kind")
        if score_authority.get("score_disclaimer") is not None:
            raw["score_disclaimer"] = score_authority.get("score_disclaimer")
        raw["score_provenance"] = score_authority.get("provenance") or {}
        prov = raw["score_provenance"]
        if isinstance(prov, dict):
            if raw.get("score_kind") is None and prov.get("score_kind") is not None:
                raw["score_kind"] = prov.get("score_kind")
            if (
                raw.get("score_disclaimer") is None
                and prov.get("score_disclaimer") is not None
            ):
                raw["score_disclaimer"] = prov.get("score_disclaimer")
        raw["_deterministic_confidence"] = confidence_from_evidence(
            mode=str(raw["mode"]),
            p_hat=raw["p_hat"],
            evidence_flags=raw.get("evidence_flags") or {},
            provenance=raw["score_provenance"],
        )

    return normalize_verdict(raw, thresholds=thresholds, default_mode=default_mode)


def is_near_match_score(score: Any, threshold: float = 0.95) -> bool:
    """Handle identity in [0,1] or percent [0,100]."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return False
    if s > 1.0 + 1e-9:
        return s >= threshold * 100.0
    return s >= threshold
