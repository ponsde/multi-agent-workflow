"""Assignment journal support."""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nanoworker.config import Config
from nanoworker.protocol import WorkerResult, result_to_json_dict

DEFAULT_JOURNAL_PATH = Path.home() / ".nanoworker" / "journal.jsonl"
FEEDBACK_EVENT = "leader_feedback"
FEEDBACK_TARGET_TYPES = frozenset({"role_card", "skill", "base_role", "model", "assignment"})


@dataclass(frozen=True)
class JournalTarget:
    enabled: bool
    path: Path


def resolve_journal_target(
    config: Config,
    enabled_override: bool | None = None,
    path_override: Path | None = None,
) -> JournalTarget:
    """Resolve journal settings from CLI, env, config, then defaults."""
    enabled = config.journal.enabled
    env_enabled = os.environ.get("NANOWORKER_JOURNAL")
    if env_enabled is not None:
        enabled = env_enabled.strip().lower() in {"1", "true", "yes", "on"}
    if enabled_override is not None:
        enabled = enabled_override

    path_value = (
        str(path_override)
        if path_override is not None
        else os.environ.get("NANOWORKER_JOURNAL_PATH") or config.journal.path
    )
    path = Path(path_value).expanduser() if path_value else DEFAULT_JOURNAL_PATH
    return JournalTarget(enabled=enabled, path=path)


def append_journal_entry(result: WorkerResult, path: Path) -> None:
    """Append a sanitized assignment result entry to a JSONL journal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result_to_json_dict(result)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assignment": payload.get("assignment"),
        "status": payload["status"],
        "success": payload["success"],
        "iterations": payload["iterations"],
        "files_changed": payload["files_changed"],
        "tests_run": payload["tests_run"],
        "concerns": payload["concerns"],
        "questions": payload["questions"],
        "role_fit": payload["role_fit"],
        "risk_level": payload["risk_level"],
        "next_recommended_roles": payload["next_recommended_roles"],
        "handoff": payload["handoff"],
        "evidence": payload["evidence"],
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def append_feedback_entry(
    path: Path,
    *,
    target: str,
    target_type: str,
    leader_comment: str,
    assignment_id: str | None = None,
    fit_tags: tuple[str, ...] = (),
    role_fit: str | None = None,
    model_fit: str | None = None,
    accepted: bool | None = None,
    reuse_when: tuple[str, ...] = (),
    avoid_when: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Append a Leader-authored feedback event to the JSONL journal."""
    normalized_type = target_type.strip().lower().replace("-", "_")
    if normalized_type not in FEEDBACK_TARGET_TYPES:
        allowed = ", ".join(sorted(FEEDBACK_TARGET_TYPES))
        raise ValueError(f"target_type must be one of: {allowed}")

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": FEEDBACK_EVENT,
        "target": target,
        "target_type": normalized_type,
        "assignment_id": assignment_id,
        "leader_comment": leader_comment,
        "fit_tags": list(_clean_tuple(fit_tags)),
        "role_fit": _clean_optional(role_fit),
        "model_fit": _clean_optional(model_fit),
        "accepted": accepted,
        "reuse_when": list(_clean_tuple(reuse_when)),
        "avoid_when": list(_clean_tuple(avoid_when)),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_journal_entries(
    path: Path,
    limit: int = 20,
    worker: str | None = None,
    status: str | None = None,
    assignment_id: str | None = None,
) -> list[dict[str, Any]]:
    """Read filtered journal entries, returning the newest entries first."""
    entries: list[dict[str, Any]] = []
    for entry in _read_jsonl_entries(path):
        if not _matches_entry(entry, worker=worker, status=status, assignment_id=assignment_id):
            continue
        entries.append(entry)

    newest = list(reversed(entries))
    return newest[:max(limit, 1)]


