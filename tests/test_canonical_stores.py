# -*- coding: utf-8 -*-
"""Canonical artifacts layout: sessions / PA memory / domain_memory."""

from __future__ import annotations

from pathlib import Path


def test_describe_canonical_stores_uses_artifacts_symlinks(tmp_path, monkeypatch):
    root = tmp_path / "nanobot-bio"
    (root / "workspace").mkdir(parents=True)
    (root / "artifacts").mkdir()
    monkeypatch.setenv("NANOBOT_BIO_ROOT", str(root))

    # Re-import paths with overridden root.
    import importlib

    import app.core.paths as paths

    importlib.reload(paths)

    dirs = paths.ensure_artifact_dirs()
    assert dirs["sessions"] == root / "artifacts" / "sessions"
    assert dirs["memory"] == root / "artifacts" / "memory"
    assert dirs["proxy_cache"] == root / "artifacts" / "cache" / "proxy_map.json"

    stores = paths.describe_canonical_stores()
    assert stores["sessions"]["canonical"] == str(root / "artifacts" / "sessions")
    assert stores["pa_memory"]["canonical"] == str(root / "artifacts" / "memory")
    assert stores["domain_memory"]["canonical"] == str(
        root / "artifacts" / "cache" / "proxy_map.json"
    )

    ws_sess = root / "workspace" / "sessions"
    ws_mem = root / "workspace" / "memory"
    assert ws_sess.is_symlink()
    assert ws_mem.is_symlink()
    assert ws_sess.resolve() == (root / "artifacts" / "sessions").resolve()
    assert ws_mem.resolve() == (root / "artifacts" / "memory").resolve()
    assert stores["sessions"]["workspace_link"]["ok"] is True
    assert stores["pa_memory"]["workspace_link"]["ok"] is True

    # Restore module for other tests in the same process.
    monkeypatch.delenv("NANOBOT_BIO_ROOT", raising=False)
    importlib.reload(paths)


def test_migrate_dedups_workspace_memory_when_artifacts_has_copy(tmp_path, monkeypatch):
    root = tmp_path / "nanobot-bio"
    art_mem = root / "artifacts" / "memory"
    ws_mem = root / "workspace" / "memory"
    art_mem.mkdir(parents=True)
    ws_mem.mkdir(parents=True)
    (art_mem / "history.jsonl").write_text('{"cursor":1}\n', encoding="utf-8")
    (ws_mem / "history.jsonl").write_text('{"cursor":1}\n', encoding="utf-8")
    monkeypatch.setenv("NANOBOT_BIO_ROOT", str(root))

    import importlib

    import app.core.paths as paths

    importlib.reload(paths)
    paths.ensure_artifact_dirs()

    assert (root / "workspace" / "memory").is_symlink()
    assert (art_mem / "history.jsonl").is_file()

    monkeypatch.delenv("NANOBOT_BIO_ROOT", raising=False)
    importlib.reload(paths)


def test_proxy_cache_fallback_points_at_package_artifacts():
    """Fallback (no app.core.paths) must be package-root artifacts/, not rbp_eval/."""
    import rbp_eval.evolve.proxy_cache as pc

    src = Path(pc.__file__).read_text(encoding="utf-8")
    # parents[2] → nanobot-bio/; parents[1] would wrongly land in rbp_eval/
    assert 'parents[2] / "artifacts" / "cache" / "proxy_map.json"' in src
    expected = Path(pc.__file__).resolve().parents[2] / "artifacts" / "cache" / "proxy_map.json"
    assert expected.parts[-3:] == ("artifacts", "cache", "proxy_map.json")
