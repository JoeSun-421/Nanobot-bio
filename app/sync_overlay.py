# -*- coding: utf-8 -*-
"""Compatibility re-export — prefer ``app.bootstrap.sync_overlay``.

Keeps ``python -m app.sync_overlay`` working.
"""

from __future__ import annotations

from app.bootstrap.sync_overlay import (  # noqa: F401
    _link_or_copy,
    main,
    sync_overlay,
)

__all__ = ["_link_or_copy", "main", "sync_overlay"]


if __name__ == "__main__":
    raise SystemExit(main())
