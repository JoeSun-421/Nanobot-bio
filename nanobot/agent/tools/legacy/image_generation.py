"""slim vendor stub."""

from typing import Any

from nanobot.agent.tools.core.base import Tool
from nanobot.agent.tools.core.tool_configs import ImageGenerationToolConfig


class ImageGenerationTool(Tool):
    config_key = "image_generation"

    @classmethod
    def config_cls(cls) -> type[ImageGenerationToolConfig]:
        return ImageGenerationToolConfig

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return False

    @property
    def name(self) -> str:
        return "image_generation"

    @property
    def description(self) -> str:
        return "Image generation is disabled in the slim vendor."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return "Error: image generation is disabled"
