"""Tool registry and role-based tool presets."""

from __future__ import annotations

from typing import Any

from nanoworker.tools.base import Tool
from nanoworker.tools.filesystem import (
    EditFileTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)
from nanoworker.tools.shell import ExecTool


class ToolRegistry:
    """Registry of available tools for a worker."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI function-calling tool schemas."""
        return [
            {
                "type": "function",
                "function": tool.schema(),
            }
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'"
        try:
            return await tool.execute(arguments)
        except Exception as e:
            return f"Error executing {name}: {e}"


# Role -> tool preset
ROLE_TOOLS: dict[str, tuple[type[Tool], ...]] = {
    "coder": (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool, ExecTool),
    "debug": (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool, ExecTool),
    "debug-duel": (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool, ExecTool),
    "tester": (ReadFileTool, ListDirTool, ExecTool),
}


def get_tools_for_role(role: str, workspace: str) -> ToolRegistry:
    """Create a ToolRegistry with tools appropriate for the given role."""
    registry = ToolRegistry()
    tool_classes = ROLE_TOOLS.get(role, ROLE_TOOLS["coder"])

    for tool_cls in tool_classes:
        if tool_cls == ExecTool:
            registry.register(tool_cls(cwd=workspace))
        else:
            registry.register(tool_cls())

    return registry
