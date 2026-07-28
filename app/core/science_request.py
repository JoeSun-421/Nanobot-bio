"""Validated scientific request and immutable evidence transport models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

COHORTS = ("K562", "HepG2")
RNA_ALPHABET = frozenset("ACGUTN")
AA_ALPHABET = frozenset("ABCDEFGHIKLMNPQRSTVWXYZOU")
STRUCTURE_SUFFIXES = (".pdb", ".pdb.gz", ".cif", ".mmcif", ".mcif", ".ent")


def _compact_sequence(value: Any) -> str:
    return "".join(str(value or "").split()).upper()


@dataclass(frozen=True)
class InputProvenance:
    """Typed identity provenance attached to every canonical request."""

    resolved: bool
    query: Optional[str]
    head_index: Any = None
    in_panel: Optional[bool] = None


@dataclass(frozen=True)
class CanonicalRequest:
    """One normalized identity/RNA request at the scientific boundary."""

    cohort: Literal["K562", "HepG2"]
    rna: str = ""
    alias: Optional[str] = None
    uniprot: Optional[str] = None
    protein_sequence: Optional[str] = None
    structure_file: Optional[str] = None
    target_source: str = "unknown"
    input_provenance: InputProvenance = field(
        default_factory=lambda: InputProvenance(False, None)
    )

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        resolved: Optional[dict[str, Any]] = None,
    ) -> "CanonicalRequest":
        cohort = str(payload.get("cohort") or "K562")
        if cohort not in COHORTS:
            raise ValueError(f"cohort must be one of {COHORTS}, got {cohort!r}")

        rna = _compact_sequence(payload.get("rna"))
        if rna and set(rna) - RNA_ALPHABET:
            raise ValueError("RNA contains characters outside A/C/G/U/T/N")

        protein = _compact_sequence(
            payload.get("protein_sequence") or payload.get("sequence")
        )
        if protein and (set(protein) - AA_ALPHABET):
            raise ValueError("protein sequence contains unsupported residues")
        if protein and not (set(protein) - RNA_ALPHABET):
            raise ValueError("protein sequence looks like RNA")

        resolved = dict(resolved or {})
        alias = resolved.get("alias") or payload.get("alias")
        uniprot = resolved.get("uniprot") or payload.get("uniprot")
        if not alias and not uniprot:
            alias = payload.get("query") or payload.get("rbp_id")
        structure = payload.get("structure_file") or payload.get("pdb_path")
        structure_path = None
        if structure:
            path = Path(str(structure)).expanduser().resolve()
            if not path.is_file():
                raise ValueError(f"structure_file does not exist: {path}")
            if not path.name.lower().endswith(STRUCTURE_SUFFIXES):
                raise ValueError(
                    "structure_file must end with "
                    + "/".join(STRUCTURE_SUFFIXES)
                )
            structure_path = str(path)

        if structure_path:
            target_source = "structure_file"
        elif protein:
            target_source = "protein_sequence"
        elif payload.get("uniprot"):
            target_source = "uniprot"
        elif payload.get("alias") or payload.get("query") or payload.get("rbp_id"):
            target_source = "identifier"
        else:
            target_source = "unknown"

        provenance = InputProvenance(
            resolved=bool(resolved.get("matched")),
            query=(
                str(payload.get("query") or payload.get("rbp_id"))
                if payload.get("query") or payload.get("rbp_id")
                else None
            ),
            head_index=resolved.get("head_index"),
            in_panel=(
                bool(resolved.get("in_panel"))
                if resolved.get("in_panel") is not None
                else None
            ),
        )
        return cls(
            cohort=cohort,  # type: ignore[arg-type]
            rna=rna,
            alias=str(alias).strip().upper() if alias else None,
            uniprot=str(uniprot).strip().upper() if uniprot else None,
            protein_sequence=protein or None,
            structure_file=structure_path,
            target_source=target_source,
            input_provenance=provenance,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    """Immutable provenance envelope around one real tool result."""

    tool: str
    status: str
    source_path: Optional[str]
    invocation: Optional[str]
    input_hash: Optional[str]
    source_sha256: Optional[str]
    latency_ms: float
    missing: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: Any) -> Optional[str]:
    candidate = Path(str(path or ""))
    if not candidate.is_file():
        return None
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_payload_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

