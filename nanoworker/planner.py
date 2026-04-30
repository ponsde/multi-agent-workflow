"""Lightweight assignment suggestion helpers for Leader runtimes."""

from __future__ import annotations

import shlex
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nanoworker.config import Config, resolve_model
from nanoworker.tools import resolve_tool_policy


@dataclass(frozen=True)
class AssignmentSuggestion:
    task_shape: str
    worker: str
    role: str
    model: str
    resolved_model: str
    tool_policy: str
    skills: tuple[str, ...]
    role_card_recommended: bool
    rationale: tuple[str, ...]
    command: str


@dataclass(frozen=True)
class RoleCandidate:
    name: str
    base_role: str
    worker: str
    model: str
    resolved_model: str
    tool_policy: str
    skills: tuple[str, ...]
    role_card_recommended: bool
    why: tuple[str, ...]
    risks: tuple[str, ...]
    acceptance_focus: tuple[str, ...]
    command: str
    source: str = "template"
    role_id: str = ""
    tags: tuple[str, ...] = ()
    preferred_models: tuple[str, ...] = ()


TASK_SHAPES: dict[str, dict[str, object]] = {
    "frontend": {
        "role": "coder",
        "tool_policy": "product-write",
        "keywords": ("frontend", "ui", "css", "component", "responsive", "design", "前端", "界面", "样式", "组件"),
        "model_terms": ("frontend", "ui", "design"),
        "role_card": True,
    },
    "backend": {
        "role": "coder",
        "tool_policy": "product-write",
        "keywords": ("backend", "api", "database", "db", "service", "auth", "后端", "接口", "数据库"),
        "model_terms": ("backend", "reasoning", "tests"),
        "role_card": False,
    },
    "debug": {
        "role": "debug",
        "tool_policy": "product-write",
        "keywords": ("bug", "debug", "fix", "error", "traceback", "失败", "报错", "修复"),
        "model_terms": ("reasoning", "review", "code"),
        "role_card": False,
    },
    "fix": {
        "role": "fixer",
        "tool_policy": "product-write",
        "keywords": ("fixer", "fix findings", "apply findings", "address findings", "修复清单", "根据审查", "定点修复"),
        "model_terms": ("code", "reasoning"),
        "role_card": False,
    },
    "review": {
        "role": "reviewer",
        "tool_policy": "read-only-review",
        "keywords": ("review", "reviewer", "audit", "security", "bug hunt", "code style", "style", "审查", "审核", "安全", "找 bug", "代码风格", "风格"),
        "model_terms": ("review", "reasoning", "code"),
        "role_card": False,
    },
    "verify": {
        "role": "tester",
        "tool_policy": "test-write-only",
        "keywords": ("test", "verify", "ci", "lint", "build", "验证", "测试", "构建"),
        "model_terms": ("tests", "reasoning"),
        "role_card": False,
    },
    "write": {
        "role": "coder",
        "tool_policy": "product-write",
        "keywords": (),
        "model_terms": ("code", "reasoning"),
        "role_card": False,
    },
}
TASK_SHAPE_PRIORITY = ("frontend", "fix", "review", "debug", "verify", "backend")
TAG_ALIASES = {
    "前端": "frontend",
    "界面": "ui",
    "组件": "component",
    "样式": "css",
    "后端": "backend",
    "接口": "api",
    "数据库": "database",
    "安全": "security",
    "测试": "test",
    "验证": "verify",
    "构建": "build",
    "修复": "fix",
    "报错": "debug",
    "审查": "review",
}


