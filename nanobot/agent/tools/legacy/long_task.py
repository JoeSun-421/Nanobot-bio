"""slim vendor stub."""

from typing import Any

from nanobot.agent.tools.core.base import Tool


class LongTaskTool(Tool):
    name = "long_task"

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return False

    @property
    def description(self) -> str:
        return "Long tasks are disabled in the slim vendor."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return "Error: long tasks are disabled"


class CompleteGoalTool(LongTaskTool):
    name = "complete_goal"
