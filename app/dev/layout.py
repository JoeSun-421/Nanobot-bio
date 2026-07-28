#!/usr/bin/env python3
"""Assert in-repo slim nanobot layout (Proposal §6.2) + import identity."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIO_ROOT = ROOT.parent
RUNTIME = ROOT / "nanobot"

REQUIRED_TOOLS = [
    "predict.py",
    "catalogue.py",
    "seq.py",
    "structure.py",
    "annotation.py",
    "common.py",
    "register.py",
    "__init__.py",
]

# Slim vendor must keep framework core + RBP SoT; must NOT keep personal-assistant surface.
REQUIRED_FRAMEWORK = [
    "__init__.py",
    "nanobot.py",
    "agent",
    "providers",
    "config",
    "sdk",
    "session",
    "bus",
    "command",
    "utils",
    "templates",
]

FORBIDDEN_SURFACE = [
    "channels",
    "webui",
    "web",
    "cli",
    "audio",
    "bridge",
    "gateway",
    "pairing",
    "api",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    skill = RUNTIME / "skills" / "rbp-agent" / "SKILL.md"
    if not skill.is_file():
        fail(f"missing {skill}")

    tools = RUNTIME / "agent" / "tools" / "rbp"
    missing = [n for n in REQUIRED_TOOLS if not (tools / n).is_file()]
    if missing:
        fail(f"missing tools under {tools}: {missing}")

    for name in REQUIRED_FRAMEWORK:
        p = RUNTIME / name
        if not p.exists():
            fail(f"slim runtime missing framework path: {p}")

    for name in FORBIDDEN_SURFACE:
        p = RUNTIME / name
        if p.exists():
            fail(f"slim runtime must not contain personal-assistant surface: {p}")

    for rel in (
        "nanobot/skills/rbp-agent/SKILL.md",
        "nanobot/agent/tools/rbp/predict.py",
        "nanobot/agent/tools/rbp/catalogue.py",
        "nanobot/agent/tools/rbp/seq.py",
        "nanobot/agent/tools/rbp/structure.py",
        "nanobot/agent/tools/rbp/annotation.py",
        "nanobot/agent/tools/rbp/common.py",
        "nanobot/agent/tools/core/base.py",
        "nanobot/agent/tools/legacy/message.py",
        "rbp_eval/evolve/runner.py",
        "rbp_eval/evolve/orchestrator.py",
        "rbp_eval/evolve/promote.py",
        "rbp_eval/scoring/fuse_hits.py",
        "rbp_eval/evolve/proxy_cache.py",
        "rbp_eval/runtime/nanobot_hooks.py",
        "rbp_eval/runtime/hooks.py",
        "app/core/paths.py",
        "app/core/capability_matrix.py",
        "app/cli/__init__.py",
        "app/agent.py",
        "app/backends/delivery",
        "artifacts",
    ):
        if not (ROOT / rel).exists():
            fail(f"missing SoT/agent path: {ROOT / rel}")

    tools_root = ROOT / "nanobot" / "agent" / "tools"
    flat_tools = [p for p in tools_root.glob("*.py") if p.name != "__init__.py"]
    if flat_tools:
        fail(f"tools root must not have flat modules: {[p.name for p in flat_tools]}")
    for banned in (
        "rbp_eval/evaluator.py",
        "rbp_eval/fuse_hits.py",
        "rbp_eval/runner.py",
        "nanobot/apps",
    ):
        if (ROOT / banned).exists():
            fail(f"removed path must not exist: {banned}")

    if (ROOT / "app" / "eval").exists():
        fail("app/eval must not exist — use top-level rbp_eval/")
    if (ROOT / "app" / "_proposal_sot").exists():
        fail("app/_proposal_sot removed — SoT is repo-root nanobot/ only")
    if (ROOT / "rbp_eval" / "fusion.py").exists():
        fail("rbp_eval/fusion.py removed — import rbp_eval.scoring.fuse_hits")

    for rel in (
        "rbp_eval/scoring/fuse_hits.py",
        "rbp_eval/evolve/proxy_cache.py",
        "rbp_eval/runtime/nanobot_hooks.py",
        "rbp_eval/runtime/hooks.py",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if "from app.eval" in text:
            fail(f"{rel} is a broken shim to app.eval")

    runtime = Path(os.environ.get("NANOBOT_SRC", ROOT / "nanobot")).expanduser().resolve()
    if runtime != RUNTIME.resolve():
        # Allow explicit override, but default must be in-repo.
        if not (runtime / "__init__.py").is_file() and not (runtime / "nanobot.py").is_file():
            fail(f"NANOBOT_SRC runtime missing at {runtime}")

    # Prefer in-repo package for import check.
    root_s = str(ROOT)
    while root_s in sys.path:
        sys.path.remove(root_s)
    sys.path.insert(0, root_s)
    bio_s = str(BIO_ROOT)
    while bio_s in sys.path:
        sys.path.remove(bio_s)

    # Drop cached sibling import if present.
    for mod in list(sys.modules):
        if mod == "nanobot" or mod.startswith("nanobot."):
            del sys.modules[mod]

    nb = importlib.import_module("nanobot")
    nb_file = Path(getattr(nb, "__file__", "") or "").resolve()
    nb_s = str(nb_file).replace("\\", "/")
    if "/nanobot-bio/nanobot/" not in nb_s and not nb_s.endswith("/nanobot-bio/nanobot/__init__.py"):
        # Accept either .../nanobot-bio/nanobot/__init__.py
        if "nanobot-bio" not in nb_s or "/nanobot/" not in nb_s:
            fail(f"import nanobot must resolve to in-repo package, got: {nb_file}")

    print("OK: nanobot slim in-repo layout")
    print(f"  runtime={RUNTIME}")
    print(f"  NANOBOT_SRC={runtime}")
    print(f"  import nanobot -> {nb_file}")


if __name__ == "__main__":
    main()
