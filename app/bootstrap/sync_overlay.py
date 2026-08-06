# -*- coding: utf-8 -*-
"""Ensure workspace skill links to in-repo SoT (slim vendor).

After the slim-vendor migration, toolkit SoT *is* the runtime at
``nanobot-bio/nanobot/``. There is no sibling-tree copy. This module only:

1. Ensures ``workspace/skills/rbp-agent/{SKILL.md,references}`` are relative
   symlinks (or fresh copies) to ``nanobot/skills/rbp-agent/``.
2. Verifies ``import nanobot`` resolves under ``nanobot-bio/nanobot``.

Legacy env ``NANOBOT_SRC`` defaults to ``$NANOBOT_BIO_ROOT/nanobot``.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _rel_link_target(src: Path, dst_file: Path) -> str:
    import posixpath

    return posixpath.relpath(src.resolve(), start=dst_file.parent.resolve())


def _link_or_copy(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        try:
            if os.readlink(dst) == _rel_link_target(src, dst):
                return "symlink-fresh"
        except Exception:
            pass
        dst.unlink()
    elif dst.exists():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    try:
        os.symlink(_rel_link_target(src, dst), dst)
        return "symlink"
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return "copy"


def sync_overlay(*, quiet: bool = False) -> int:
    """Validate in-repo runtime + refresh workspace skill links."""
    from app.bootstrap.sot import skill_md, sot_root, tools_rbp

    bio = Path(
        os.environ.get("NANOBOT_BIO_ROOT", Path(__file__).resolve().parents[2])
    ).expanduser().resolve()
    sot = sot_root()
    src_rbp = tools_rbp()
    src_skill = skill_md()
    nanobot_src = Path(
        os.environ.get("NANOBOT_SRC", bio / "nanobot")
    ).expanduser().resolve()
    workspace = Path(
        os.environ.get("NANOBOT_WORKSPACE", bio / "workspace")
    ).expanduser().resolve()

    def _log(msg: str) -> None:
        if not quiet:
            print(msg)

    _log(f"[sync_overlay] SoT={sot}")
    _log(f"[sync_overlay] NANOBOT_SRC={nanobot_src}")
    _log(f"[sync_overlay] WORKSPACE={workspace}")

    if not src_rbp.is_dir():
        print("ERROR: missing SoT tools at", src_rbp, file=sys.stderr)
        return 1
    if not src_skill.is_file():
        print("ERROR: missing SoT skill at", src_skill, file=sys.stderr)
        return 1

    # Slim vendor: SoT must be the runtime tree itself.
    if nanobot_src.resolve() != (bio / "nanobot").resolve():
        _log(
            f"[sync_overlay] WARN: NANOBOT_SRC={nanobot_src} "
            f"(expected in-repo {bio / 'nanobot'})"
        )
    if not (nanobot_src / "__init__.py").is_file() and not (
        nanobot_src / "nanobot.py"
    ).is_file():
        print("ERROR: NANOBOT_SRC is not a nanobot package root:", nanobot_src, file=sys.stderr)
        return 1
    if not (nanobot_src / "agent" / "tools" / "rbp").is_dir():
        print("ERROR: missing agent/tools/rbp under", nanobot_src, file=sys.stderr)
        return 1

    dest_skill_dir = workspace / "skills" / "rbp-agent"
    how_skill = _link_or_copy(src_skill, dest_skill_dir / "SKILL.md")
    _log(f"[sync_overlay] skill ({how_skill}) -> {dest_skill_dir / 'SKILL.md'}")

    src_refs = src_skill.parent / "references"
    if src_refs.is_dir():
        how_refs = _link_or_copy(src_refs, dest_skill_dir / "references")
        _log(f"[sync_overlay] references ({how_refs}) -> {dest_skill_dir / 'references'}")

    # Import identity check (best-effort).
    try:
        # Ensure bio root precedes BIO_ROOT sibling.
        root_s = str(bio)
        while root_s in sys.path:
            sys.path.remove(root_s)
        sys.path.insert(0, root_s)
        # Only nuke + reimport nanobot when it is currently mis-resolved (outside
        # nanobot-bio). Blindly deleting nanobot.* from sys.modules duplicates
        # stateful singletons (e.g. turn_guards) for any code holding old refs —
        # harmful both in-process and across in-process tests. When nanobot already
        # points at the in-repo tree (the normal case) this check is a no-op.
        expected_pkg = (bio / "nanobot").resolve()
        already = sys.modules.get("nanobot")
        need_reimport = True
        already_file = getattr(already, "__file__", None) if already is not None else None
        if already_file:
            try:
                if Path(already_file).resolve().parent == expected_pkg:
                    need_reimport = False
            except OSError:
                need_reimport = True
        if need_reimport:
            for mod in list(sys.modules):
                if mod == "nanobot" or mod.startswith("nanobot."):
                    del sys.modules[mod]
        import nanobot as _nb

        nb_file = Path(_nb.__file__).resolve()
        # Linux checkouts may be Nanobot-bio (case-sensitive); nbio.sh accepts both.
        nb_s = str(nb_file).replace("\\", "/")
        if "nanobot-bio" not in nb_s and "Nanobot-bio" not in nb_s:
            print(
                "WARN: import nanobot resolved outside nanobot-bio:",
                nb_file,
                file=sys.stderr,
            )
        else:
            _log(f"[sync_overlay] import nanobot -> {nb_file}")
    except Exception as exc:
        _log(f"[sync_overlay] import check skipped: {exc!r}")

    _log("[sync_overlay] ok (in-repo SoT == runtime; workspace skill linked)")
    return 0


def main(argv: list[str] | None = None) -> int:
    return sync_overlay()


if __name__ == "__main__":
    raise SystemExit(main())
