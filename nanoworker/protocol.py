"""Runtime protocol objects for nanoworker."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

DONE = "done"
DONE_WITH_CONCERNS = "done_with_concerns"
NEEDS_CONTEXT = "needs_context"
BLOCKED = "blocked"
FAILED = "failed"

VALID_STATUSES = frozenset({
    DONE,
    DONE_WITH_CONCERNS,
    NEEDS_CONTEXT,
    BLOCKED,
    FAILED,
})
SUCCESS_STATUSES = frozenset({DONE, DONE_WITH_CONCERNS})

REPORT_SECTION_NAMES = {
    "files_changed": {
        "files changed",
        "changed files",
        "files modified",
        "新增/修改的文件",
        "修改的文件",
    },
    "tests_run": {
        "tests run",
        "verification",
        "测试结果",
        "运行的测试",
    },
    "concerns": {
        "concerns",
        "risks",
        "风险",
        "顾虑",
    },
    "questions": {
        "questions",
        "open questions",
        "问题",
        "需要补充",
    },
    "evidence": {
        "evidence",
        "supporting evidence",
        "decision evidence",
        "证据",
    },
    "next_recommended_roles": {
        "next recommended roles",
        "recommended next roles",
        "next roles",
        "suggested next roles",
        "建议后续角色",
        "建议下一角色",
    },
    "handoff": {
        "handoff",
        "handoff notes",
        "handoff note",
        "交接",
        "移交",
    },
    "role_fit": {
        "role fit",
        "role_fit",
        "角色适配",
        "角色匹配",
    },
    "risk_level": {
        "risk level",
        "risk_level",
        "风险等级",
    },
}


@dataclass(frozen=True)
class AssignmentSnapshot:
    worker: str
    base_role: str
    tool_policy: str
    model: str
    assignment_id: str | None = None
    model_profile: str | None = None
    skills: tuple[str, ...] = ()
    role_file: str | None = None


@dataclass(frozen=True)
class WorkerResult:
    status: str
    summary: str
    iterations: int
    files_changed: tuple[str, ...] = ()
    tests_run: tuple[str, ...] = ()
    concerns: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    role_fit: str | None = None
    risk_level: str | None = None
    next_recommended_roles: tuple[str, ...] = ()
    handoff: str = ""
    evidence: tuple[str, ...] = ()
    assignment: AssignmentSnapshot | None = None

    @property
    def success(self) -> bool:
        return self.status in SUCCESS_STATUSES


def normalize_status(status: str | None, default: str = DONE) -> str:
    """Normalize worker status strings into the runtime status vocabulary."""
    if not status:
        return default
    value = status.strip().lower().replace("-", "_").replace(" ", "_")
    if value in VALID_STATUSES:
        return value
    if value in {"success", "completed", "complete"}:
        return DONE
    if value in {"error", "failure"}:
        return FAILED
    return default


def infer_status(final_content: str, default: str = DONE) -> str:
    """Infer status from a worker's final natural-language or JSON response."""
    text = final_content.strip()
    if not text:
        return default

    parsed = _try_parse_json_object(text)
    if parsed:
        return normalize_status(str(parsed.get("status", "")), default=default)

    match = re.search(r"(?im)^\s*(?:status|状态)\s*[:：]\s*([a-zA-Z_\-\s]+)\s*$", text)
    if match:
        return normalize_status(match.group(1), default=default)

    upper = text.upper()
    for marker, status in (
        ("NEEDS_CONTEXT", NEEDS_CONTEXT),
        ("BLOCKED", BLOCKED),
        ("DONE_WITH_CONCERNS", DONE_WITH_CONCERNS),
        ("FAILED", FAILED),
        ("DONE", DONE),
    ):
        if marker in upper:
            return status

    return default


