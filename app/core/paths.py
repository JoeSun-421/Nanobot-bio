# -*- coding: utf-8 -*-
"""Single source of truth for nanobot-bio package + runtime artifact paths.

Code lives under the package root; all run products go under ``artifacts/``
(gitignored) with fixed subdirectories. Legacy locations remain as symlinks
created by :func:`ensure_artifact_dirs`.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo root (nanobot-bio/), not the app/ package dir.
_DEFAULT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(os.environ.get("NANOBOT_BIO_ROOT", _DEFAULT_ROOT)).expanduser().resolve()

ARTIFACTS = PACKAGE_ROOT / "artifacts"
TRACES = ARTIFACTS / "traces"
SESSIONS = ARTIFACTS / "sessions"
REPORTS = ARTIFACTS / "reports"
CACHE = ARTIFACTS / "cache"
STRUCTURE_CACHE = CACHE / "structure"
LITERATURE_CACHE = CACHE / "literature"
PROXY_CACHE = CACHE / "proxy_map.json"
LOGS = ARTIFACTS / "logs"
DIAG = ARTIFACTS / "diag"

# Convenience defaults used by CLI / integrate / eval
DEFAULT_AGENT_TRACE = TRACES / "nanobot_run.jsonl"
DEFAULT_EVAL_TRACE = TRACES / "loo_val.jsonl"
DEFAULT_CHAT_LOG = LOGS / "cli_chat.log"
DEFAULT_LOO_REPORT = REPORTS / "eval_loo_report.json"
DEFAULT_VAL_BATCH = REPORTS / "val_batch_results.json"
DEFAULT_EVOLVE_REPORT = REPORTS / "self_evolution_report.json"

# Compat: legacy workspace sessions → artifacts/sessions
_LEGACY_SESSIONS_LINK = PACKAGE_ROOT / "workspace" / "sessions"


def ensure_artifact_dirs() -> dict[str, Path]:
    """Create artifact subdirs and maintain workspace/sessions compat symlink."""
    for d in (TRACES, SESSIONS, REPORTS, CACHE, STRUCTURE_CACHE, LITERATURE_CACHE, LOGS, DIAG):
        d.mkdir(parents=True, exist_ok=True)

    _ensure_symlink(_LEGACY_SESSIONS_LINK, SESSIONS)
    # Migrate leftover rbp_eval/cache → artifacts/cache, then remove obsolete paths
    _migrate_legacy_proxy_cache()
    for obsolete in (
        PACKAGE_ROOT / "rbp_eval" / "traces",
        PACKAGE_ROOT / "rbp_eval" / "cache",
    ):
        _remove_compat_link(obsolete)

    return {
        "artifacts": ARTIFACTS,
        "traces": TRACES,
        "sessions": SESSIONS,
        "reports": REPORTS,
        "cache": CACHE,
        "structure_cache": STRUCTURE_CACHE,
        "logs": LOGS,
        "diag": DIAG,
    }


def _migrate_legacy_proxy_cache() -> None:
    """Move ``rbp_eval/cache/proxy_map.json`` into ``artifacts/cache/`` once."""
    legacy = PACKAGE_ROOT / "rbp_eval" / "cache" / "proxy_map.json"
    if not legacy.is_file():
        return
    if not PROXY_CACHE.is_file():
        try:
            PROXY_CACHE.parent.mkdir(parents=True, exist_ok=True)
            legacy.replace(PROXY_CACHE)
        except OSError:
            return
    else:
        try:
            legacy.unlink()
        except OSError:
            pass


def _remove_compat_link(link: Path) -> None:
    """Remove leftover symlink or empty/migrated dir under ``rbp_eval``."""
    try:
        if link.is_symlink():
            link.unlink()
            return
        if not link.is_dir():
            return
        # After migration, drop empty cache/traces dirs (ignore .gitkeep-only)
        leftover = [p for p in link.iterdir() if p.name != ".gitkeep"]
        if leftover:
            return
        for p in link.iterdir():
            if p.is_file():
                p.unlink()
        link.rmdir()
    except OSError:
        pass


def _ensure_symlink(link: Path, target: Path) -> None:
    """Point ``link`` at ``target`` if missing or already a correct symlink."""
    try:
        target_rel = os.path.relpath(target, start=link.parent)
    except ValueError:
        target_rel = str(target)

    if link.is_symlink():
        try:
            if link.resolve() == target.resolve():
                return
        except OSError:
            pass
        link.unlink()
    elif link.is_dir():
        # Real directory (pre-migration): leave alone if non-empty and not empty placeholder
        if any(link.iterdir()):
            return
        link.rmdir()
    elif link.exists():
        return

    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target_rel, target_is_directory=True)


def migrate_flat_artifacts() -> list[str]:
    """Move legacy flat ``artifacts/*.json`` into ``artifacts/reports/``."""
    ensure_artifact_dirs()
    moved: list[str] = []
    if not ARTIFACTS.is_dir():
        return moved
    for p in list(ARTIFACTS.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".json", ".jsonl"}:
            continue
        dest = REPORTS / p.name
        if dest.exists():
            continue
        p.rename(dest)
        moved.append(p.name)
    # af3_diag dir → diag/
    old_diag = ARTIFACTS / "af3_diag"
    if old_diag.is_dir() and not old_diag.is_symlink():
        dest_diag = DIAG / "af3_diag"
        if not dest_diag.exists():
            old_diag.rename(dest_diag)
            moved.append("af3_diag/")
    return moved


def resolve_under_package(path: str | Path) -> Path:
    """Resolve a user path; relative paths are under PACKAGE_ROOT."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = PACKAGE_ROOT / p
    return p
