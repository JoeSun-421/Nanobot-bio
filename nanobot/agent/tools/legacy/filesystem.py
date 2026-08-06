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
    @property
    def name(self) -> str:
        return "read_file"


class WriteFileTool(_FsTool):
    @property
    def name(self) -> str:
        return "write_file"


class EditFileTool(_FsTool):
    @property
    def name(self) -> str:
        return "edit_file"


class ListDirTool(_FsTool):
    @property
    def name(self) -> str:
        return "list_dir"


__all__ = ["EditFileTool", "FileToolsConfig", "ListDirTool", "ReadFileTool", "WriteFileTool", "_FsTool"]
