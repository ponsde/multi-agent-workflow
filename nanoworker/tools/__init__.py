"""Tool registry and tool-policy presets."""

from __future__ import annotations

from typing import Any

from nanoworker.tools.base import Tool
from nanoworker.tools.filesystem import (
    EditTool,
    FindTool,
    GrepTool,
    LsTool,
    ReadTool,
    WriteTool,
)
from nanoworker.tools.shell import BashTool


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


class TestWriteTool(WriteTool):
    """Write tool constrained to test/spec-looking paths."""

    description = "Write content to a test/spec file in the workspace. Creates parent directories if needed."

    def __init__(self, workspace: str) -> None:
        super().__init__(workspace, write_policy="tests")


class TestEditTool(EditTool):
    """Edit tool constrained to test/spec-looking paths."""

    description = "Edit a test/spec file with one or more exact string replacements."

    def __init__(self, workspace: str) -> None:
        super().__init__(workspace, write_policy="tests")


PRIMARY_TOOL_POLICIES = (
    "product-write",
    "read-only-review",
    "test-write-only",
    "no-shell",
    "read-only-no-shell",
)


# Tool policy -> tool preset. Role names remain accepted as compatibility aliases.
TOOL_POLICIES: dict[str, tuple[type[Tool], ...]] = {
    "product-write": (ReadTool, WriteTool, EditTool, LsTool, GrepTool, FindTool, BashTool),
    "read-only-review": (ReadTool, LsTool, GrepTool, FindTool, BashTool),
    "test-write-only": (ReadTool, TestWriteTool, TestEditTool, LsTool, GrepTool, FindTool, BashTool),
    "no-shell": (ReadTool, WriteTool, EditTool, LsTool, GrepTool, FindTool),
    "read-only-no-shell": (ReadTool, LsTool, GrepTool, FindTool),
    "coder": (ReadTool, WriteTool, EditTool, LsTool, GrepTool, FindTool, BashTool),
    "debug": (ReadTool, WriteTool, EditTool, LsTool, GrepTool, FindTool, BashTool),
    "fixer": (ReadTool, WriteTool, EditTool, LsTool, GrepTool, FindTool, BashTool),
    "reviewer": (ReadTool, LsTool, GrepTool, FindTool, BashTool),
    "debug-duel": (ReadTool, LsTool, GrepTool, FindTool, BashTool),
    "tester": (ReadTool, TestWriteTool, TestEditTool, LsTool, GrepTool, FindTool, BashTool),
}
ROLE_TOOLS = TOOL_POLICIES


ROLE_DEFAULT_TOOL_POLICY: dict[str, str] = {
    "coder": "product-write",
    "debug": "product-write",
    "fixer": "product-write",
    "reviewer": "read-only-review",
    "debug-duel": "read-only-review",
    "tester": "test-write-only",
}


def resolve_tool_policy(role: str, tool_policy: str | None = None) -> str:
    """Resolve a worker role plus optional policy override into a policy name."""
    return tool_policy or ROLE_DEFAULT_TOOL_POLICY.get(role, role)


def get_tools_for_policy(tool_policy: str, workspace: str) -> ToolRegistry:
    """Create a ToolRegistry with tools appropriate for the given tool policy."""
    if tool_policy not in TOOL_POLICIES:
        raise ValueError(f"unknown tool_policy: {tool_policy}")

    registry = ToolRegistry()
    tool_classes = TOOL_POLICIES[tool_policy]

    for tool_cls in tool_classes:
        if tool_cls == BashTool:
            registry.register(tool_cls(cwd=workspace))
        else:
            registry.register(tool_cls(workspace))

    return registry


def get_tools_for_role(role: str, workspace: str) -> ToolRegistry:
    """Create a ToolRegistry with the default tools for a role."""
    return get_tools_for_policy(resolve_tool_policy(role), workspace)
