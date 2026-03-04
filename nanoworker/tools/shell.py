"""Shell execution tool."""

from __future__ import annotations

import asyncio
from typing import Any

from nanoworker.tools.base import Tool

DEFAULT_TIMEOUT = 120  # seconds


class ExecTool(Tool):
    name = "exec"
    description = "Execute a shell command and return its output (stdout + stderr)."

    def __init__(self, cwd: str = ".", timeout: int = DEFAULT_TIMEOUT) -> None:
        self._cwd = cwd
        self._timeout = timeout

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute.",
                },
            },
            "required": ["command"],
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        command = arguments["command"]
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )

            output_parts = []
            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))
            if stderr:
                output_parts.append(f"STDERR:\n{stderr.decode('utf-8', errors='replace')}")

            output = "\n".join(output_parts) or "(no output)"

            if len(output) > 50_000:
                output = output[:50_000] + "\n... (truncated)"

            return f"Exit code: {proc.returncode}\n{output}"

        except asyncio.TimeoutError:
            return f"Error: command timed out after {self._timeout}s"
        except Exception as e:
            return f"Error executing command: {e}"