ROLE_CANDIDATE_LIBRARY: dict[str, tuple[dict[str, object], ...]] = {
    "frontend": (
        {
            "name": "Frontend Implementer",
            "shape": "frontend",
            "why": ("Task looks UI/frontend-oriented.", "A temporary Role Card can carry design-system and responsive constraints."),
            "risks": ("May touch shared styles or component contracts.",),
            "acceptance": ("Render states are covered.", "Responsive layout holds.", "Build or relevant UI checks pass."),
        },
        {
            "name": "Code Reviewer",
            "shape": "review",
            "why": ("Post-implementation review should catch regressions and weak verification.",),
            "risks": ("Read-only review cannot fix issues directly.",),
            "acceptance": ("Findings are concrete and severity-ranked.",),
        },
        {
            "name": "Tester",
            "shape": "verify",
            "why": ("Frontend work benefits from explicit verification evidence.",),
            "risks": ("May need a browser or project-specific test command.",),
            "acceptance": ("Relevant commands or manual evidence are reported.",),
        },
    ),
    "backend": (
        {
            "name": "Backend Implementer",
            "shape": "backend",
            "why": ("Task looks backend/API/data-oriented.",),
            "risks": ("Contracts, migrations, or auth paths may have hidden call sites.",),
            "acceptance": ("API/data contract behavior is covered.", "Relevant tests pass."),
        },
        {
            "name": "Code Reviewer",
            "shape": "review",
            "why": ("Review can catch contract and edge-case regressions.",),
            "risks": ("Read-only review cannot fix issues directly.",),
            "acceptance": ("Findings cite concrete files and behavior.",),
        },
        {
            "name": "Tester",
            "shape": "verify",
            "why": ("Backend changes need command-level verification.",),
            "risks": ("May need services, env, or fixtures.",),
            "acceptance": ("Commands and pass/fail evidence are recorded.",),
        },
    ),
    "debug": (
        {
            "name": "Debugger",
            "shape": "debug",
            "why": ("Task describes a failure that may need diagnosis.",),
            "risks": ("Root cause may require reproduction context.",),
            "acceptance": ("Failure cause is explained.", "Fix or next concrete blocker is reported."),
        },
        {
            "name": "Fixer",
            "shape": "fix",
            "why": ("Use after Debug or Reviewer produces concrete findings.",),
            "risks": ("Should not broaden into redesign.",),
            "acceptance": ("Assigned finding is fixed with targeted verification.",),
        },
    ),
    "fix": (
        {
            "name": "Fixer",
            "shape": "fix",
            "why": ("Task appears to contain known findings or a handoff to apply.",),
            "risks": ("Finding may be under-specified or stale.",),
            "acceptance": ("Each assigned finding is fixed or rejected with evidence.",),
        },
        {
            "name": "Tester",
            "shape": "verify",
            "why": ("Applied fixes need follow-up verification.",),
            "risks": ("Verification may require the original failing command.",),
            "acceptance": ("Regression or targeted check is reported.",),
        },
    ),
    "review": (
        {
            "name": "Code Reviewer",
            "shape": "review",
            "why": ("Task asks for review/audit or bug hunting.",),
            "risks": ("Review scope can be too broad without named files or diff.",),
            "acceptance": ("Findings are actionable, severity-ranked, and low-noise.",),
        },
        {
            "name": "Fixer",
            "shape": "fix",
            "why": ("Use after Leader accepts review findings.",),
            "risks": ("Should only address accepted findings.",),
            "acceptance": ("Accepted findings are fixed and verified.",),
        },
    ),
    "verify": (
        {
            "name": "Tester",
            "shape": "verify",
            "why": ("Task asks for tests, build, lint, CI, or verification.",),
            "risks": ("Environment may be missing dependencies or services.",),
            "acceptance": ("Exact commands and outcomes are recorded.",),
        },
        {
            "name": "Fixer",
            "shape": "fix",
            "why": ("Use only if verification produces concrete accepted failures.",),
            "risks": ("Tester should not fix product code directly.",),
            "acceptance": ("Accepted failure is fixed and rechecked.",),
        },
    ),
    "write": (
        {
            "name": "Coder",
            "shape": "write",
            "why": ("Default implementation path for a scoped task.",),
            "risks": ("Task may need a more specific temporary Role Card.",),
            "acceptance": ("Task Packet acceptance criteria are met.",),
        },
        {
            "name": "Code Reviewer",
            "shape": "review",
            "why": ("A read-only review can be used as a quality gate.",),
            "risks": ("Review needs clear scope or diff context.",),
            "acceptance": ("Findings are concrete and routeable.",),
        },
    ),
}


