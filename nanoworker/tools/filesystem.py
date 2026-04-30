"""File system tools: read, write, edit, ls, grep, find."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from nanoworker.tools.base import Tool
from nanoworker.tools.pathing import assert_write_allowed, relative_workspace_path, resolve_workspace_path

DEFAULT_READ_LIMIT = 250
MAX_READ_CHARS = 100_000
MAX_LIST_ENTRIES = 200
MAX_SEARCH_RESULTS = 200
SKIP_DIRS = {".git", ".worktrees", "node_modules", ".venv", "__pycache__"}


class ReadTool(Tool):
    name = "read"
    description = "Read a text file in the workspace. Paths may be relative to the workspace or absolute inside it."

    def __init__(self, workspace: str) -> None:
        self._workspace = workspace

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read."},
                "offset": {"type": "integer", "description": "1-indexed line number to start from."},
                "limit": {"type": "integer", "description": "Maximum number of lines to read."},
            },
            "required": ["path"],
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        path = resolve_workspace_path(self._workspace, arguments["path"])
        if not path.exists():
            return f"Error: file not found: {arguments['path']}"
        if not path.is_file():
            return f"Error: not a file: {arguments['path']}"

        offset = max(int(arguments.get("offset", 1)), 1)
        limit = max(int(arguments.get("limit", DEFAULT_READ_LIMIT)), 1)

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            return f"Error reading {arguments['path']}: {e}"

        start = offset - 1
        if start >= len(lines):
            return f"Error: offset {offset} is beyond end of file ({len(lines)} lines)"

        selected = lines[start:start + limit]
        content = "\n".join(selected)
        if len(content) > MAX_READ_CHARS:
            content = content[:MAX_READ_CHARS] + f"\n\n... (truncated at {MAX_READ_CHARS} chars)"

        end = start + len(selected)
        if end < len(lines):
            content += f"\n\n[Showing lines {offset}-{end} of {len(lines)}. Use offset={end + 1} to continue.]"
        return content


class WriteTool(Tool):
    name = "write"
    description = "Write content to a file in the workspace. Creates parent directories if needed."

    def __init__(self, workspace: str, write_policy: str = "default") -> None:
        self._workspace = workspace
        self._write_policy = write_policy

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write."},
                "content": {"type": "string", "description": "Content to write."},
            },
            "required": ["path", "content"],
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        path = resolve_workspace_path(self._workspace, arguments["path"])
        assert_write_allowed(self._workspace, path, policy=self._write_policy)
        content = arguments["content"]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            rel = relative_workspace_path(self._workspace, path)
            return f"Successfully wrote {len(content)} chars to {rel}"
        except Exception as e:
            return f"Error writing {arguments['path']}: {e}"


class EditTool(Tool):
    name = "edit"
    description = "Edit one file with one or more exact string replacements."

    def __init__(self, workspace: str, write_policy: str = "default") -> None:
        self._workspace = workspace
        self._write_policy = write_policy

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to edit."},
                "old_string": {
                    "type": "string",
                    "description": "Legacy single exact string to replace. Prefer edits[].old_string.",
                },
                "new_string": {
                    "type": "string",
                    "description": "Legacy replacement string. Prefer edits[].new_string.",
                },
                "edits": {
                    "type": "array",
                    "description": "Exact replacements applied against the original file.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_string": {"type": "string"},
                            "new_string": {"type": "string"},
                        },
                        "required": ["old_string", "new_string"],
                    },
                },
            },
            "required": ["path"],
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        path = resolve_workspace_path(self._workspace, arguments["path"])
        assert_write_allowed(self._workspace, path, policy=self._write_policy)
        if not path.exists():
            return f"Error: file not found: {arguments['path']}"

        edits = _normalize_edits(arguments)
        if not edits:
            return "Error: provide edits[] or old_string/new_string"

        try:
            original = path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading {arguments['path']}: {e}"

        updated = original
        for edit in edits:
            old = edit["old_string"]
            new = edit["new_string"]
            count = updated.count(old)
            if count == 0:
                return f"Error: old_string not found in {arguments['path']}"
            if count > 1:
                return f"Error: old_string found {count} times in {arguments['path']}, must be unique"
            updated = updated.replace(old, new, 1)

        try:
            path.write_text(updated, encoding="utf-8")
            rel = relative_workspace_path(self._workspace, path)
            return f"Successfully edited {rel} ({len(edits)} replacement{'s' if len(edits) != 1 else ''})"
        except Exception as e:
            return f"Error writing {arguments['path']}: {e}"


class LsTool(Tool):
    name = "ls"
    description = "List files and directories in the workspace."

    def __init__(self, workspace: str) -> None:
        self._workspace = workspace

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to list. Defaults to workspace root."},
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        raw_path = arguments.get("path") or "."
        path = resolve_workspace_path(self._workspace, raw_path)
        if not path.exists():
            return f"Error: path not found: {raw_path}"
        if not path.is_dir():
            return f"Error: not a directory: {raw_path}"

        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception as e:
            return f"Error listing {raw_path}: {e}"

        lines = []
        for entry in entries[:MAX_LIST_ENTRIES]:
            prefix = "d " if entry.is_dir() else "f "
            lines.append(f"{prefix}{entry.name}")
        result = "\n".join(lines)
        if len(entries) > MAX_LIST_ENTRIES:
            result += f"\n... ({len(entries) - MAX_LIST_ENTRIES} more entries)"
        return result


class GrepTool(Tool):
    name = "grep"
    description = "Search text files in the workspace with a regex pattern."

    def __init__(self, workspace: str) -> None:
        self._workspace = workspace

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for."},
                "path": {"type": "string", "description": "File or directory path. Defaults to workspace root."},
                "glob": {"type": "string", "description": "Optional filename glob, e.g. '*.py'."},
            },
            "required": ["pattern"],
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        raw_path = arguments.get("path") or "."
        root = resolve_workspace_path(self._workspace, raw_path)
        try:
            regex = re.compile(arguments["pattern"])
        except re.error as e:
            return f"Error: invalid regex: {e}"

        glob = arguments.get("glob")
        files = [root] if root.is_file() else _iter_text_candidates(root, glob)
        results: list[str] = []
        for file_path in files:
            if len(results) >= MAX_SEARCH_RESULTS:
                break
            try:
                for line_no, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
                    if regex.search(line):
                        rel = relative_workspace_path(self._workspace, file_path)
                        results.append(f"{rel}:{line_no}:{line}")
                        if len(results) >= MAX_SEARCH_RESULTS:
                            break
            except UnicodeDecodeError:
                continue
            except Exception:
                continue

        if not results:
            return "(no matches)"
        output = "\n".join(results)
        if len(results) >= MAX_SEARCH_RESULTS:
            output += f"\n... (truncated at {MAX_SEARCH_RESULTS} matches)"
        return output


class FindTool(Tool):
    name = "find"
    description = "Find file paths in the workspace by glob pattern."

    def __init__(self, workspace: str) -> None:
        self._workspace = workspace

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Filename glob. Defaults to '*'."},
                "path": {"type": "string", "description": "Directory path. Defaults to workspace root."},
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        raw_path = arguments.get("path") or "."
        pattern = arguments.get("pattern") or "*"
        root = resolve_workspace_path(self._workspace, raw_path)
        if not root.exists():
            return f"Error: path not found: {raw_path}"
        if root.is_file():
            return relative_workspace_path(self._workspace, root) if fnmatch.fnmatch(root.name, pattern) else "(no matches)"

        matches: list[str] = []
        for path in _walk_files(root):
            if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(relative_workspace_path(self._workspace, path), pattern):
                matches.append(relative_workspace_path(self._workspace, path))
                if len(matches) >= MAX_SEARCH_RESULTS:
                    break

        if not matches:
            return "(no matches)"
        output = "\n".join(matches)
        if len(matches) >= MAX_SEARCH_RESULTS:
            output += f"\n... (truncated at {MAX_SEARCH_RESULTS} files)"
        return output


def _normalize_edits(arguments: dict[str, Any]) -> list[dict[str, str]]:
    raw_edits = arguments.get("edits")
    if isinstance(raw_edits, list):
        return [
            {"old_string": str(edit["old_string"]), "new_string": str(edit["new_string"])}
            for edit in raw_edits
            if isinstance(edit, dict) and "old_string" in edit and "new_string" in edit
        ]
    if "old_string" in arguments and "new_string" in arguments:
        return [{"old_string": arguments["old_string"], "new_string": arguments["new_string"]}]
    return []


def _iter_text_candidates(root: Path, glob: str | None) -> list[Path]:
    return [path for path in _walk_files(root) if glob is None or fnmatch.fnmatch(path.name, glob)]


def _walk_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return files
