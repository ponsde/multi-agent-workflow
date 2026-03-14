"""Core agent loop for worker execution."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

from loguru import logger

from nanoworker.llm import ToolCall, chat
from nanoworker.tools import ToolRegistry


@dataclass(frozen=True)
class WorkerResult:
    success: bool
    summary: str
    iterations: int
    files_changed: tuple[str, ...] = ()


def _track_file_changes(tool_calls_log: list[dict[str, Any]]) -> tuple[str, ...]:
    """Extract file paths from write/edit tool calls and flag exec usage."""
    paths: set[str] = set()
    has_exec = False
    for entry in tool_calls_log:
        name = entry["name"]
        if name in ("write_file", "edit_file"):
            args = entry.get("arguments", {})
            if "path" in args:
                paths.add(args["path"])
        elif name == "exec":
            has_exec = True
    if has_exec:
        paths.add("[exec commands were used - additional files may have changed]")
    return tuple(sorted(paths))


async def run_worker(
    model: str,
    system_prompt: str,
    task: str,
    tools: ToolRegistry,
    max_iterations: int = 30,
) -> WorkerResult:
    """Run the worker agent loop."""

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    tool_schemas = tools.schemas()
    tool_calls_log: list[dict[str, Any]] = []
    final_content = ""

    for iteration in range(1, max_iterations + 1):
        logger.info(f"Iteration {iteration}/{max_iterations}")

        try:
            response = await chat(
                model=model,
                messages=messages,
                tools=tool_schemas if tool_schemas else None,
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return WorkerResult(
                success=False,
                summary=f"LLM call failed: {e}",
                iterations=iteration,
            )

        # No tool calls → final response
        if not response.tool_calls:
            final_content = response.content or ""
            logger.info("Worker finished (no more tool calls)")
            break

        # Build assistant message with tool calls
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in response.tool_calls
            ],
        }
        # Only include content if non-empty (some APIs reject empty content)
        if response.content:
            assistant_msg["content"] = response.content
        messages.append(assistant_msg)

        # Execute each tool call
        for tc in response.tool_calls:
            try:
                args = json.loads(tc.arguments)
            except json.JSONDecodeError:
                args = {}

            logger.info(f"  Tool: {tc.name}({_summarize_args(args)})")

            result = await tools.execute(tc.name, args)

            tool_calls_log.append({
                "name": tc.name,
                "arguments": args,
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
    else:
        final_content = f"Worker reached max iterations ({max_iterations})"
        logger.warning(final_content)

        files_changed = _track_file_changes(tool_calls_log)
        return WorkerResult(
            success=False,
            summary=final_content,
            iterations=max_iterations,
            files_changed=files_changed,
        )

    files_changed = _track_file_changes(tool_calls_log)

    return WorkerResult(
        success=True,
        summary=final_content[:2000] if final_content else "Task completed",
        iterations=iteration,
        files_changed=files_changed,
    )


def _summarize_args(args: dict[str, Any]) -> str:
    """Create a short summary of tool arguments for logging."""
    parts = []
    for key, value in args.items():
        if isinstance(value, str) and len(value) > 60:
            parts.append(f"{key}=...{len(value)} chars...")
        else:
            parts.append(f"{key}={value!r}")
    return ", ".join(parts[:3])


def output_result(result: WorkerResult) -> None:
    """Write JSON result to stdout."""
    data = {
        "success": result.success,
        "summary": result.summary,
        "files_changed": list(result.files_changed),
        "iterations": result.iterations,
    }
    print(json.dumps(data, ensure_ascii=False), file=sys.stdout)