def suggest_assignment(config: Config, task: str, workspace: str | None = None) -> AssignmentSuggestion:
    """Suggest a worker/model/tool-policy tuple for a task description."""
    task_shape = infer_task_shape(task)
    shape = TASK_SHAPES[task_shape]
    role = str(shape["role"])
    tool_policy = str(shape["tool_policy"])

    worker_name = _select_worker(config, role=role)
    worker = config.workers.get(worker_name)
    if worker is None:
        raise ValueError("no workers configured")

    model_profile = _select_model_profile(
        config,
        role=role,
        model_terms=tuple(shape["model_terms"]),
        fallback_model=worker.model,
    )
    resolved = resolve_model(config, model_profile)

    rationale = (
        f"task_shape={task_shape}",
        f"role={role}",
        f"tool_policy={tool_policy}",
        f"model={model_profile}",
    )
    command = _command_hint(
        worker=worker_name,
        workspace=workspace,
        model=model_profile,
        tool_policy=tool_policy,
    )
    return AssignmentSuggestion(
        task_shape=task_shape,
        worker=worker_name,
        role=role,
        model=model_profile,
        resolved_model=resolved.model,
        tool_policy=tool_policy,
        skills=worker.skills,
        role_card_recommended=bool(shape["role_card"]),
        rationale=rationale,
        command=command,
    )


def suggest_role_candidates(
    config: Config,
    task: str,
    workspace: str | None = None,
    role_infos: tuple[Any, ...] | list[Any] = (),
) -> tuple[RoleCandidate, ...]:
    """Return role-card candidate data for Leader to judge."""
    task_shape = infer_task_shape(task)
    specs = ROLE_CANDIDATE_LIBRARY.get(task_shape, ROLE_CANDIDATE_LIBRARY["write"])
    candidates: list[RoleCandidate] = []
    for spec in specs:
        shape_name = str(spec["shape"])
        shape = TASK_SHAPES[shape_name]
        role = str(shape["role"])
        tool_policy = str(shape["tool_policy"])
        worker_name = _select_worker(config, role=role)
        worker = config.workers.get(worker_name)
        if worker is None:
            continue
        model_profile = _select_model_profile(
            config,
            role=role,
            model_terms=tuple(shape["model_terms"]),
            fallback_model=worker.model,
        )
        resolved = resolve_model(config, model_profile)
        command = _command_hint(
            worker=worker_name,
            workspace=workspace,
            model=model_profile,
            tool_policy=tool_policy,
        )
        candidates.append(
            RoleCandidate(
                name=str(spec["name"]),
                base_role=role,
                worker=worker_name,
                model=model_profile,
                resolved_model=resolved.model,
                tool_policy=tool_policy,
                skills=worker.skills,
                role_card_recommended=bool(shape["role_card"]) or shape_name != worker.role,
                why=_tuple_value(spec["why"]),
                risks=_tuple_value(spec["risks"]),
                acceptance_focus=_tuple_value(spec["acceptance"]),
                command=command,
            )
        )
    candidates.extend(_registered_role_candidates(config, task=task, workspace=workspace, role_infos=role_infos))
    return tuple(candidates)


def infer_task_shape(task: str) -> str:
    text = task.lower()
    for shape in TASK_SHAPE_PRIORITY:
        spec = TASK_SHAPES[shape]
        if any(_keyword_matches(text, keyword) for keyword in spec["keywords"]):
            return shape
    return "write"


def _keyword_matches(text: str, keyword: str) -> bool:
    if keyword.isascii():
        escaped = re.escape(keyword.lower())
        return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None
    return keyword in text


def _tuple_value(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple | list):
        return tuple(str(item) for item in value)
    return (str(value),)


