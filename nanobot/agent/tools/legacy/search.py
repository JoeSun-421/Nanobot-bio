"""slim vendor stub."""

from nanobot.agent.tools.legacy.filesystem import _FsTool


class FindFilesTool(_FsTool):
    @property
    def name(self) -> str:
        return "find_files"


class GrepTool(_FsTool):
    @property
    def name(self) -> str:
        return "grep"
