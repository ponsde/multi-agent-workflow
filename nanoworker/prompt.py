"""System prompt builder for workers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

SkillDirs = Path | Iterable[Path]


def load_skill(skills_dir: SkillDirs, skill_name: str) -> str | None:
    """Load a SKILL.md file content, stripping YAML frontmatter."""
    skill_path = _resolve_skill_path(skills_dir, skill_name)
    if skill_path is None:
        return None

    content = skill_path.read_text(encoding="utf-8")

    return _strip_frontmatter(content)


def skill_exists(skills_dir: SkillDirs, skill_name: str) -> bool:
    """Return whether a skill can be resolved by folder or frontmatter name."""
    return _resolve_skill_path(skills_dir, skill_name) is not None


def _resolve_skill_path(skills_dir: SkillDirs, skill_name: str) -> Path | None:
    for directory in _as_skill_dirs(skills_dir):
        index_file = directory / "index.json"
        if not index_file.exists():
            continue
        from nanoworker.roles import resolve_registered_role_path

        registered = resolve_registered_role_path(directory, index_file, skill_name)
        if registered is not None:
            return registered
    return None


def _as_skill_dirs(skills_dir: SkillDirs) -> tuple[Path, ...]:
    if isinstance(skills_dir, Path):
        return (skills_dir,)
    return tuple(Path(directory) for directory in skills_dir)


def _strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].lstrip("\n")
    return content


def _frontmatter_name(path: Path) -> str | None:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end == -1:
        return None
    for line in content[3:end].splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return None


def build_system_prompt(
    worker_name: str,
    role: str,
    workspace: str,
    skills_dir: SkillDirs,
    skill_names: tuple[str, ...],
    extra_sections: tuple[str, ...] = (),
) -> str:
    """Build the system prompt for a worker."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    parts = [
        f"# Worker: {worker_name}",
        f"- Role: {role}",
        f"- Time: {now}",
        f"- Workspace: {workspace}",
        "",
        "You are a worker agent. Execute the task given to you using your tools.",
        "Work directly in the workspace directory. Read and write files as needed.",
        "Prefer paths relative to the workspace.",
        "When done, include a status line: Status: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, BLOCKED, or FAILED.",
        "",
    ]

    # Load and inject skills
    for skill_name in skill_names:
        skill_content = load_skill(skills_dir, skill_name)
        if skill_content:
            parts.append("---")
            parts.append("")
            parts.append(skill_content)
            parts.append("")

    for section in extra_sections:
        if section.strip():
            parts.append("---")
            parts.append("")
            parts.append(section.strip())
            parts.append("")

    return "\n".join(parts)