def suggestion_to_dict(suggestion: AssignmentSuggestion) -> dict[str, object]:
    return {
        "task_shape": suggestion.task_shape,
        "worker": suggestion.worker,
        "role": suggestion.role,
        "model": suggestion.model,
        "resolved_model": suggestion.resolved_model,
        "tool_policy": suggestion.tool_policy,
        "skills": list(suggestion.skills),
        "role_card_recommended": suggestion.role_card_recommended,
        "rationale": list(suggestion.rationale),
        "command": suggestion.command,
    }


def role_candidate_to_dict(
    candidate: RoleCandidate,
    *,
    task: str = "",
    feedback_entries: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": candidate.name,
        "base_role": candidate.base_role,
        "worker": candidate.worker,
        "model": candidate.model,
        "resolved_model": candidate.resolved_model,
        "tool_policy": candidate.tool_policy,
        "skills": list(candidate.skills),
        "role_card_recommended": candidate.role_card_recommended,
        "why": list(candidate.why),
        "risks": list(candidate.risks),
        "acceptance_focus": list(candidate.acceptance_focus),
        "command": candidate.command,
        "source": candidate.source,
    }
    if candidate.role_id:
        payload["role_id"] = candidate.role_id
    if candidate.tags:
        payload["tags"] = list(candidate.tags)
    if candidate.preferred_models:
        payload["preferred_models"] = list(candidate.preferred_models)
    feedback = candidate_feedback(candidate, task=task, feedback_entries=feedback_entries)
    if feedback:
        payload["feedback"] = list(feedback)
        payload["feedback_summary"] = candidate_feedback_summary(candidate, task=task, feedback_entries=feedback_entries)
    return payload


def candidate_feedback(
    candidate: RoleCandidate,
    *,
    task: str,
    feedback_entries: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    limit: int = 3,
) -> tuple[dict[str, object], ...]:
    """Return Leader feedback entries that look relevant to a candidate."""
    terms = _candidate_feedback_terms(candidate, task)
    matches: list[tuple[int, str, dict[str, Any]]] = []
    for entry in feedback_entries:
        if entry.get("event") != "leader_feedback":
            continue
        score = _feedback_match_score(entry, candidate, terms)
        if score <= 0:
            continue
        matches.append((score, str(entry.get("timestamp", "")), entry))

    matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return tuple(_feedback_note(entry) for _, _, entry in matches[:max(limit, 1)])


def candidate_feedback_summary(
    candidate: RoleCandidate,
    *,
    task: str,
    feedback_entries: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    limit: int = 10,
) -> dict[str, object]:
    """Return a compact Leader-readable summary for matching feedback."""
    notes = candidate_feedback(candidate, task=task, feedback_entries=feedback_entries, limit=limit)
    if not notes:
        return {}

    tag_counts: Counter[str] = Counter()
    role_fit_counts: Counter[str] = Counter()
    model_fit_counts: Counter[str] = Counter()
    comments: list[str] = []
    accepted = 0
    rejected = 0
    for note in notes:
        if note.get("accepted") is True:
            accepted += 1
        elif note.get("accepted") is False:
            rejected += 1
        for tag in note.get("fit_tags") or ():
            tag_text = str(tag).strip()
            if tag_text:
                tag_counts[tag_text] += 1
        role_fit = str(note.get("role_fit") or "").strip()
        if role_fit:
            role_fit_counts[role_fit] += 1
        model_fit = str(note.get("model_fit") or "").strip()
        if model_fit:
            model_fit_counts[model_fit] += 1
        comment = str(note.get("leader_comment") or "").strip()
        if comment and comment not in comments:
            comments.append(comment)

    return {
        "count": len(notes),
        "accepted": accepted,
        "rejected": rejected,
        "top_tags": [
            {"tag": tag, "count": count}
            for tag, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        ],
        "role_fit": dict(sorted(role_fit_counts.items())),
        "model_fit": dict(sorted(model_fit_counts.items())),
        "recent_comments": comments[:3],
    }


