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
REPORTS_JSON = REPORTS / "json"
REPORTS_MD = REPORTS / "md"
REPORTS_CSV = REPORTS / "csv"
MEMORY = ARTIFACTS / "memory"
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
DEFAULT_LOO_REPORT = REPORTS_JSON / "eval_loo_report.json"
DEFAULT_VAL_BATCH = REPORTS_JSON / "val_batch_results.json"
DEFAULT_EVOLVE_REPORT = REPORTS_JSON / "self_evolution_report.json"

# Compat: legacy workspace sessions/memory → artifacts/
_LEGACY_SESSIONS_LINK = PACKAGE_ROOT / "workspace" / "sessions"
_LEGACY_MEMORY_LINK = PACKAGE_ROOT / "workspace" / "memory"

_REPORT_SUFFIX_DIRS = {
    ".json": "json",
    ".md": "md",
    ".markdown": "md",
    ".csv": "csv",
}


def report_path(name: str | Path, *, root: Path | None = None) -> Path:
    """Return ``root/{json|md|csv}/<name>`` based on file suffix."""
    root = root or REPORTS
    p = Path(name)
    sub = _REPORT_SUFFIX_DIRS.get(p.suffix.lower())
    if sub is None:
        return root / p.name
    return root / sub / p.name


def find_report(name: str | Path, *, root: Path | None = None) -> Path | None:
    """Locate a report under format subdirs or legacy flat ``root/<name>``."""
    root = root or REPORTS
    p = Path(name)
    for candidate in (report_path(p.name, root=root), root / p.name):
        if candidate.is_file():
            return candidate
    return None


def paired_md_path(json_path: Path) -> Path:
    """Markdown twin for a JSON report (``…/json/x.json`` → ``…/md/x.md``)."""
    json_path = Path(json_path)
    name = json_path.stem + ".md"
    if json_path.parent.name == "json":
        return json_path.parent.parent / "md" / name
    return json_path.with_suffix(".md")


def ensure_artifact_dirs() -> dict[str, Path]:
    """Create artifact subdirs and maintain workspace sessions/memory symlinks."""
    for d in (
        TRACES,
        SESSIONS,
        REPORTS,
        REPORTS_JSON,
        REPORTS_MD,
        REPORTS_CSV,
        MEMORY,
        CACHE,
        STRUCTURE_CACHE,
        LITERATURE_CACHE,
        LOGS,
        DIAG,
    ):
        d.mkdir(parents=True, exist_ok=True)

    _ensure_symlink(_LEGACY_SESSIONS_LINK, SESSIONS)
    _migrate_workspace_memory()
    # Migrate leftover rbp_eval/cache → artifacts/cache, then remove obsolete paths
    _migrate_legacy_proxy_cache()
    migrate_reports_by_format()
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
        "reports_json": REPORTS_JSON,
        "reports_md": REPORTS_MD,
        "reports_csv": REPORTS_CSV,
        "memory": MEMORY,
        "cache": CACHE,
        "structure_cache": STRUCTURE_CACHE,
        "logs": LOGS,
        "diag": DIAG,
        "proxy_cache": PROXY_CACHE,
    }


