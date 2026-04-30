"""Core agent loop for worker execution."""

from __future__ import annotations

import json
import sys
from typing import Any

from loguru import logger

from nanoworker.llm import chat
from nanoworker.protocol import (
    FAILED,
    AssignmentSnapshot,
    WorkerResult,
    extract_decision_data,
    extract_report_sections,
    infer_status,
    result_to_json_dict,
)
from nanoworker.tools import ToolRegistry


def _track_file_changes(tool_calls_log: list[dict[str, Any]]) -> tuple[str, ...]:
    """Extract file paths from write/edit tool calls and flag bash usage."""
    paths: set[str] = set()
    has_bash = False
    for entry in tool_calls_log:
        name = entry["name"]
        if name in ("write", "edit", "write_file", "edit_file"):
            args = entry.get("arguments", {})
            if "path" in args:
                paths.add(args["path"])
        elif name in ("bash", "exec"):
            has_bash = True
    if has_bash:
        paths.add("[bash commands were used - additional files may have changed]")
    return tuple(sorted(paths))


def _merge_reported_files(tracked: tuple[str, ...], reported: tuple[str, ...]) -> tuple[str, ...]:
    paths = set(tracked)
    for item in reported:
        path = item.split(":", 1)[0].strip().strip("`")
        if path:
            paths.add(path)
    return tuple(sorted(paths))


async def run_worker(
    model: str,
    system_prompt: str,
    task: str,
    tools: ToolRegistry,
    max_iterations: int = 30,
    assignment: AssignmentSnapshot | None = None,
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
                status=FAILED,
                summary=f"LLM call failed: {e}",
                iterations=iteration,
                files_changed=_track_file_changes(tool_calls_log),
                assignment=assignment,
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
            status=FAILED,
            summary=final_content,
            iterations=max_iterations,
            files_changed=files_changed,
            assignment=assignment,
        )

    files_changed = _track_file_changes(tool_calls_log)
    summary = final_content[:2000] if final_content else "Task completed"
    report_sections = extract_report_sections(final_content)
    decision_data = extract_decision_data(final_content)

    return WorkerResult(
        status=infer_status(final_content),
        summary=summary,
        iterations=iteration,
        files_changed=_merge_reported_files(files_changed, report_sections["files_changed"]),
        tests_run=report_sections["tests_run"],
        concerns=report_sections["concerns"],
        questions=report_sections["questions"],
        role_fit=decision_data["role_fit"],
        risk_level=decision_data["risk_level"],
        next_recommended_roles=decision_data["next_recommended_roles"],
        handoff=decision_data["handoff"],
        evidence=decision_data["evidence"],
        assignment=assignment,
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
    data = result_to_json_dict(result)
    print(json.dumps(data, ensure_ascii=False), file=sys.stdout)