def _registered_role_candidates(
    config: Config,
    *,
    task: str,
    workspace: str | None,
    role_infos: tuple[Any, ...] | list[Any],
) -> list[RoleCandidate]:
    task_terms = _task_terms(task)
    task_shape = infer_task_shape(task)
    candidates: list[RoleCandidate] = []
    for role_info in role_infos:
        role_id = str(getattr(role_info, "name", "") or "").strip()
        if not role_id:
            continue
        tags = _tuple_value(getattr(role_info, "tags", ()))
        description = str(getattr(role_info, "description", "") or "")
        display_name = str(getattr(role_info, "frontmatter_name", "") or role_id)
        metadata_terms = _terms_from_text(f"{role_id} {display_name} {description} {' '.join(tags)}")
        overlap = task_terms.intersection(metadata_terms)
        if not overlap:
            continue

        base_role = str(getattr(role_info, "base_role", "") or "").strip()
        if not base_role:
            base_role = str(TASK_SHAPES[task_shape]["role"])
        shape_name = _shape_for_base_role(base_role, task_shape)
        shape = TASK_SHAPES[shape_name]
        worker_name = _select_worker(config, role=base_role)
        worker = config.workers.get(worker_name)
        if worker is None:
            continue
        preferred_models = _tuple_value(getattr(role_info, "preferred_models", ()))
        model_profile = preferred_models[0] if preferred_models else _select_model_profile(
            config,
            role=base_role,
            model_terms=tuple(shape["model_terms"]),
            fallback_model=worker.model,
        )
        resolved = resolve_model(config, model_profile)
        command = _append_skill_to_command(
            _command_hint(
                worker=worker_name,
                workspace=workspace,
                model=model_profile,
                tool_policy=str(shape["tool_policy"]),
            ),
            role_id,
        )
        candidates.append(
            RoleCandidate(
                name=display_name,
                base_role=base_role,
                worker=worker_name,
                model=model_profile,
                resolved_model=resolved.model,
                tool_policy=str(shape["tool_policy"]),
                skills=_merge_unique((*worker.skills, role_id)),
                role_card_recommended=False,
                why=(f"Registered role metadata matched task terms: {', '.join(sorted(overlap))}.",),
                risks=("Persistent role guidance may still need a Task Packet with concrete scope.",),
                acceptance_focus=("Use the role metadata as candidate context; Leader still decides fit.",),
                command=command,
                source="registered_role",
                role_id=role_id,
                tags=tags,
                preferred_models=preferred_models,
            )
        )
    candidates.sort(key=lambda candidate: (-len(set(candidate.tags).intersection(task_terms)), candidate.role_id))
    return candidates


def _feedback_match_score(entry: dict[str, Any], candidate: RoleCandidate, terms: set[str]) -> int:
    target_type = str(entry.get("target_type", "")).strip().lower().replace("-", "_")
    target = str(entry.get("target", "")).strip()
    target_terms = _terms_from_text(target)
    score = 0

    if target_type == "model" and _normalized_value(target) in {
        _normalized_value(candidate.model),
        _normalized_value(candidate.resolved_model),
    }:
        score += 6
    elif target_type == "skill" and _normalized_value(target) in {
        _normalized_value(skill) for skill in candidate.skills
    }:
        score += 6
    elif target_type == "base_role" and _normalized_value(target) == _normalized_value(candidate.base_role):
        score += 6
    elif target_type == "role_card" and target_terms.intersection(terms):
        score += 4
    elif target_type == "assignment" and target_terms.intersection(terms):
        score += 2

    tags = _feedback_tags(entry)
    score += 2 * len(tags.intersection(terms))
    return score


def _candidate_feedback_terms(candidate: RoleCandidate, task: str) -> set[str]:
    terms: set[str] = set()
    for value in (
        candidate.name,
        candidate.base_role,
        candidate.worker,
        candidate.model,
        candidate.resolved_model,
        infer_task_shape(task),
        task,
        candidate.role_id,
        *candidate.tags,
        *candidate.preferred_models,
        *candidate.skills,
    ):
        terms.update(_terms_from_text(value))

    lowered = task.lower()
    for source, alias in TAG_ALIASES.items():
        if source in lowered:
            terms.add(alias)
    return terms


