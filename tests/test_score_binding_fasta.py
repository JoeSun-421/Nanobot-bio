# -*- coding: utf-8 -*-
"""Tests for score_binding_fasta + path allowlist + read_project_doc."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_path_guard_rejects_outside(tmp_path, monkeypatch):
    from nanobot.agent.tools.rbp.path_guard import resolve_allowed_path

    outside = tmp_path / "secret.fasta"
    outside.write_text(">NEG|x\nACGU\n", encoding="utf-8")
    # Only allow ROOT, not tmp_path
    monkeypatch.setenv("RBP_FASTA_ALLOW_ROOTS", str(ROOT))
    with pytest.raises(ValueError, match="outside allowlist"):
        resolve_allowed_path(outside, roots=[ROOT.resolve()])


def test_path_guard_accepts_under_root(tmp_path):
    from nanobot.agent.tools.rbp.path_guard import resolve_allowed_path

    f = tmp_path / "t.fasta"
    f.write_text(">a\nAAAA\n>NEG|b\nCCCC\n", encoding="utf-8")
    got = resolve_allowed_path(f, roots=[tmp_path.resolve()], allowed_suffixes={".fasta"})
    assert got == f.resolve()


def test_run_fasta_score_mock_delivery(tmp_path, monkeypatch):
    from nanobot.agent.tools.rbp import fasta_score as fs

    f = tmp_path / "mini.fasta"
    f.write_text(
        ">POS1\n" + ("A" * 128) + "\n"
        ">NEG|n1\n" + ("C" * 128) + "\n"
        ">POS2\n" + ("G" * 128) + "\n"
        ">NEG|n2\n" + ("T" * 128) + "\n"
        ">POS3\n" + ("AC" * 64) + "\n"
        ">NEG|n3\n" + ("GT" * 64) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RBP_FASTA_ALLOW_ROOTS", str(tmp_path))

    class _Cli:
        def call(self, name, payload):
            assert name == "rhobind_predict"
            rna = payload["rna"]
            # Higher score for A/G rich (crude)
            prob = 0.9 if rna.count("A") + rna.count("G") > 40 else 0.1
            return {"predictions": [{"alias": "FXR2", "prob": prob}]}

    monkeypatch.setattr(fs, "get_delivery_client", lambda **_k: _Cli())
    monkeypatch.setattr(fs, "_score_via_infer", lambda **_k: None)

    out = fs.run_fasta_score(
        path=f,
        rbp="FXR2",
        cohort="K562",
        prefer_infer=False,
        device="cpu",
    )
    assert out.get("ok") is True
    assert out.get("n") == 6
    assert out.get("n_pos") == 3
    assert out.get("n_neg") == 3
    assert out.get("auprc") is not None
    assert Path(out["preds_csv"]).is_file()


def test_score_binding_fasta_tool_requires_rbp(tmp_path, monkeypatch):
    import asyncio

    from nanobot.agent.tools.rbp.fasta_score import ScoreBindingFastaTool

    f = tmp_path / "x.fasta"
    f.write_text(">a\nACGU\n", encoding="utf-8")
    monkeypatch.setenv("RBP_FASTA_ALLOW_ROOTS", str(tmp_path))
    raw = asyncio.run(ScoreBindingFastaTool().execute(path=str(f)))
    env = json.loads(raw)
    assert env.get("status") == "error"


def test_read_project_doc_chunk(tmp_path, monkeypatch):
    from nanobot.agent.tools.rbp import project_doc as pd
    from nanobot.agent.tools.rbp import path_guard as pg

    docs = tmp_path / "docs"
    docs.mkdir()
    md = docs / "guide.md"
    body = "A" * 100 + "B" * 100
    md.write_text(body, encoding="utf-8")

    monkeypatch.setattr(pg, "default_path_roots", lambda: [tmp_path.resolve()])
    monkeypatch.setattr(pg, "doc_extra_roots", lambda: [docs.resolve()])

    out1 = pd.read_project_doc(path=str(md), offset=0, max_chars=100)
    assert out1["ok"] is True
    assert out1["content"] == "A" * 100
    assert out1["eof"] is False
    assert out1["next_offset"] == 100

    out2 = pd.read_project_doc(path=str(md), offset=100, max_chars=100)
    assert out2["content"] == "B" * 100
    assert out2["eof"] is True


def test_read_project_doc_rejects_py(tmp_path, monkeypatch):
    from nanobot.agent.tools.rbp import path_guard as pg

    py = tmp_path / "x.py"
    py.write_text("print(1)\n", encoding="utf-8")
    monkeypatch.setattr(pg, "default_path_roots", lambda: [tmp_path.resolve()])
    monkeypatch.setattr(pg, "doc_extra_roots", lambda: [tmp_path.resolve()])
    with pytest.raises(ValueError, match="suffix"):
        pg.resolve_doc_path(py)


def test_tools_registered():
    from nanobot.agent.tools.rbp import ALL_RBP_TOOL_CLASSES

    names = {cls().name for cls in ALL_RBP_TOOL_CLASSES}
    assert "score_binding_fasta" in names
    assert "read_project_doc" in names
