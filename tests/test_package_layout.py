# -*- coding: utf-8 -*-
"""Package layout + import isolation after maturity reorg."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_tools_root_only_init_and_packages():
    tools = ROOT / "nanobot" / "agent" / "tools"
    flat = sorted(p.name for p in tools.glob("*.py"))
    assert flat == ["__init__.py"]
    for name in ("core", "rbp", "legacy"):
        assert (tools / name).is_dir()
        assert (tools / name / "__init__.py").is_file()


def test_rbp_eval_top_level_only_packages():
    reval = ROOT / "rbp_eval"
    py = sorted(p.name for p in reval.glob("*.py"))
    assert set(py) <= {"__init__.py", "__main__.py"}
    for name in ("scoring", "loo", "evolve", "accept", "runtime", "rna", "plans"):
        assert (reval / name).is_dir()


def test_no_old_flat_import_paths_in_repo():
    banned = [
        "from nanobot.agent.tools.base import",
        "from nanobot.agent.tools.shell import",
        "from rbp_eval.fuse_hits import",
        "from rbp_eval.evaluator import",
        "from rbp_eval.loo_eval import",
        "from rbp_eval.proxy_cache import",
        "module: rbp_eval.proxy_cache",
        "module: rbp_eval.fuse_hits",
        "python -m rbp_eval.evaluation_plan",
        "python -m rbp_eval.loo_eval",
        "python -m rbp_eval.runner",
        '"rbp_eval/runner.py"',
        '"rbp_eval/evaluator.py"',
        '"rbp_eval/proxy_cache.py"',
    ]
    roots = [
        ROOT / "nanobot",
        ROOT / "app",
        ROOT / "rbp_eval",
        ROOT / "scripts",
        ROOT / "tests",
        ROOT / ".github",
    ]
    # Docs that must stay accurate after reorg
    extra_files = [
        ROOT / "ARCHITECTURE.md",
        ROOT / "app" / "backends" / "delivery" / "mapping.yaml",
    ]
    offenders: list[str] = []
    paths: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for pat in ("*.py", "*.sh", "*.yml", "*.yaml", "*.md"):
            paths.extend(root.rglob(pat))
    paths.extend(p for p in extra_files if p.is_file())
    for path in paths:
        if "__pycache__" in path.parts or path.name == "test_package_layout.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # layout.py intentionally lists banned paths as must-not-exist checks
        if path.name == "layout.py" and "fail(f\"removed path" in text:
            continue
        for b in banned:
            if b in text:
                offenders.append(f"{path.relative_to(ROOT)}: {b}")
    assert not offenders, "stale import/path leftovers:\n" + "\n".join(offenders)


def test_chat_import_path_does_not_load_evolve_or_loo():
    # Clear packages that might already be loaded in the test process.
    for mod in list(sys.modules):
        if mod == "rbp_eval" or mod.startswith("rbp_eval."):
            del sys.modules[mod]
    importlib.invalidate_caches()
    from nanobot.config.schema import Config

    Config()
    loaded = [m for m in sys.modules if m.startswith("rbp_eval.")]
    assert not any(m.startswith("rbp_eval.evolve") for m in loaded), loaded
    assert not any(m.startswith("rbp_eval.loo") for m in loaded), loaded


def test_real_path_imports():
    from nanobot.agent.tools.core.base import Tool
    from nanobot.agent.tools.legacy.message import MessageTool
    from rbp_eval.scoring.fuse_hits import aggregate_probability
    from rbp_eval.evolve.orchestrator import run_self_evolution

    assert Tool
    assert MessageTool
    assert callable(aggregate_probability)
    assert callable(run_self_evolution)


def test_sot_skill_and_tools_resolve_under_nanobot():
    from app.bootstrap import skill_md, tools_rbp

    skill = skill_md()
    tools = tools_rbp()
    assert skill.is_file()
    assert "nanobot/skills/rbp-agent/SKILL.md" in str(skill).replace("\\", "/")
    assert "/plugin/" not in str(skill).replace("\\", "/")
    assert tools.is_dir()
    for name in ("__init__.py", "common.py", "register.py", "predict.py", "annotation.py"):
        assert (tools / name).is_file(), name


def test_agent_skill_path_uses_sot_not_plugin():
    from app.agent import skill_path
    from app.bootstrap import skill_md

    p = skill_path()
    assert p is not None and p.is_file()
    assert p.resolve() == skill_md().resolve()
    agent_src = (ROOT / "app" / "agent.py").read_text(encoding="utf-8")
    assert "plugin/nanobot" not in agent_src.replace("\\", "/")
    assert "skill_md" in agent_src
    assert (ROOT / "app" / "bootstrap" / "sot.py").is_file()
    assert (ROOT / "app" / "bootstrap" / "sync_overlay.py").is_file()
    assert (ROOT / "app" / "sync_overlay.py").is_file()
    for removed in ("sot.py", "rbp_bootstrap.py", "integrate.py"):
        assert not (ROOT / "app" / removed).is_file(), removed

