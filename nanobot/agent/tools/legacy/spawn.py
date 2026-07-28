"""slim vendor stub."""

from typing import Any

from nanobot.agent.tools.core.base import Tool


class SpawnTool(Tool):
    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return False

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return "Subagent spawning is disabled in the slim vendor."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return "Error: subagent spawning is disabled"
