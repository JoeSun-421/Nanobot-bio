"""slim vendor stub."""

from typing import Any

from nanobot.agent.tools.core.base import Tool
from nanobot.agent.tools.core.tool_configs import CliAppsToolConfig


class CliAppsTool(Tool):
    config_key = "cli_apps"

    @classmethod
    def config_cls(cls) -> type[CliAppsToolConfig]:
        return CliAppsToolConfig

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return False

    @property
    def name(self) -> str:
        return "run_cli_app"

    @property
    def description(self) -> str:
        return "CLI Apps are disabled in the slim vendor."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return "Error: CLI Apps are disabled"
