"""Validated agent-to-delivery tool mapping.

``mapping.yaml`` is the App-owned orchestration manifest.  The delivery
``registry.json`` remains authoritative for delivery capabilities, while this
module supplies the fields that registry intentionally does not contain:
script paths, agent wrapper names, stage membership, axis gates, and raw-tool
exposure policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

MAPPING_PATH = Path(__file__).with_name("mapping.yaml")
VALID_STAGES = frozenset({"stage0", "stage1", "stage2", "stage3"})


class MappingValidationError(ValueError):
    """Raised when App mapping and delivery registry cannot be reconciled."""


@dataclass(frozen=True)
class DeliveryBinding:
    agent_name: str
    delivery_name: str
    script: str
    stages: tuple[str, ...]
    axis: str | None
    retrieve: bool
    suppress_raw: bool


def load_tool_mapping(path: Path | None = None) -> dict[str, dict[str, Any]]:
    candidate = Path(path or MAPPING_PATH)
    try:
        raw = yaml.safe_load(candidate.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise MappingValidationError(f"cannot load tool mapping {candidate}: {exc}") from exc
    if not isinstance(raw, dict) or not raw:
        raise MappingValidationError(f"tool mapping {candidate} must be a non-empty object")
    out: dict[str, dict[str, Any]] = {}
    for name, spec in raw.items():
        if not isinstance(name, str) or not isinstance(spec, dict):
            raise MappingValidationError(f"invalid top-level mapping entry {name!r}")
        out[name] = dict(spec)
    return out


def _stages(spec: dict[str, Any], *, agent_name: str) -> tuple[str, ...]:
    raw = spec.get("stages", spec.get("stage"))
    if isinstance(raw, str):
        stages = (raw,)
    elif isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        stages = tuple(dict.fromkeys(raw))
    else:
        raise MappingValidationError(f"{agent_name}: stage/stages metadata is required")
    unknown = set(stages) - VALID_STAGES
    if unknown:
        raise MappingValidationError(f"{agent_name}: unknown stages {sorted(unknown)}")
    return stages


def _binding_nodes(value: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(value, dict):
        return
    if "registry_name" in value or "script" in value:
        yield value
    for child in value.values():
        if isinstance(child, dict):
            yield from _binding_nodes(child)


def delivery_bindings(
    mapping: dict[str, dict[str, Any]] | None = None,
) -> tuple[DeliveryBinding, ...]:
    mapping = mapping or load_tool_mapping()
    bindings: list[DeliveryBinding] = []
    by_delivery: dict[str, DeliveryBinding] = {}
    for agent_name, spec in mapping.items():
        stages = _stages(spec, agent_name=agent_name)
        axis = str(spec["axis"]) if spec.get("axis") else None
        retrieve = bool(spec.get("retrieve"))
        suppress_raw = bool(spec.get("suppress_raw"))
        for node in _binding_nodes(spec):
            delivery_name = node.get("registry_name")
            script = node.get("script")
            if not isinstance(delivery_name, str) or not delivery_name:
                raise MappingValidationError(
                    f"{agent_name}: every script binding needs registry_name"
                )
            if not isinstance(script, str) or not script:
                raise MappingValidationError(
                    f"{agent_name}: delivery binding {delivery_name!r} needs script"
                )
            binding = DeliveryBinding(
                agent_name=agent_name,
                delivery_name=delivery_name,
                script=script,
                stages=stages,
                axis=str(node.get("axis") or axis) if (node.get("axis") or axis) else None,
                retrieve=bool(node.get("retrieve", retrieve)),
                suppress_raw=bool(node.get("suppress_raw", suppress_raw)),
            )
            prior = by_delivery.get(delivery_name)
            if prior is not None and prior.script != binding.script:
                raise MappingValidationError(
                    f"conflicting scripts for {delivery_name!r}: "
                    f"{prior.script!r} vs {binding.script!r}"
                )
            if prior is None:
                by_delivery[delivery_name] = binding
                bindings.append(binding)
    return tuple(bindings)


def delivery_script_map() -> dict[str, str]:
    return {binding.delivery_name: binding.script for binding in delivery_bindings()}


def direct_raw_tool_names(
    mapping: dict[str, dict[str, Any]] | None = None,
) -> frozenset[str]:
    mapping = mapping or load_tool_mapping()
    direct: set[str] = set()
    for agent_name, spec in mapping.items():
        if spec.get("registry_name") == agent_name and spec.get("script"):
            direct.add(agent_name)
    return frozenset(direct)


def curated_tool_names(
    mapping: dict[str, dict[str, Any]] | None = None,
) -> frozenset[str]:
    mapping = mapping or load_tool_mapping()
    return frozenset(mapping) - direct_raw_tool_names(mapping)


def suppressed_raw_delivery_names() -> frozenset[str]:
    return frozenset(
        binding.delivery_name
        for binding in delivery_bindings()
        if binding.suppress_raw
    )


def stage_tool_sets(
    mapping: dict[str, dict[str, Any]] | None = None,
) -> dict[str, frozenset[str]]:
    mapping = mapping or load_tool_mapping()
    out: dict[str, set[str]] = {stage: set() for stage in VALID_STAGES}
    for agent_name, spec in mapping.items():
        for stage in _stages(spec, agent_name=agent_name):
            out[stage].add(agent_name)
    return {stage: frozenset(names) for stage, names in out.items()}


def retrieve_tool_names(
    mapping: dict[str, dict[str, Any]] | None = None,
) -> frozenset[str]:
    mapping = mapping or load_tool_mapping()
    names = {
        agent_name
        for agent_name, spec in mapping.items()
        if bool(spec.get("retrieve"))
    }
    names.update(
        binding.delivery_name
        for binding in delivery_bindings(mapping)
        if binding.retrieve
    )
    return frozenset(names)


def tool_axis_gates(
    mapping: dict[str, dict[str, Any]] | None = None,
) -> dict[str, str]:
    mapping = mapping or load_tool_mapping()
    gates: dict[str, str] = {}
    for agent_name, spec in mapping.items():
        if spec.get("axis"):
            gates[agent_name] = str(spec["axis"])
    for binding in delivery_bindings(mapping):
        if binding.axis:
            gates[binding.delivery_name] = binding.axis
    return gates


def validate_delivery_registry(
    registry: dict[str, Any],
    *,
    delivery_root: Path | None = None,
) -> None:
    """Fail closed when ready registry tools and App bindings diverge."""
    rows = registry.get("tools") if isinstance(registry, dict) else None
    if not isinstance(rows, list):
        raise MappingValidationError("delivery registry needs a tools list")
    registry_names: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise MappingValidationError("delivery registry contains an invalid tool row")
        if row.get("status") == "ready":
            registry_names.add(str(row["name"]))
    scripts = delivery_script_map()
    mapped_names = set(scripts)
    missing = sorted(registry_names - mapped_names)
    stale = sorted(mapped_names - registry_names)
    if missing or stale:
        raise MappingValidationError(
            "delivery registry/mapping mismatch: "
            f"missing_bindings={missing}, stale_bindings={stale}"
        )
    if delivery_root is not None:
        absent = sorted(
            name for name, rel in scripts.items()
            if not (Path(delivery_root) / rel).is_file()
        )
        if absent:
            raise MappingValidationError(
                f"mapped delivery scripts are missing for: {absent}"
            )


__all__ = [
    "DeliveryBinding",
    "MAPPING_PATH",
    "MappingValidationError",
    "curated_tool_names",
    "delivery_bindings",
    "delivery_script_map",
    "direct_raw_tool_names",
    "load_tool_mapping",
    "retrieve_tool_names",
    "stage_tool_sets",
    "suppressed_raw_delivery_names",
    "tool_axis_gates",
    "validate_delivery_registry",
]
