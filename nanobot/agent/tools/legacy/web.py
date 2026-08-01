"""slim vendor stub."""

from typing import Any

from nanobot.agent.tools.core.base import Tool
from nanobot.agent.tools.core.tool_configs import WebFetchConfig, WebSearchConfig, WebToolsConfig


class _WebStub(Tool):
    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return False

    @property
    def description(self) -> str:
        return "Web access is disabled in the slim vendor."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return "Error: web access is disabled"


class WebSearchTool(_WebStub):
    @property
    def name(self) -> str:
        return "web_search"


class WebFetchTool(_WebStub):
    @property
    def name(self) -> str:
        return "web_fetch"


__all__ = [
    "WebFetchConfig", "WebFetchTool", "WebSearchConfig", "WebSearchTool",
    "WebToolsConfig",
]
