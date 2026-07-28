from __future__ import annotations

from pathlib import Path

import pytest

from app.core.science_request import CanonicalRequest, EvidenceRecord


def test_canonical_request_accepts_identifier_and_sequence():
    req = CanonicalRequest.from_payload(
        {
            "query": "novel",
            "protein_sequence": "MKTIIALSYIFCLVFAD",
            "rna": "ACGUACGU",
            "cohort": "HepG2",
        },
        resolved={"matched": False, "alias": None, "uniprot": None},
    )
    assert req.cohort == "HepG2"
    assert req.target_source == "protein_sequence"
    assert req.rna == "ACGUACGU"
    assert req.alias == "NOVEL"
    assert req.input_provenance.query == "novel"


def test_canonical_request_rejects_rna_as_protein():
    with pytest.raises(ValueError, match="looks like RNA"):
        CanonicalRequest.from_payload({"protein_sequence": "ACGUACGU"})


def test_canonical_request_validates_structure_file(tmp_path: Path):
    cif = tmp_path / "query.cif"
    cif.write_text("data_query\n", encoding="utf-8")
    req = CanonicalRequest.from_payload({"structure_file": str(cif)})
    assert req.target_source == "structure_file"
    assert req.structure_file == str(cif.resolve())


@pytest.mark.parametrize("filename", ["query.mmcif", "query.mcif", "query.ent", "query.pdb.gz"])
def test_canonical_request_accepts_supported_structure_formats(tmp_path: Path, filename: str):
    structure = tmp_path / filename
    structure.write_text("structure\n", encoding="utf-8")
    req = CanonicalRequest.from_payload({"structure_file": str(structure)})
    assert req.structure_file == str(structure.resolve())


def test_canonical_request_normalizes_resolved_ids_and_cohort():
    req = CanonicalRequest.from_payload(
        {"query": "ptbp1", "cohort": "HepG2"},
        resolved={
            "matched": True,
            "alias": "ptbp1",
            "uniprot": "p26599",
            "in_panel": True,
            "head_index": {"HepG2": 7},
        },
    )
    assert req.alias == "PTBP1"
    assert req.uniprot == "P26599"
    assert req.cohort == "HepG2"
    assert req.input_provenance.resolved is True


def test_evidence_record_is_typed_and_serializable():
    row = EvidenceRecord(
        tool="resolve_rbp",
        status="ok",
        source_path="/tmp/tool.py",
        invocation="import_run",
        input_hash="abc",
        source_sha256="def",
        latency_ms=1.2,
    ).to_dict()
    assert row["missing"] is False
    assert row["tool"] == "resolve_rbp"
