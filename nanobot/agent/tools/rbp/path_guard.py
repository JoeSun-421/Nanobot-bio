# -*- coding: utf-8 -*-
"""Allowlisted path resolution for score_binding_fasta / read_project_doc."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional, Sequence


def _env_roots(var: str) -> list[Path]:
    raw = (os.environ.get(var) or "").strip()
    if not raw:
        return []
    out: list[Path] = []
    for part in raw.split(":"):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(Path(part).expanduser().resolve())
        except OSError:
            continue
    return out


def default_path_roots() -> list[Path]:
    """Roots allowed for any controlled file tool (FASTA or MD)."""
    roots: list[Path] = []
    try:
        cwd = Path.cwd().resolve()
        roots.append(cwd)
    except OSError:
        pass
    bio = os.environ.get("NANOBOT_BIO_ROOT") or os.environ.get("NANOBOT_BIO")
    if bio:
        try:
            roots.append(Path(bio).expanduser().resolve())
        except OSError:
            pass
    else:
        # Infer package root: …/nanobot-bio/nanobot/agent/tools/rbp/path_guard.py
        try:
            pkg = Path(__file__).resolve().parents[4]
            roots.append(pkg)
        except (IndexError, OSError):
            pass
    try:
        from nanobot.agent.tools.rbp.common import ensure_nanobot_bio_on_path

        ensure_nanobot_bio_on_path()
        from app.backends.delivery.env import resolve_delivery_paths

        droot = resolve_delivery_paths().get("delivery_root")
        if droot:
            roots.append(Path(droot).expanduser().resolve())
    except Exception:
        dr = os.environ.get("DELIVERY_ROOT")
        if dr:
            try:
                roots.append(Path(dr).expanduser().resolve())
            except OSError:
                pass
    roots.extend(_env_roots("RBP_FASTA_ALLOW_ROOTS"))
    roots.extend(_env_roots("RBP_DOC_ALLOW_ROOTS"))
    # Dedup preserving order
    seen: set[str] = set()
    uniq: list[Path] = []
    for r in roots:
        key = str(r)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_allowed_path(
    path: str | Path,
    *,
    roots: Optional[Sequence[Path]] = None,
    allowed_suffixes: Optional[Iterable[str]] = None,
) -> Path:
    """Resolve ``path`` and ensure it stays inside an allowlisted root.

    Raises ``ValueError`` with a short reason on failure.
    """
    raw = str(path or "").strip()
    if not raw:
        raise ValueError("path required")
    # Reject obvious traversal tokens before resolve
    if "\x00" in raw:
        raise ValueError("invalid path")
    p = Path(raw).expanduser()
    try:
        resolved = p.resolve(strict=True)
    except FileNotFoundError as e:
        raise ValueError(f"path not found: {raw}") from e
    except OSError as e:
        raise ValueError(f"cannot resolve path: {raw}") from e
    if not resolved.is_file():
        raise ValueError(f"not a file: {resolved}")

    allow = list(roots) if roots is not None else default_path_roots()
    if not any(_is_under(resolved, r) for r in allow):
        raise ValueError(
            f"path outside allowlist: {resolved}. "
            "Allowed under DELIVERY_ROOT / NANOBOT_BIO_ROOT / cwd / "
            "RBP_FASTA_ALLOW_ROOTS / RBP_DOC_ALLOW_ROOTS."
        )
    if allowed_suffixes is not None:
        suf = resolved.suffix.lower()
        ok = {s.lower() if s.startswith(".") else f".{s.lower()}" for s in allowed_suffixes}
        if suf not in ok:
            raise ValueError(f"suffix {suf!r} not allowed; expected one of {sorted(ok)}")
    return resolved


def doc_extra_roots() -> list[Path]:
    """Tighter roots for markdown docs (subset / overlay of default roots)."""
    roots: list[Path] = []
    try:
        pkg = Path(__file__).resolve().parents[4]  # nanobot-bio
    except (IndexError, OSError):
        pkg = None
    if pkg is not None:
        roots.extend(
            [
                pkg / "docs",
                pkg / "nanobot" / "skills",
                pkg / "workspace" / "skills",
                pkg,  # root README.md etc. (file must still be .md)
            ]
        )
    roots.extend(_env_roots("RBP_DOC_ALLOW_ROOTS"))
    out: list[Path] = []
    for r in roots:
        try:
            out.append(r.resolve())
        except OSError:
            continue
    return out


def resolve_doc_path(path: str | Path) -> Path:
    """Allowlisted markdown under docs/skills/package root."""
    resolved = resolve_allowed_path(
        path,
        roots=default_path_roots(),
        allowed_suffixes={".md", ".markdown"},
    )
    # Must also sit under a doc-oriented root (or RBP_DOC_ALLOW_ROOTS already in default).
    doc_roots = doc_extra_roots()
    if not any(_is_under(resolved, r) for r in doc_roots):
        raise ValueError(
            f"markdown path not under docs/skills allowlist: {resolved}. "
            "Use nanobot-bio/docs/, nanobot/skills/, workspace/skills/, "
            "or RBP_DOC_ALLOW_ROOTS."
        )
    return resolved


__all__ = [
    "default_path_roots",
    "doc_extra_roots",
    "resolve_allowed_path",
    "resolve_doc_path",
]
