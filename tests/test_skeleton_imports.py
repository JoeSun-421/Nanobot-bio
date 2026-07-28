# -*- coding: utf-8 -*-
"""Layout + import smoke (agent path, not pipeline MVP)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_layout_proposal_paths():
    tools = ROOT / "nanobot" / "agent" / "tools"
    assert (tools / "rbp" / "predict.py").is_file()
    assert (tools / "core" / "base.py").is_file()
    assert (tools / "legacy" / "message.py").is_file()
    assert list(tools.glob("*.py")) == [tools / "__init__.py"]
    assert (ROOT / "nanobot" / "skills" / "rbp-agent" / "SKILL.md").is_file()
    assert (ROOT / "nanobot" / "legacy" / "apps").is_dir()
    assert not (ROOT / "nanobot" / "apps").exists()
    reval = ROOT / "rbp_eval"
    assert (reval / "evolve" / "runner.py").is_file()
    assert (reval / "evolve" / "orchestrator.py").is_file()
    assert (reval / "scoring" / "fuse_hits.py").is_file()
    assert (reval / "evolve" / "proxy_cache.py").is_file()
    assert (reval / "runtime" / "nanobot_hooks.py").is_file()
    assert not (reval / "evaluator.py").exists()
    assert not (reval / "fuse_hits.py").exists()
    assert (ROOT / "app" / "backends" / "delivery" / "client.py").is_file()
    assert (ROOT / "app" / "cli" / "__init__.py").is_file()
    assert (ROOT / "app" / "agent.py").is_file()
    assert (ROOT / "app" / "integrate.py").is_file()  # compat re-export → app.agent
    assert (ROOT / "app" / "core" / "capability_matrix.py").is_file()
    assert not (ROOT / "cli.py").exists()
    assert not (ROOT / "integrate.py").exists()
    # Removed shims / obsolete product dirs / fixed pipeline
    assert not (ROOT / "rbp_tools").exists()
    assert not (ROOT / "demos").exists()
    assert not (ROOT / "out").exists()
    assert not (ROOT / "core" / "pipeline.py").exists()
    assert not (ROOT / "app" / "core" / "pipeline.py").exists()
    assert not (ROOT / "app" / "eval").exists()
    # Product core surface
    assert (ROOT / "app" / "core" / "verdict_schema.py").is_file()
    assert (ROOT / "app" / "core" / "onboard.py").is_file()
    assert (ROOT / "app" / "core" / "chat_ux.py").is_file()


def test_rbp_eval_modules_importable():
    """Eval package modules should be real modules (not dead shims)."""
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits
    from rbp_eval.scoring.fuse_hits import fuse_proxy_candidates
    from rbp_eval.runtime.nanobot_hooks import RBPTraceHook
    from rbp_eval.evolve.proxy_cache import lookup_proxies, promote_from_traces

    assert callable(fuse_rbp_hits)
    assert callable(fuse_proxy_candidates)
    assert callable(lookup_proxies)
    assert callable(promote_from_traces)
    assert hasattr(RBPTraceHook, "emit_query_end")


def test_skill_sot_matches_workspace_copy():
    from app.integrate import ensure_workspace_skill
    from app.sot import skill_md

    sot_path = skill_md()
    assert sot_path.is_file()
    sot = sot_path.read_text(encoding="utf-8")
    ws = ensure_workspace_skill()
    assert ws.is_file()
    assert sot == ws.read_text(encoding="utf-8")


def test_verdict_schema():
    from app.core.verdict_schema import normalize_verdict, validate_verdict

    v = normalize_verdict(
        {
            "label": "Likely",
            "p_hat": 0.6,
            "confidence": "medium",
            "explanation": "ok",
            "supporting_rbps": [],
        }
    )
    ok, errs = validate_verdict(v)
    assert ok, errs


def test_fuse_and_label():
    from app.core.verdict_schema import label_from_p_hat
    from rbp_eval.scoring.fuse_hits import fuse_proxy_candidates
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

    fused = fuse_proxy_candidates(
        {
            "seq": [{"alias": "A", "score": 0.9}],
            "struct": [{"alias": "A", "score": 0.5}],
        },
        n_cand=5,
        tau_drop=0.1,
    )
    assert fused
    assert label_from_p_hat(0.8) in ("Strong", "Likely", "Unlikely", "No")
    donors = fuse_rbp_hits(
        [[{"alias": "ELAVL1", "score": 0.9, "metric": "domain_overlap", "rank": 1}]],
        top_k=3,
    )
    assert isinstance(donors, list)


def test_agent_default_no_fallback():
    from app.integrate import RBPAgent

    # Instantiation may fail without delivery; only check default flag via signature
    import inspect

    sig = inspect.signature(RBPAgent.__init__)
    assert sig.parameters["allow_fallback"].default is False


def test_delivery_resolve():
    from app.backends.delivery.client import DeliveryToolClient
    from app.backends.delivery.env import apply_delivery_env

    apply_delivery_env()
    cli = DeliveryToolClient(offline=True, device="cpu", use_conda=False)
    r = cli.call("resolve_rbp", {"query": "PTBP1"})
    assert r.get("matched")
    assert r.get("alias") == "PTBP1"