def read_feedback_entries(
    path: Path,
    limit: int = 100,
    *,
    target: str | None = None,
    target_type: str | None = None,
    tag: str | None = None,
    assignment_id: str | None = None,
) -> list[dict[str, Any]]:
    """Read Leader feedback events, returning newest entries first."""
    entries: list[dict[str, Any]] = []
    for entry in _read_jsonl_entries(path):
        if entry.get("event") != FEEDBACK_EVENT:
            continue
        if not _matches_feedback(
            entry,
            target=target,
            target_type=target_type,
            tag=tag,
            assignment_id=assignment_id,
        ):
            continue
        entries.append(entry)

    newest = list(reversed(entries))
    return newest[:max(limit, 1)]


def build_journal_stats(
    path: Path,
    *,
    target: str | None = None,
    target_type: str | None = None,
    worker: str | None = None,
    role: str | None = None,
    model: str | None = None,
    skill: str | None = None,
    tag: str | None = None,
    since: str | datetime | None = None,
    until: str | datetime | None = None,
) -> dict[str, Any]:
    """Aggregate assignment results and Leader feedback for Leader inspection."""
    since_dt = _parse_time_bound(since, "since")
    until_dt = _parse_time_bound(until, "until")
    assignment_entries: list[dict[str, Any]] = []
    feedback_entries: list[dict[str, Any]] = []
    for entry in _read_jsonl_entries(path):
        if not _matches_time_window(entry, since=since_dt, until=until_dt):
            continue
        if entry.get("event") == FEEDBACK_EVENT:
            if _matches_feedback(entry, target=target, target_type=target_type, tag=tag, assignment_id=None):
                feedback_entries.append(entry)
            continue
        if _matches_stats_assignment(
            entry,
            target=target,
            target_type=target_type,
            worker=worker,
            role=role,
            model=model,
            skill=skill,
        ):
            assignment_entries.append(entry)

    return {
        "path": str(path),
        "filters": {
            "target": target,
            "target_type": _normalize_target_type(target_type),
            "worker": worker,
            "role": role,
            "model": model,
            "skill": skill,
            "tag": tag,
            "since": _format_time_bound(since_dt),
            "until": _format_time_bound(until_dt),
        },
        "assignments": _assignment_stats(assignment_entries),
        "feedback": _feedback_stats(feedback_entries),
    }


