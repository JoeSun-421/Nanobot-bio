# -*- coding: utf-8 -*-
"""Load / update nanobot-bio/.env (do not commit secrets)."""

from __future__ import annotations

import os
import re
from pathlib import Path


def default_dotenv_path() -> Path:
    """Repo-root ``nanobot-bio/.env`` (gitignored)."""
    return Path(__file__).resolve().parents[1] / ".env"


def load_dotenv(path: Path | None = None, *, override: bool = False) -> Path | None:
    """Parse KEY=VALUE lines from ``.env``. Returns path if loaded, else None."""
    if path is None:
        path = default_dotenv_path()
    path = path.expanduser()
    if not path.is_file():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = val
    return path


_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=")


def upsert_dotenv(
    key: str,
    value: str,
    path: Path | None = None,
    *,
    apply_environ: bool = True,
) -> Path:
    """Create or update ``KEY=value`` in ``.env`` without printing the value.

    Existing keys are replaced in place; new keys are appended. File mode is
    set to ``0o600`` when the OS allows it.
    """
    key = key.strip()
    if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        raise ValueError(f"invalid .env key: {key!r}")
    path = (path or default_dotenv_path()).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Escape nothing exotic — API keys are single-line tokens; quote if needed.
    if any(c in value for c in ' \t#"\'\\') or value == "":
        rendered = f'{key}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"\n'
    else:
        rendered = f"{key}={value}\n"

    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    found = False
    out: list[str] = []
    for line in lines:
        m = _ENV_LINE.match(line.lstrip("\ufeff"))
        if m and m.group(1) == key:
            out.append(rendered)
            found = True
        else:
            out.append(line if line.endswith("\n") else line + "\n")
    if not found:
        if out and not out[-1].endswith("\n"):
            out[-1] = out[-1] + "\n"
        out.append(rendered)

    path.write_text("".join(out), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    if apply_environ:
        os.environ[key] = value
    return path


def read_dotenv_keys(path: Path | None = None) -> dict[str, str]:
    """Return KEY→value map from a ``.env`` file (empty dict if missing)."""
    path = (path or default_dotenv_path()).expanduser()
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key:
            out[key] = val
    return out
