"""Agent tools package: core runtime + rbp product + legacy stubs.

CLI examples:
  nanobot-bio nanobot-smoke
  nanobot-bio doctor
  nanobot-bio agent --example pos
"""
from nanobot.agent.tools.core.base import Schema, Tool, tool_parameters
from nanobot.agent.tools.core.context import ToolContext
from nanobot.agent.tools.core.loader import ToolLoader
from nanobot.agent.tools.core.registry import ToolRegistry

__all__ = ["Schema", "Tool", "ToolContext", "ToolLoader", "ToolRegistry", "tool_parameters"]
