"""slim vendor stub."""

from nanobot.agent.tools.legacy.filesystem import _FsTool


class FindFilesTool(_FsTool):
    name = "find_files"


class GrepTool(_FsTool):
    name = "grep"