def _read_jsonl_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def _parse_time_bound(value: str | datetime | None, label: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as e:
            raise ValueError(f"{label} must be an ISO-8601 timestamp") from e
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_time_bound(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _matches_time_window(entry: dict[str, Any], *, since: datetime | None, until: datetime | None) -> bool:
    if since is None and until is None:
        return True
    timestamp = _parse_entry_timestamp(entry)
    if timestamp is None:
        return False
    if since is not None and timestamp < since:
        return False
    if until is not None and timestamp > until:
        return False
    return True


def _parse_entry_timestamp(entry: dict[str, Any]) -> datetime | None:
    raw = entry.get("timestamp")
    if not raw:
        return None
    try:
        return _parse_time_bound(str(raw), "timestamp")
    except ValueError:
        return None


def _matches_entry(
    entry: dict[str, Any],
    worker: str | None,
    status: str | None,
    assignment_id: str | None,
) -> bool:
    assignment = entry.get("assignment") or {}
    if worker and assignment.get("worker") != worker:
        return False
    if status and entry.get("status") != status:
        return False
    entry_assignment_id = assignment.get("assignment_id") or entry.get("assignment_id")
    if assignment_id and entry_assignment_id != assignment_id:
        return False
    return True


def _matches_feedback(
    entry: dict[str, Any],
    *,
    target: str | None,
    target_type: str | None,
    tag: str | None,
    assignment_id: str | None,
) -> bool:
    if target and entry.get("target") != target:
        return False
    normalized_type = _normalize_target_type(target_type)
    if normalized_type and entry.get("target_type") != normalized_type:
        return False
    if assignment_id and entry.get("assignment_id") != assignment_id:
        return False
    if tag and tag not in set(str(item) for item in (entry.get("fit_tags") or ())):
        return False
    return True


def _matches_stats_assignment(
    entry: dict[str, Any],
    *,
    target: str | None,
    target_type: str | None,
    worker: str | None,
    role: str | None,
    model: str | None,
    skill: str | None,
) -> bool:
    assignment = entry.get("assignment") or {}
    if worker and assignment.get("worker") != worker:
        return False
    if role and assignment.get("base_role") != role:
        return False
    if model and model not in {assignment.get("model"), assignment.get("model_profile")}:
        return False
    skills = set(str(item) for item in (assignment.get("skills") or ()))
    if skill and skill not in skills:
        return False
    if target and not _assignment_matches_target(assignment, target, target_type):
        return False
    return True


def _assignment_matches_target(assignment: dict[str, Any], target: str, target_type: str | None) -> bool:
    normalized_type = _normalize_target_type(target_type)
    if normalized_type == "assignment":
        return assignment.get("assignment_id") == target
    if normalized_type == "model":
        return target in {assignment.get("model"), assignment.get("model_profile")}
    if normalized_type == "base_role":
        return assignment.get("base_role") == target
    if normalized_type == "skill":
        return target in set(str(item) for item in (assignment.get("skills") or ()))
    if normalized_type == "role_card":
        return target in str(assignment.get("role_file") or "")
    return target in {
        str(assignment.get("assignment_id") or ""),
        str(assignment.get("worker") or ""),
        str(assignment.get("base_role") or ""),
        str(assignment.get("model") or ""),
        str(assignment.get("model_profile") or ""),
        *set(str(item) for item in (assignment.get("skills") or ())),
    }


def _assignment_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(entry.get("status") or "") for entry in entries if entry.get("status"))
    role_fit = Counter(str(entry.get("role_fit") or "") for entry in entries if entry.get("role_fit"))
    risk_level = Counter(str(entry.get("risk_level") or "") for entry in entries if entry.get("risk_level"))
    workers = Counter(str((entry.get("assignment") or {}).get("worker") or "") for entry in entries)
    roles = Counter(str((entry.get("assignment") or {}).get("base_role") or "") for entry in entries)
    models = Counter(str((entry.get("assignment") or {}).get("model") or "") for entry in entries)
    next_roles: Counter[str] = Counter()
    for entry in entries:
        next_roles.update(str(item) for item in (entry.get("next_recommended_roles") or ()) if item)
    return {
        "count": len(entries),
        "success": sum(1 for entry in entries if entry.get("success") is True),
        "failed": sum(1 for entry in entries if entry.get("success") is False),
        "statuses": _counter_dict(statuses),
        "role_fit": _counter_dict(role_fit),
        "risk_level": _counter_dict(risk_level),
        "workers": _counter_dict(workers),
        "roles": _counter_dict(roles),
        "models": _counter_dict(models),
        "next_recommended_roles": _counter_dict(next_roles),
    }


def _feedback_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    target_types = Counter(str(entry.get("target_type") or "") for entry in entries if entry.get("target_type"))
    targets = Counter(str(entry.get("target") or "") for entry in entries if entry.get("target"))
    role_fit = Counter(str(entry.get("role_fit") or "") for entry in entries if entry.get("role_fit"))
    model_fit = Counter(str(entry.get("model_fit") or "") for entry in entries if entry.get("model_fit"))
    tags: Counter[str] = Counter()
    for entry in entries:
        tags.update(str(item) for item in (entry.get("fit_tags") or ()) if item)
    return {
        "count": len(entries),
        "accepted": sum(1 for entry in entries if entry.get("accepted") is True),
        "rejected": sum(1 for entry in entries if entry.get("accepted") is False),
        "target_types": _counter_dict(target_types),
        "targets": _counter_dict(targets),
        "tags": _counter_dict(tags),
        "role_fit": _counter_dict(role_fit),
        "model_fit": _counter_dict(model_fit),
        "recent_comments": [
            {
                "timestamp": entry.get("timestamp"),
                "target": entry.get("target"),
                "target_type": entry.get("target_type"),
                "leader_comment": entry.get("leader_comment"),
                "assignment_id": entry.get("assignment_id"),
            }
            for entry in list(reversed(entries))[:5]
        ],
    }


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: value for key, value in counter.items() if key}


def _normalize_target_type(target_type: str | None) -> str | None:
    if target_type is None:
        return None
    normalized = target_type.strip().lower().replace("-", "_")
    return normalized or None


def _clean_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(value.strip() for value in values if value and value.strip())


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
