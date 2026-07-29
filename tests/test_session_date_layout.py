# -*- coding: utf-8 -*-
"""Session transcripts live under sessions/YYYY-MM-DD/."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from nanobot.session.manager import Session, SessionManager


def test_new_session_saved_under_local_date_folder(tmp_path: Path) -> None:
    mgr = SessionManager(tmp_path)
    session = mgr.get_or_create("chat-123")
    session.add_message("user", "hello")
    mgr.save(session)

    date_dir = tmp_path / "sessions" / session.created_at.strftime("%Y-%m-%d")
    path = date_dir / "chat-123.jsonl"
    assert path.is_file()
    assert not (tmp_path / "sessions" / "chat-123.jsonl").exists()

    listed = mgr.list_sessions()
    assert len(listed) == 1
    assert listed[0]["key"] == "chat-123"
    assert listed[0]["path"] == str(path)


def test_migrate_flat_session_uses_created_at(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    flat = sessions / "chat-old.jsonl"
    flat.write_text(
        json.dumps(
            {
                "_type": "metadata",
                "key": "chat-old",
                "created_at": "2026-07-23T10:00:00",
                "updated_at": "2026-07-23T11:00:00",
                "metadata": {},
                "last_consolidated": 0,
            }
        )
        + "\n"
        + json.dumps(
            {
                "role": "user",
                "content": "prior turn",
                "timestamp": "2026-07-23T10:00:01",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    mgr = SessionManager(tmp_path)
    dest = sessions / "2026-07-23" / "chat-old.jsonl"
    assert dest.is_file()
    assert not flat.exists()

    loaded = mgr.get_or_create("chat-old")
    assert len(loaded.messages) == 1
    assert loaded.messages[0]["content"] == "prior turn"


def test_migrate_flat_falls_back_to_mtime(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    flat = sessions / "chat-mtime.jsonl"
    # No metadata created_at — only a message line.
    flat.write_text(
        json.dumps({"role": "user", "content": "x", "timestamp": "2026-01-01T00:00:00"})
        + "\n",
        encoding="utf-8",
    )
    mtime = datetime(2026, 7, 25, 12, 0, 0).timestamp()
    import os

    os.utime(flat, (mtime, mtime))

    SessionManager(tmp_path)
    assert (sessions / "2026-07-25" / "chat-mtime.jsonl").is_file()
    assert not flat.exists()


def test_delete_and_reload_across_date_layout(tmp_path: Path) -> None:
    mgr = SessionManager(tmp_path)
    s = Session(key="chat:del", created_at=datetime(2026, 7, 28, 9, 0, 0))
    s.add_message("user", "bye")
    mgr.save(s)
    path = tmp_path / "sessions" / "2026-07-28" / "chat_del.jsonl"
    assert path.is_file()

    assert mgr.delete_session("chat:del") is True
    assert not path.exists()
    mgr.invalidate("chat:del")
    again = mgr.get_or_create("chat:del")
    assert again.messages == []
