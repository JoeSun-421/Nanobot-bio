"""Quarantined vendored WebUI metadata compatibility.

Terminal scientific execution does not import a WebUI surface. Constants live
here (not under ``nanobot.webui``) so the slim layout gate can forbid that
package while cron still tags proactive websocket deliveries.
"""

from __future__ import annotations

import uuid
from typing import Any

# Formerly nanobot.webui.metadata — kept local so nothing imports nanobot.webui.
WEBUI_MESSAGE_SOURCE_METADATA_KEY = "webui_message_source"
WEBUI_TURN_METADATA_KEY = "webui_turn"


def cron_proactive_delivery_metadata(
    channel: str,
    metadata: dict[str, Any] | None,
    *,
    turn_seed: str,
    source_label: str | None = None,
) -> dict[str, Any]:
    """Return channel metadata for a fresh proactive cron delivery turn."""
    out = dict(metadata or {})
    out.pop(WEBUI_TURN_METADATA_KEY, None)
    if channel == "websocket":
        out[WEBUI_TURN_METADATA_KEY] = f"{turn_seed}:{uuid.uuid4().hex}"
        source: dict[str, str] = {"kind": "cron"}
        if source_label:
            source["label"] = source_label
        out[WEBUI_MESSAGE_SOURCE_METADATA_KEY] = source
    return out
