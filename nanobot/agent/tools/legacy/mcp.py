"""slim vendor stub."""

from typing import Any, Mapping


def session_extra(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    return {}


def runtime_lines(message: Any, **kwargs: Any) -> list[str]:
    return []


async def connect_missing_servers(state: Any, registry: Any) -> None:
    return None


async def handle_runtime_control(state: Any, msg: Any, registry: Any) -> bool:
    return False