def describe_canonical_stores() -> dict[str, dict[str, object]]:
    """Return layout status for sessions / PA memory / domain memory (proxy_cache).

    Canonical data lives under ``artifacts/``. ``workspace/sessions`` and
    ``workspace/memory`` are compatibility symlinks only.
    """
    ensure_artifact_dirs()

    def _link_status(link: Path, target: Path) -> dict[str, object]:
        ok = False
        kind = "missing"
        points_to: str | None = None
        if link.is_symlink():
            kind = "symlink"
            try:
                points_to = str(link.readlink())
                ok = link.resolve() == target.resolve()
            except OSError:
                ok = False
        elif link.is_dir():
            kind = "directory"
            try:
                ok = link.resolve() == target.resolve()
            except OSError:
                ok = False
        elif link.exists():
            kind = "other"
        return {
            "path": str(link),
            "kind": kind,
            "points_to": points_to,
            "canonical": str(target),
            "ok": ok,
        }

    return {
        "sessions": {
            "canonical": str(SESSIONS),
            "role": "chat_transcripts",
            "workspace_link": _link_status(_LEGACY_SESSIONS_LINK, SESSIONS),
        },
        "pa_memory": {
            "canonical": str(MEMORY),
            "role": "personal_assistant_memory",
            "files": ["MEMORY.md", "history.jsonl", ".dream_cursor"],
            "workspace_link": _link_status(_LEGACY_MEMORY_LINK, MEMORY),
            "note": "Disabled in scientific_mode (no MEMORY.md injection / Dream).",
        },
        "domain_memory": {
            "canonical": str(PROXY_CACHE),
            "role": "domain_memory",
            "exists": PROXY_CACHE.is_file(),
            "note": "proxy_map.json; promote_from_traces only. Not PA memory.",
        },
    }


def _migrate_workspace_memory() -> None:
    """Move ``workspace/memory`` into ``artifacts/memory/`` once; keep symlink."""
    legacy = _LEGACY_MEMORY_LINK
    MEMORY.mkdir(parents=True, exist_ok=True)
    if legacy.is_symlink():
        _ensure_symlink(legacy, MEMORY)
        return
    if legacy.is_dir():
        for p in list(legacy.iterdir()):
            dest = MEMORY / p.name
            if dest.exists():
                # Prefer artifacts copy; drop duplicate leftover under workspace.
                try:
                    if p.is_file() or p.is_symlink():
                        p.unlink()
                    elif p.is_dir() and not any(p.iterdir()):
                        p.rmdir()
                except OSError:
                    pass
                continue
            try:
                p.rename(dest)
            except OSError:
                continue
        leftover = [p for p in legacy.iterdir() if p.name != ".gitkeep"]
        if leftover:
            # Do not leave a parallel real directory silently; doctor reports this.
            return
        try:
            for p in list(legacy.iterdir()):
                if p.is_file():
                    p.unlink()
            legacy.rmdir()
        except OSError:
            return
    elif legacy.exists():
        return
    _ensure_symlink(legacy, MEMORY)


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


def migrate_reports_by_format() -> list[str]:
    """Move flat ``artifacts/reports/*.{json,md,csv}`` into format subdirs."""
    moved: list[str] = []
    if not REPORTS.is_dir():
        return moved
    for sub in (REPORTS_JSON, REPORTS_MD, REPORTS_CSV):
        sub.mkdir(parents=True, exist_ok=True)
    for p in list(REPORTS.iterdir()):
        if not p.is_file():
            continue
        dest = report_path(p.name)
        if dest.parent == REPORTS or dest.exists():
            continue
        try:
            p.rename(dest)
            moved.append(p.name)
        except OSError:
            continue
    return moved


def migrate_flat_artifacts() -> list[str]:
    """Move legacy flat ``artifacts/*.json`` into ``artifacts/reports/json/``."""
    ensure_artifact_dirs()
    moved: list[str] = []
    if not ARTIFACTS.is_dir():
        return moved
    for p in list(ARTIFACTS.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".json", ".jsonl"}:
            continue
        dest = report_path(p.name) if p.suffix.lower() == ".json" else REPORTS / p.name
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        p.rename(dest)
        moved.append(p.name)
    # af3_diag dir → diag/
    old_diag = ARTIFACTS / "af3_diag"
    if old_diag.is_dir() and not old_diag.is_symlink():
        dest_diag = DIAG / "af3_diag"
        if not dest_diag.exists():
            old_diag.rename(dest_diag)
            moved.append("af3_diag/")
    moved.extend(migrate_reports_by_format())
    return moved


def resolve_under_package(path: str | Path) -> Path:
    """Resolve a user path; relative paths are under PACKAGE_ROOT."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = PACKAGE_ROOT / p
    return p
