# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_unwrap_fenced_json_inside_explanation():
    from app.core.verdict_schema import extract_verdict_from_content

    messy = """{
  "label": "No",
  "p_hat": null,
  "confidence": "low",
  "explanation": "```json\\n{\\n  \\"label\\": \\"No\\",\\n  \\"p_hat\\": null,\\n  \\"confidence\\": \\"low\\",\\n  \\"explanation\\": \\"OOM on own-head.\\",\\n  \\"supporting_rbps\\": [{\\"rbp_id\\": \\"P26599\\", \\"alias\\": \\"PTBP1\\", \\"prob\\": null, \\"similarity_score\\": 1.0}]\\n}\\n```",
  "supporting_rbps": []
}"""
    v = extract_verdict_from_content(messy)
    assert v["label"] == "No"
    assert v["p_hat"] is None
    assert "OOM" in v["explanation"]
    assert "```" not in v["explanation"]
    assert v["supporting_rbps"] and v["supporting_rbps"][0]["alias"] == "PTBP1"


def test_parse_markdown_fenced_verdict():
    from app.core.verdict_schema import extract_verdict_from_content

    content = """Here is the result:
```json
{
  "label": "Strong",
  "p_hat": 0.966,
  "confidence": "high",
  "explanation": "Own-head PTBP1 score.",
  "supporting_rbps": [{"alias": "PTBP1", "prob": 0.966, "similarity_score": 1.0}]
}
```
"""
    v = extract_verdict_from_content(content)
    assert v["label"] == "Strong"
    assert abs(float(v["p_hat"]) - 0.966) < 1e-6
    assert "Own-head" in v["explanation"]


def test_terminal_style_nested_fence_in_explanation():
    """Exact failure mode from rbp-agent chat: JSON dumped into explanation."""
    from app.core.chat_ux import format_verdict_display
    from app.core.verdict_schema import extract_verdict_from_content

    # After json.loads of the outer object, explanation has real newlines + fence
    outer = {
        "label": "No",
        "p_hat": None,
        "confidence": "low",
        "explanation": (
            "```json\n"
            "{\n"
            '  "label": "No",\n'
            '  "p_hat": null,\n'
            '  "confidence": "low",\n'
            '  "explanation": "PTBP1 own-head failed with OOM (rc=137).",\n'
            '  "supporting_rbps": [\n'
            '    {"rbp_id": "P26599", "alias": "PTBP1", "prob": null, "similarity_score": 1.0}\n'
            "  ]\n"
            "}\n"
            "```"
        ),
        "supporting_rbps": [],
    }
    import json

    content = json.dumps(outer, ensure_ascii=False)
    v = extract_verdict_from_content(content)
    assert "```" not in v["explanation"]
    assert "{" not in v["explanation"]
    assert "OOM" in v["explanation"]
    assert v["supporting_rbps"][0]["alias"] == "PTBP1"

    from types import SimpleNamespace

    shown = format_verdict_display(SimpleNamespace(content=content, verdict=None))
    assert "```" not in shown
    assert "PTBP1 own-head failed with OOM (rc=137)." in shown


def test_prior_missing_and_structure_flags_force_low_confidence():
    from app.core.verdict_schema import normalize_verdict

    v = normalize_verdict(
        {
            "label": "Likely",
            "p_hat": 0.55,
            "confidence": "high",
            "explanation": "transfer vote",
            "supporting_rbps": [],
            "prior_missing": True,
        }
    )
    assert v["confidence"] == "low"
    assert v.get("prior_missing") is True

    v2 = normalize_verdict(
        {
            "label": "Likely",
            "p_hat": 0.55,
            "confidence": "high",
            "explanation": "sequence-only",
            "supporting_rbps": [],
            "evidence_flags": {"structure_unavailable": True},
        }
    )
    assert v2["confidence"] == "low"


def test_literature_unavailable_does_not_deduct_confidence_points():
    """Literature offline is caveat-only; confidence_from_evidence must ignore it."""
    from app.core.verdict_schema import confidence_from_evidence

    base = dict(
        mode="multi_head",
        p_hat=0.61,
        provenance={
            "aggregation": {
                "terms": [
                    {"donor": "A", "prob": 0.5},
                    {"donor": "B", "prob": 0.6},
                    {"donor": "C", "prob": 0.7},
                ],
                "n_transfer_priors": 3,
                "n_donor_quality": 3,
            },
            "predictions": [
                {"prob": 0.5},
                {"prob": 0.6},
                {"prob": 0.7},
            ],
        },
    )
    without = confidence_from_evidence(
        **base, evidence_flags={"structure_evidence_available": True}
    )
    with_lit = confidence_from_evidence(
        **base,
        evidence_flags={
            "structure_evidence_available": True,
            "literature_unavailable": True,
        },
    )
    assert without == with_lit
    assert with_lit == "medium"


def test_literature_unavailable_still_surfaces_as_caveat_only():
    from app.core.verdict_schema import normalize_verdict

    v = normalize_verdict(
        {
            "label": "Likely",
            "p_hat": 0.61,
            "confidence": "medium",
            "explanation": "transfer vote",
            "supporting_rbps": [],
            "evidence_flags": {"literature_unavailable": True},
            "_deterministic_confidence": "medium",
        }
    )
    assert "literature_unavailable" in (v.get("caveats") or [])
    assert v["confidence"] == "medium"
