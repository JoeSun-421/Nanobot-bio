"""slim vendor stub."""

from typing import Any

from nanobot.agent.tools.legacy.filesystem import _FsTool


class ApplyPatchTool(_FsTool):
    @property
    def name(self) -> str:
        return "apply_patch"

    async def execute(self, **kwargs: Any) -> str:
        return "Error: apply_patch is disabled in the slim vendor"
