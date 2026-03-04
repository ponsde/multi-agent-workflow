"""System prompt builder for workers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def load_skill(skills_dir: Path, skill_name: str) -> str | None:
    """Load a SKILL.md file content, stripping YAML frontmatter."""
    skill_path = skills_dir / skill_name / "SKILL.md"
    if not skill_path.exists():
        return None

    content = skill_path.read_text(encoding="utf-8")

    # Strip YAML frontmatter (--- ... ---)
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].lstrip("\n")

    return content


def build_system_prompt(
    worker_name: str,
    role: str,
    workspace: str,
    skills_dir: Path,
    skill_names: tuple[str, ...],
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
        "When done, provide a clear summary of what you did.",
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

    return "\n".join(parts)
