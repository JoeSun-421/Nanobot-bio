"""Cohort-specific RhoBind head lookup shared by product and evaluation paths."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional


def normalize_cohort(cohort: str) -> str:
    value = str(cohort or "K562").strip().lower()
    if value == "k562":
        return "K562"
    if value == "hepg2":
        return "HepG2"
    raise ValueError(f"unsupported cohort: {cohort!r}")


def _canonical_alias(value: object) -> str:
    alias = str(value or "").strip()
    for suffix in ("_K562", "_HepG2"):
        if alias.lower().endswith(suffix.lower()):
            alias = alias[: -len(suffix)]
            break
    return alias.upper()


@lru_cache(maxsize=8)
def _load_aliases(release: str, cohort: str) -> frozenset[str]:
    name = (
        "head_index_k562.json"
        if cohort == "K562"
        else "head_index_hepg2.json"
    )
    path = Path(release) / "checkpoints" / name
    raw = json.loads(path.read_text(encoding="utf-8"))
    aliases = {
        _canonical_alias(alias)
        for alias in (raw.get("alias_to_head") or {})
        if _canonical_alias(alias)
    }
    aliases.update(
        _canonical_alias(alias)
        for alias in (raw.get("order") or [])
        if _canonical_alias(alias)
    )
    return frozenset(aliases)


def cohort_head_aliases(
    cohort: str,
    *,
    release: Optional[Path] = None,
) -> set[str]:
    """Return canonical aliases with a real head in exactly ``cohort``."""
    normalized = normalize_cohort(cohort)
    if release is None:
        from app.backends.delivery.env import resolve_delivery_paths

        release = resolve_delivery_paths()["rhobind_release"]
    return set(_load_aliases(str(Path(release).resolve()), normalized))


def alias_has_cohort_head(
    query: str,
    *,
    cohort: str,
    aliases: Optional[set[str]] = None,
) -> bool:
    """Return whether alias or UniProt ID resolves to a head in ``cohort``."""
    normalized = normalize_cohort(cohort)
    allowed = aliases if aliases is not None else cohort_head_aliases(normalized)
    token = _canonical_alias(query)
    if not token:
        return False
    if token in allowed:
        return True

    try:
        from app.backends.delivery.env import load_rbp_registry

        registry = load_rbp_registry()
    except Exception:
        return False
    for uniprot, record in registry.items():
        if not isinstance(record, dict):
            continue
        alias = _canonical_alias(record.get("alias"))
        if token not in {_canonical_alias(uniprot), alias}:
            continue
        heads = record.get("head_index") or {}
        return isinstance(heads, dict) and heads.get(normalized) is not None
    return False


__all__ = [
    "alias_has_cohort_head",
    "cohort_head_aliases",
    "normalize_cohort",
]
