"""slim vendor stub."""

from typing import Any

from nanobot.agent.tools.core.base import Tool


class LongTaskTool(Tool):
    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return False

    @property
    def name(self) -> str:
        return "long_task"

    @property
    def description(self) -> str:
        return "Long tasks are disabled in the slim vendor."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return "Error: long tasks are disabled"


class CompleteGoalTool(LongTaskTool):
    @property
    def name(self) -> str:
        return "complete_goal"
