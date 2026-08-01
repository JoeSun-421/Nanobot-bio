"""slim vendor stub."""

from __future__ import annotations

from typing import Any

from nanobot.agent.tools.core.base import Tool
from nanobot.agent.tools.core.tool_configs import ExecToolConfig


class ExecTool(Tool):
    config_key = "exec"

    @classmethod
    def config_cls(cls) -> type[ExecToolConfig]:
        return ExecToolConfig

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return False

    @classmethod
    async def _spawn(cls, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Shell execution is disabled in the slim vendor.")

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "Shell execution is disabled in the slim vendor."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return "Error: shell execution is disabled"
