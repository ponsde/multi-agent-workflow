"""File system tools: read, write, edit, list_dir."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nanoworker.tools.base import Tool


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the contents of a file at the given absolute path."

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to read.",
                },
            },
            "required": ["path"],
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        path = Path(arguments["path"])
        if not path.exists():
            return f"Error: file not found: {path}"
        if not path.is_file():
            return f"Error: not a file: {path}"
        try:
            content = path.read_text(encoding="utf-8")
            if len(content) > 100_000:
                return content[:100_000] + f"\n\n... (truncated, total {len(content)} chars)"
            return content
        except Exception as e:
            return f"Error reading {path}: {e}"


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write content to a file at the given absolute path. Creates parent directories if needed."

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file.",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        path = Path(arguments["path"])
        content = arguments["content"]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} chars to {path}"
        except Exception as e:
            return f"Error writing {path}: {e}"


class EditFileTool(Tool):
    name = "edit_file"
    description = "Edit a file by replacing an exact string match with new content."

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to edit.",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact string to find and replace. Must be unique in the file.",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement string.",
                },
            },
            "required": ["path", "old_string", "new_string"],
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        path = Path(arguments["path"])
        old_string = arguments["old_string"]
        new_string = arguments["new_string"]

        if not path.exists():
            return f"Error: file not found: {path}"

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading {path}: {e}"

        count = content.count(old_string)
        if count == 0:
            return f"Error: old_string not found in {path}"
        if count > 1:
            return f"Error: old_string found {count} times in {path}, must be unique"

        updated = content.replace(old_string, new_string, 1)
        try:
            path.write_text(updated, encoding="utf-8")
            return f"Successfully edited {path}"
        except Exception as e:
            return f"Error writing {path}: {e}"


class ListDirTool(Tool):
    name = "list_dir"
    description = "List files and directories at the given path."

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the directory to list.",
                },
            },
            "required": ["path"],
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        path = Path(arguments["path"])
        if not path.exists():
            return f"Error: path not found: {path}"
        if not path.is_dir():
            return f"Error: not a directory: {path}"

        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            lines = []
            for entry in entries[:200]:
                prefix = "d " if entry.is_dir() else "f "
                lines.append(f"{prefix}{entry.name}")
            result = "\n".join(lines)
            if len(entries) > 200:
                result += f"\n... ({len(entries) - 200} more entries)"
            return result
        except Exception as e:
            return f"Error listing {path}: {e}"