def _feedback_tags(entry: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    raw_tags = entry.get("fit_tags") or ()
    if isinstance(raw_tags, str):
        raw_tags = (raw_tags,)
    if isinstance(raw_tags, list | tuple):
        for tag in raw_tags:
            tags.update(_terms_from_text(str(tag)))
    return tags


def _feedback_note(entry: dict[str, Any]) -> dict[str, object]:
    return {
        "target": str(entry.get("target", "")),
        "target_type": str(entry.get("target_type", "")),
        "leader_comment": str(entry.get("leader_comment", "")),
        "fit_tags": list(entry.get("fit_tags") or ()),
        "role_fit": entry.get("role_fit"),
        "model_fit": entry.get("model_fit"),
        "accepted": entry.get("accepted"),
        "reuse_when": list(entry.get("reuse_when") or ()),
        "avoid_when": list(entry.get("avoid_when") or ()),
        "assignment_id": entry.get("assignment_id"),
    }


def _terms_from_text(value: str) -> set[str]:
    terms = {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 1}
    return {_normalize_term(term) for term in terms}


def _normalized_value(value: str) -> str:
    return "-".join(sorted(_terms_from_text(value))) or value.strip().lower()


def _normalize_term(term: str) -> str:
    return {
        "db": "database",
        "tests": "test",
        "testing": "test",
        "reviewer": "review",
        "reviewing": "review",
    }.get(term, term)


def _task_terms(task: str) -> set[str]:
    terms = _terms_from_text(task)
    terms.add(infer_task_shape(task))
    lowered = task.lower()
    for source, alias in TAG_ALIASES.items():
        if source in lowered:
            terms.add(alias)
    return terms


def _shape_for_base_role(base_role: str, task_shape: str) -> str:
    if str(TASK_SHAPES[task_shape]["role"]) == base_role:
        return task_shape
    for shape, spec in TASK_SHAPES.items():
        if str(spec["role"]) == base_role:
            return shape
    return task_shape


def _merge_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            merged.append(value)
            seen.add(value)
    return tuple(merged)


def _append_skill_to_command(command: str, skill: str) -> str:
    return f"{command} --skill {shlex.quote(skill)}"


def _select_worker(config: Config, role: str) -> str:
    preferred_names = {
        "coder": ("write", "coder"),
        "debug": ("debug",),
        "fixer": ("fix", "fixer"),
        "tester": ("verify", "tester"),
        "reviewer": ("review", "reviewer"),
        "debug-duel": ("review", "duel"),
    }.get(role, ())
    for name in preferred_names:
        if name in config.workers and config.workers[name].role == role:
            return name
    for name, worker in config.workers.items():
        if worker.role == role:
            return name
    if config.workers:
        return next(iter(config.workers))
    raise ValueError("no workers configured")


def _select_model_profile(
    config: Config,
    role: str,
    model_terms: tuple[str, ...],
    fallback_model: str,
) -> str:
    best_name = fallback_model
    best_score = -1
    for name, profile in config.models.items():
        score = 0
        if role in profile.preferred_roles:
            score += 5
        profile_terms = set(profile.strengths) | set(profile.preferred_roles)
        score += sum(3 for term in model_terms if term in profile_terms)
        if score > best_score:
            best_name = name
            best_score = score
    return best_name


def _command_hint(worker: str, workspace: str | None, model: str, tool_policy: str) -> str:
    workspace_part = workspace or "<workspace>"
    return " ".join(
        [
            "nanoworker",
            shlex.quote(worker),
            "--workspace",
            shlex.quote(str(Path(workspace_part)) if workspace else workspace_part),
            "--message-file",
            "<task-packet.md>",
            "--model",
            shlex.quote(model),
            "--tool-policy",
            shlex.quote(resolve_tool_policy("", tool_policy)),
        ]
    )
