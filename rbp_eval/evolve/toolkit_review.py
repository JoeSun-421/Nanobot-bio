# -*- coding: utf-8 -*-
"""Human review of toolkit expansion proposals (audit only — no auto-install)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.paths import REPORTS_JSON, ensure_artifact_dirs

PROPOSALS_PATH = REPORTS_JSON / "toolkit_proposals.json"
DECISIONS_PATH = REPORTS_JSON / "toolkit_proposals_decisions.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_proposals(path: Path | None = None) -> dict[str, Any]:
    p = path or PROPOSALS_PATH
    if not p.is_file():
        return {"schema": "toolkit_proposals/v1", "proposals": [], "human_review": True}
    return json.loads(p.read_text(encoding="utf-8"))


def load_decisions(path: Path | None = None) -> dict[str, Any]:
    p = path or DECISIONS_PATH
    if not p.is_file():
        return {
            "schema": "toolkit_proposals_decisions/v1",
            "auto_install": False,
            "decisions": [],
        }
    return json.loads(p.read_text(encoding="utf-8"))


def list_proposals(*, proposals_path: Path | None = None) -> list[dict[str, Any]]:
    data = load_proposals(proposals_path)
    return list(data.get("proposals") or [])


def review_proposal(
    proposal_id: str,
    *,
    decision: str,
    note: str = "",
    proposals_path: Path | None = None,
    decisions_path: Path | None = None,
) -> dict[str, Any]:
    """Accept or reject a proposal id; append audit record. Never installs tools."""
    ensure_artifact_dirs()
    decision = str(decision).strip().lower()
    if decision not in ("accept", "reject"):
        raise ValueError("decision must be accept|reject")
    proposals = list_proposals(proposals_path=proposals_path)
    ids = {str(p.get("id")) for p in proposals if isinstance(p, dict)}
    if proposal_id not in ids and proposals:
        # Allow recording even if id unknown (operator override) but flag it
        known = False
    else:
        known = proposal_id in ids or not proposals
    data = load_decisions(decisions_path)
    entry = {
        "ts": _utc(),
        "id": proposal_id,
        "decision": decision,
        "note": note or "",
        "known_proposal": known,
        "auto_install": False,
        "action": "audit_only_no_delivery_install",
    }
    decisions = list(data.get("decisions") or [])
    decisions.append(entry)
    data["decisions"] = decisions
    data["schema"] = "toolkit_proposals_decisions/v1"
    data["auto_install"] = False
    data["updated_at"] = _utc()
    out = decisions_path or DECISIONS_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return entry
