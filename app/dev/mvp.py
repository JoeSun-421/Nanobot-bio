#!/usr/bin/env python3
"""
Agent MVP acceptance (Agent Owner only — does not modify delivery).

Levels
------
A. Agent package structure + always-on SKILL (Stage 0 playbook)
B. Delivery bridge + Stage-0 own-head wiring (resolve in_panel + examples)
C. Eval-only fixture pipeline (informational; not part of the agent MVP)
D. Near-match helpers + self-evolution modules
E. Nanobot tool registration + execute (whitelist)
F. Nanobot.from_config().run (primary agent path)

Hard gate: A + B + D. Level C never gates MVP.
Exit 0 if the hard gate passes (Level E preferred). Level F completes the primary path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BIO_ROOT = ROOT.parent
# Prefer real nanobot over nanobot-bio/nanobot source stub
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BIO_ROOT))


class Check:
    def __init__(self, name: str, level: str):
        self.name = name
        self.level = level
        self.ok = False
        self.detail = ""

    def pass_(self, detail: str = "") -> None:
        self.ok = True
        self.detail = detail

    def fail(self, detail: str) -> None:
        self.ok = False
        self.detail = detail


def main() -> int:
    try:
        from app.core.chat_ux import configure_chat_logging

        configure_chat_logging(verbose=False)
    except Exception:
        pass

    checks: list[Check] = []

    def add(level: str, name: str) -> Check:
        c = Check(name, level)
        checks.append(c)
        return c

    # ----- A: structure -----
    c = add("A", "SoT nanobot/agent/tools/rbp")
    src = ROOT / "nanobot" / "agent" / "tools" / "rbp"
    need = [
        "predict.py",
        "catalogue.py",
        "seq.py",
        "structure.py",
        "annotation.py",
        "common.py",
        "register.py",
        "__init__.py",
    ]
    missing = [n for n in need if not (src / n).is_file()]
    if missing:
        c.fail(f"missing {missing}")
    else:
        c.pass_(str(src))

    c = add("A", "skill SKILL.md always-on + Stage 0")
    skill = ROOT / "nanobot" / "skills" / "rbp-agent" / "SKILL.md"
    if not skill.is_file():
        c.fail(f"missing {skill}")
    else:
        text = skill.read_text(encoding="utf-8")
        if "Stage 0" not in text or "in_panel" not in text:
            c.fail("SKILL missing Stage 0 / in_panel own-head playbook")
        elif "always: true" not in text:
            c.fail("SKILL must set always: true (inject into system prompt)")
        else:
            c.pass_(str(skill))

    c = add("A", "rbp_eval + app + artifacts")
    ok_files = all(
        (ROOT / p).exists()
        for p in (
            "rbp_eval/evolve/runner.py",
            "rbp_eval/evolve/orchestrator.py",
            "rbp_eval/evolve/proxy_cache.py",
            "rbp_eval/scoring/fuse_hits.py",
            "nanobot/agent/tools/core/base.py",
            "app/core/paths.py",
            "app/core/capability_matrix.py",
            "app/cli/__init__.py",
            "app/agent.py",
            "nanobot/agent/tools/rbp/predict.py",
            "nanobot/skills/rbp-agent/SKILL.md",
            "artifacts",
        )
    )
    if ok_files:
        c.pass_("SoT nanobot/ + rbp_eval/ + app/")
    else:
        c.fail("missing SoT layout pieces")

    c = add("A", "slim in-repo nanobot (framework + rbp SoT)")
    required = ("providers", "__init__.py", "nanobot.py", "agent", "sdk", "session")
    forbidden = ("channels", "webui", "web", "cli", "audio", "bridge", "gateway")
    missing = [n for n in required if not (ROOT / "nanobot" / n).exists()]
    bad = [n for n in forbidden if (ROOT / "nanobot" / n).exists()]
    if missing:
        c.fail(f"slim runtime missing: {missing}")
    elif bad:
        c.fail(f"personal-assistant surface still present: {bad}")
    else:
        try:
            import nanobot as _nb

            _f = str(getattr(_nb, "__file__", "") or "").replace("\\", "/")
            if "nanobot-bio" not in _f:
                c.fail(f"import nanobot must be in-repo, got: {_f}")
            else:
                c.pass_(_f)
        except Exception as e:
            c.fail(str(e))

    c = add("A", "integrate.RBPAgent")
    try:
        from app.agent import RBPAgent, skill_path

        c.pass_(f"skill={skill_path()}")
    except Exception as e:
        c.fail(str(e))

    c = add("A", "verdict schema module")
    try:
        from app.core.verdict_schema import validate_verdict, normalize_verdict

        v = normalize_verdict(
            {
                "label": "Likely",
                "p_hat": 0.6,
                "confidence": "medium",
                "explanation": "test",
                "supporting_rbps": [],
            }
        )
        ok, errs = validate_verdict(v)
        if ok:
            c.pass_("ok")
        else:
            c.fail(str(errs))
    except Exception as e:
        c.fail(str(e))

    # ----- B: delivery bridge -----
    from app.backends.delivery.client import DeliveryToolClient

    c = add("B", "delivery env + resolve_rbp")
    try:
        from app.backends.delivery.env import apply_delivery_env, delivery_root

        apply_delivery_env()
        cli = DeliveryToolClient(offline=True, device="cpu", use_conda=False)
        r = cli.call("resolve_rbp", {"query": "PTBP1"})
        if r.get("matched") and r.get("alias") == "PTBP1":
            c.pass_(f"DELIVERY_ROOT={delivery_root()}")
        else:
            c.fail(str(r)[:200])
    except Exception as e:
        c.fail(str(e))

    c = add("B", "integrate tools pure-python")
    try:
        cli = DeliveryToolClient(offline=True, device="cpu", use_conda=False)
        v = cli.call(
            "similarity_weighted_vote",
            {
                "predictions": [{"alias": "ELAVL1", "prob": 0.8}],
                "hits": [{"alias": "ELAVL1", "score": 0.9}],
            },
        )
        if v.get("score") is not None and not v.get("error"):
            c.pass_(f"score={v.get('score')}")
        else:
            c.fail(str(v)[:200])
    except Exception as e:
        c.fail(str(e))

    c = add("B", "Stage-0 own-head wiring (examples + in_panel)")
    try:
        from app.backends.delivery.examples import load_example, own_head_prompt

        ex = load_example("pos")
        cli = DeliveryToolClient(offline=True, device="cpu", use_conda=False)
        r = cli.call("resolve_rbp", {"query": ex["query"]})
        prompt = own_head_prompt("pos")
        if not r.get("in_panel"):
            c.fail(f"PTBP1 not in_panel: {r}")
        elif len(ex["rna"]) != 128:
            c.fail(f"sample_rna_pos len={len(ex['rna'])} expected 128")
        elif "own-head" not in prompt.lower():
            c.fail("own_head_prompt missing own-head contract")
        else:
            c.pass_(
                f"in_panel alias={r.get('alias')} head={r.get('head_index')} "
                f"rna_len={len(ex['rna'])}"
            )
    except Exception as e:
        c.fail(str(e))

    # ----- C: pipeline removed (informational) -----
    c = add("C", "fixed pipeline removed from product")
    pipe = ROOT / "core" / "pipeline.py"
    llm_tp = ROOT / "core" / "llm_touchpoints.py"
    if pipe.is_file() or llm_tp.is_file():
        c.fail(f"still present: pipeline={pipe.is_file()} llm_touchpoints={llm_tp.is_file()}")
    else:
        c.pass_("core/pipeline + llm_touchpoints deleted; Nanobot.run only")

    # ----- D: near-match plumbing (skill + helpers; not pipeline MVP) -----
    c = add("D", "near_match + self-evolution modules")
    try:
        import yaml
        from app.core.verdict_schema import is_near_match_score
        from rbp_eval.evolve.proposals import tool_attribution
        from rbp_eval.evolve.retune import retune_weights
        from rbp_eval.evolve.proxy_cache import load_proxy_cache

        cfg = yaml.safe_load(
            (ROOT / "config" / "defaults.yaml").read_text(encoding="utf-8")
        )
        thr = float(cfg.get("near_match_seq_identity") or 0)
        skill_txt = (
            ROOT / "nanobot" / "skills" / "rbp-agent" / "SKILL.md"
        ).read_text(encoding="utf-8")
        if thr < 0.9 or not is_near_match_score(0.96, thr):
            c.fail("near_match helper/config broken")
        elif "0.95" not in skill_txt and "near-known" not in skill_txt.lower():
            c.fail("SKILL missing near-known / 0.95 identity path")
        elif not callable(tool_attribution) or not callable(retune_weights):
            c.fail("evaluator missing")
        else:
            _ = load_proxy_cache()
            c.pass_(f"threshold={thr}; evolution APIs ok")
    except Exception as e:
        c.fail(str(e))

    # ----- E: nanobot tools (Stage whitelist, not full delivery surface) -----
    c = add("E", "nanobot Tool register + execute (whitelist)")
    try:
        from nanobot.agent.tools.core.base import Tool  # noqa: F401
        from nanobot.agent.tools.core.registry import ToolRegistry
        from app.backends.delivery.registry import STAGE_RAW_WHITELIST, register_tools
        from app.backends.delivery.client import DeliveryToolClient
        import asyncio

        reg = ToolRegistry()
        client = DeliveryToolClient(offline=True, device="cpu", use_conda=False)
        names = register_tools(reg, client, include_raw_delivery="whitelist")
        banned = {"literature_retrieval", "exec", "spawn"}
        if banned & set(names):
            c.fail(f"noisy tools registered: {sorted(banned & set(names))}")
        elif "literature_retrieval" in names:
            c.fail("literature_retrieval must not be on MVP whitelist")
        else:
            t = reg.get("resolve_rbp") or reg.get("get_known_rbp_list")
            if t is None:
                c.fail(f"no resolve tool in {names[:10]}")
            else:
                raw = asyncio.run(
                    t.execute(query="PTBP1") if t.name == "resolve_rbp" else t.execute()
                )
                data = json.loads(raw)
                if data.get("status") == "ok":
                    n_extra = len([n for n in names if n in STAGE_RAW_WHITELIST])
                    c.pass_(
                        f"n_tools={len(names)} whitelist_extras={n_extra} executed={t.name}"
                    )
                else:
                    c.fail(str(data)[:200])
    except ImportError as e:
        c.fail(f"nanobot not installed: {e}")
    except Exception as e:
        c.fail(str(e))

    # ----- F: primary agent path -----
    c = add("F", "Nanobot.from_config().run (primary agent path)")
    try:
        from app.backends.delivery.examples import own_head_prompt
        from app.agent import RBPAgent

        agent = RBPAgent(
            offline=False,
            prefer_nanobot_llm=True,
            allow_fallback=False,
            auto_install_into_nanobot=True,
        )
        # Prefer Stage-0 own-head prompt; falls back if examples missing.
        try:
            msg = own_head_prompt("pos")
        except Exception:
            msg = "Resolve RBP PTBP1 with tools; if in_panel, stop after one note."
        result = agent.run_sync(msg, session_key="mvp:llm", ephemeral=True)
        if result.mode == "nanobot_llm":
            c.pass_(
                f"mvp_complete={result.mvp_complete} verdict_valid={result.verdict_valid} "
                f"p_hat={(result.verdict or {}).get('p_hat')}"
            )
        else:
            c.fail(f"mode={result.mode} error={result.error}")
    except Exception as e:
        c.fail(str(e))

    # ----- report -----
    print("=" * 64)
    print("Agent MVP acceptance")
    print("=" * 64)
    by_level: dict[str, list[Check]] = {}
    for ch in checks:
        by_level.setdefault(ch.level, []).append(ch)

    # Level C is eval-fixture only and does not gate the agent MVP.
    hard_levels = {"A", "B", "D"}
    hard_ok = True
    for level in ("A", "B", "C", "D", "E", "F"):
        print(f"\n--- Level {level} ---")
        for ch in by_level.get(level, []):
            mark = "PASS" if ch.ok else "FAIL"
            print(f"  [{mark}] {ch.name}: {ch.detail}")
            if level in hard_levels and not ch.ok:
                hard_ok = False

    e_ok = all(ch.ok for ch in by_level.get("E", []))
    f_ok = all(ch.ok for ch in by_level.get("F", []))
    c_ok = all(ch.ok for ch in by_level.get("C", []))

    print("\n" + "=" * 64)
    print("Note: Level C = confirm fixed pipeline deleted. Level F = primary Nanobot path.")
    if hard_ok and f_ok:
        print("RESULT: FULL AGENT MVP PASS (A/B/D + F)")
        code = 0
    elif hard_ok and e_ok:
        print("RESULT: AGENT STRUCTURE+TOOLS PASS (A/B/D/E); need LLM for F")
        code = 0
    elif hard_ok:
        print("RESULT: AGENT STRUCTURE PASS (A/B/D); install tools/LLM for E/F")
        code = 0
    else:
        print("RESULT: FAIL — fix Level A/B/D before claiming agent MVP")
        code = 1
    if not c_ok:
        print("(info) Level C: restore deletion of core/pipeline")

    report = {
        "hard_ok": hard_ok,
        "tools_ok": e_ok,
        "llm_ok": f_ok,
        "pipeline_gone": c_ok,
        "checks": [
            {"level": ch.level, "name": ch.name, "ok": ch.ok, "detail": ch.detail}
            for ch in checks
        ],
    }
    out = ROOT / "artifacts" / "mvp_accept.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return code


if __name__ == "__main__":
    # ensure delivery_root available in nested try blocks
    from app.backends.delivery.env import delivery_root  # noqa: F401

    raise SystemExit(main())
