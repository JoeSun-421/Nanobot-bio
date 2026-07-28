"""slim vendor stub."""

from typing import Any

from nanobot.agent.tools.core.base import Tool
from nanobot.agent.tools.core.tool_configs import FileToolsConfig


class _FsTool(Tool):
    config_key = "file"

    @classmethod
    def config_cls(cls) -> type[FileToolsConfig]:
        return FileToolsConfig

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    @property
    def description(self) -> str:
        return "Filesystem access is disabled in the slim vendor."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return "Error: filesystem access is disabled"


class ReadFileTool(_FsTool):
    name = "read_file"


class WriteFileTool(_FsTool):
    name = "write_file"


class EditFileTool(_FsTool):
    name = "edit_file"


class ListDirTool(_FsTool):
    name = "list_dir"


__all__ = ["EditFileTool", "FileToolsConfig", "ListDirTool", "ReadFileTool", "WriteFileTool", "_FsTool"]