def _try_parse_json_object(text: str) -> dict[str, Any] | None:
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            text = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def result_to_json_dict(result: WorkerResult) -> dict[str, Any]:
    """Return the stable stdout JSON payload for a worker result."""
    payload: dict[str, Any] = {
        "success": result.success,
        "status": result.status,
        "summary": result.summary,
        "files_changed": list(result.files_changed),
        "tests_run": list(result.tests_run),
        "concerns": list(result.concerns),
        "questions": list(result.questions),
        "role_fit": result.role_fit,
        "risk_level": result.risk_level,
        "next_recommended_roles": list(result.next_recommended_roles),
        "handoff": result.handoff,
        "evidence": list(result.evidence),
        "iterations": result.iterations,
    }
    if result.assignment is not None:
        payload["assignment"] = {
            "worker": result.assignment.worker,
            "base_role": result.assignment.base_role,
            "tool_policy": result.assignment.tool_policy,
            "model": result.assignment.model,
            "assignment_id": result.assignment.assignment_id,
            "model_profile": result.assignment.model_profile,
            "skills": list(result.assignment.skills),
            "role_file": result.assignment.role_file,
        }
    return payload


def extract_report_sections(text: str) -> dict[str, tuple[str, ...]]:
    """Extract common final-report list sections from Markdown-ish worker output."""
    sections: dict[str, list[str]] = {key: [] for key in REPORT_SECTION_NAMES}
    current: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        section = _section_key_for_line(line)
        if section is not None:
            current = section
            continue
        if _looks_like_section_heading(line):
            current = None
            continue

        if current is None:
            continue

        item = _extract_list_item(line)
        if item is not None and not _is_empty_item(item):
            sections[current].append(item)

    return {key: tuple(value) for key, value in sections.items()}


def extract_decision_data(text: str) -> dict[str, object]:
    """Extract optional Leader-routing data from JSON or Markdown-ish final output."""
    parsed = _try_parse_json_object(text.strip())
    if parsed:
        return {
            "role_fit": _clean_scalar(_json_value(parsed, "role_fit", "roleFit")),
            "risk_level": _clean_scalar(_json_value(parsed, "risk_level", "riskLevel")),
            "next_recommended_roles": _string_tuple(
                _json_value(parsed, "next_recommended_roles", "nextRecommendedRoles", "next_roles")
            ),
            "handoff": _clean_scalar(_json_value(parsed, "handoff", "handoff_note", "handoffNote")) or "",
            "evidence": _string_tuple(_json_value(parsed, "evidence")),
        }

    sections = extract_report_sections(text)
    role_fit = (
        _extract_inline_value(text, ("role fit", "role_fit", "角色适配", "角色匹配"))
        or _first_item(sections["role_fit"])
    )
    risk_level = (
        _extract_inline_value(text, ("risk level", "risk_level", "风险等级"))
        or _first_item(sections["risk_level"])
    )
    handoff = (
        _extract_inline_value(text, ("handoff", "handoff note", "handoff notes", "交接", "移交"))
        or "\n".join(sections["handoff"])
    )
    return {
        "role_fit": _clean_scalar(role_fit),
        "risk_level": _clean_scalar(risk_level),
        "next_recommended_roles": sections["next_recommended_roles"],
        "handoff": _clean_scalar(handoff) or "",
        "evidence": sections["evidence"],
    }


def _section_key_for_line(line: str) -> str | None:
    label = line.lstrip("#").strip().rstrip(":：").lower()
    for key, names in REPORT_SECTION_NAMES.items():
        if label in names:
            return key
    return None


def _looks_like_section_heading(line: str) -> bool:
    if line.startswith("#"):
        return True
    return line.endswith((":", "：")) and not line.startswith(("-", "*"))


def _extract_list_item(line: str) -> str | None:
    for prefix in ("- ", "* "):
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def _is_empty_item(item: str) -> bool:
    return item.strip().lower() in {"none", "none.", "n/a", "na", "无", "无。"}


def _json_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return () if _is_empty_item(value) else (value.strip(),)
    if isinstance(value, list | tuple):
        items: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and not _is_empty_item(text):
                items.append(text)
        return tuple(items)
    text = str(value).strip()
    return (text,) if text and not _is_empty_item(text) else ()


def _clean_scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list | tuple):
        value = _first_item(tuple(str(item) for item in value))
    text = str(value).strip()
    if not text or _is_empty_item(text):
        return None
    return text


def _first_item(items: tuple[str, ...]) -> str | None:
    return items[0] if items else None


def _extract_inline_value(text: str, labels: tuple[str, ...]) -> str | None:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"(?im)^[^\S\r\n]*(?:{label_pattern})[^\S\r\n]*[:：][^\S\r\n]*(.+?)[^\S\r\n]*$", text)
    return match.group(1).strip() if match else None
