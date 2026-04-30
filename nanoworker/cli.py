"""CLI entry point for nanoworker."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from typer.core import TyperGroup


class WorkerDefaultGroup(TyperGroup):
    """Route unknown commands to `run` so `nanoworker write ...` stays valid."""

    def resolve_command(self, ctx, args):
        try:
            return super().resolve_command(ctx, args)
        except Exception:
            if args:
                args.insert(0, "run")
                return super().resolve_command(ctx, args)
            raise


app = typer.Typer(
    name="nanoworker",
    cls=WorkerDefaultGroup,
    help="Lightweight worker agent for multi-agent orchestration.",
)
role_app = typer.Typer(help="Create temporary Role Cards or persistent skills.")
app.add_typer(role_app, name="role")


# Bundled role templates. Runtime roles are installed into ~/.nanoworker/roles.
SKILLS_DIR = Path(__file__).parent.parent / "skills"


def _run_async(coro):
    """Run an async function synchronously."""
    return asyncio.run(coro)


@role_app.command("create")
def role_create_command(
    name: str = typer.Argument(help="Display name for the temporary Role Card."),
    task: Optional[str] = typer.Argument(None, help="Optional task summary used to infer sensible defaults."),
    task_file: Optional[Path] = typer.Option(
        None,
        "--task-file",
        "--message-file",
        help="Read task context from a Task Packet or message file.",
    ),
    base_role: Optional[str] = typer.Option(
        None,
        "--base-role",
        help="Override inferred base role: coder, debug, fixer, tester, reviewer, or debug-duel.",
    ),
    preferred_model: Optional[str] = typer.Option(
        None,
        "--preferred-model",
        "--model",
        help="Model profile/id or routing guidance for this temporary role.",
    ),
    mission: Optional[str] = typer.Option(None, "--mission", help="Override the Role Card mission."),
    owns: Optional[list[str]] = typer.Option(None, "--own", help="Scope owned by this role. Repeatable."),
    avoids: Optional[list[str]] = typer.Option(None, "--avoid", help="Out-of-scope work for this role. Repeatable."),
    methods: Optional[list[str]] = typer.Option(None, "--method", help="Workflow or quality rule. Repeatable."),
    acceptance: Optional[list[str]] = typer.Option(
        None,
        "--acceptance",
        help="Acceptance focus item. Repeatable.",
    ),
    skills: Optional[list[str]] = typer.Option(
        None,
        "--skill",
        help="Persistent skill Leader should also pass for this assignment. Repeatable.",
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write Role Card markdown to this file."),
    force: bool = typer.Option(False, "--force", help="Overwrite --output if it exists."),
    json_output: bool = typer.Option(False, "--json", help="Output metadata as JSON."),
) -> None:
    """Create a temporary Role Card for one assignment."""
    from nanoworker.roles import RoleSpec, build_role_card, resolve_role_spec

    task_text = _resolve_optional_text(task, task_file)
    spec = RoleSpec(
        name=name,
        task=task_text,
        base_role=base_role,
        preferred_model=preferred_model,
        mission=mission,
        owns=tuple(owns or ()),
        avoids=tuple(avoids or ()),
        methods=tuple(methods or ()),
        acceptance=tuple(acceptance or ()),
        skills=tuple(skills or ()),
    )
    resolved = resolve_role_spec(spec)
    content = build_role_card(spec)

    if output is not None:
        _write_text_file(output, content, force=force)

    command = _role_dispatch_hint(
        base_role=resolved.base_role,
        role_file=output,
        task_file=task_file,
        model=preferred_model,
        skills=resolved.skills,
    )
    payload = {
        "kind": "role_card",
        "name": resolved.name,
        "task_shape": resolved.task_shape,
        "base_role": resolved.base_role,
        "preferred_model": resolved.preferred_model,
        "skills": list(resolved.skills),
        "path": str(output) if output is not None else None,
        "command": command,
        "content": content,
    }

    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if output is None:
        typer.echo(content, nl=False)
        typer.echo()
        typer.echo(f"Command hint: {command}")
    else:
        typer.echo(f"Wrote Role Card to {output}")
        typer.echo(f"Command hint: {command}")


@role_app.command("skill")
def role_skill_command(
    name: str = typer.Argument(help="Display name for the persistent skill."),
    task: Optional[str] = typer.Argument(None, help="Optional task summary used to infer sensible defaults."),
    task_file: Optional[Path] = typer.Option(
        None,
        "--task-file",
        "--message-file",
        help="Read task context from a Task Packet or message file.",
    ),
    description: Optional[str] = typer.Option(None, "--description", help="Skill frontmatter description."),
    slug: Optional[str] = typer.Option(None, "--slug", help="Skill directory/name. Defaults to a slug of NAME."),
    base_role: Optional[str] = typer.Option(None, "--base-role", help="Override inferred base role."),
    preferred_model: Optional[str] = typer.Option(
        None,
        "--preferred-model",
        "--model",
        help="Model profile/id or routing guidance for this persistent skill.",
    ),
    tags: Optional[list[str]] = typer.Option(None, "--tag", help="Routing/search tag for this role. Repeatable."),
    mission: Optional[str] = typer.Option(None, "--mission", help="Override the skill role statement."),
    owns: Optional[list[str]] = typer.Option(None, "--own", help="Scope owned by this skill. Repeatable."),
    avoids: Optional[list[str]] = typer.Option(None, "--avoid", help="Out-of-scope work for this skill. Repeatable."),
    methods: Optional[list[str]] = typer.Option(None, "--method", help="Workflow or quality rule. Repeatable."),
    acceptance: Optional[list[str]] = typer.Option(
        None,
        "--acceptance",
        help="Quality bar item. Repeatable.",
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write to a specific SKILL.md path."),
    skills_dir: Optional[Path] = typer.Option(
        None,
        "--skills-dir",
        help="Managed role store directory. Defaults to ~/.nanoworker/roles.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing SKILL.md."),
    json_output: bool = typer.Option(False, "--json", help="Output metadata as JSON."),
) -> None:
    """Create a reusable persistent SKILL.md from a role spec."""
    from nanoworker.config import load_local_env_file
    from nanoworker.roles import RoleSpec, build_skill_doc, resolve_role_spec, slugify_role_name

    load_local_env_file()
    task_text = _resolve_optional_text(task, task_file)
    skill_name = slug or slugify_role_name(name)
    spec = RoleSpec(
        name=name,
        task=task_text,
        base_role=base_role,
        preferred_model=preferred_model,
        tags=tuple(tags or ()),
        mission=mission,
        owns=tuple(owns or ()),
        avoids=tuple(avoids or ()),
        methods=tuple(methods or ()),
        acceptance=tuple(acceptance or ()),
    )
    resolved = resolve_role_spec(spec)
    content = build_skill_doc(spec, skill_name=skill_name, description=description)
    store_dir, index_file = _resolve_role_store(skills_dir)
    target = output or (store_dir / skill_name / "SKILL.md")
    _write_text_file(target, content, force=force)
    if _is_relative_to(target.resolve(), store_dir.resolve()):
        from nanoworker.roles import register_role_path

        register_role_path(store_dir, index_file, target)

    payload = {
        "kind": "skill",
        "name": skill_name,
        "display_name": resolved.name,
        "task_shape": resolved.task_shape,
        "base_role": resolved.base_role,
        "preferred_model": resolved.preferred_model,
        "tags": list(resolved.tags),
        "preferred_models": [preferred_model] if preferred_model else [],
        "path": str(target),
        "registered": _is_relative_to(target.resolve(), store_dir.resolve()),
        "use": f"--skill {shlex.quote(skill_name)}",
    }

    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo(f"Wrote skill to {target}")
    typer.echo(f"Use: --skill {skill_name}")


@role_app.command("list")
def role_list_command(
    skills_dir: Optional[Path] = typer.Option(
        None,
        "--skills-dir",
        help="Managed role store directory. Defaults to ~/.nanoworker/roles.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """List available persistent role skills."""
    from nanoworker.config import load_local_env_file
    from nanoworker.roles import list_registered_roles

    load_local_env_file()
    resolved_dir, index_file = _resolve_role_store(skills_dir)
    skills = list_registered_roles(resolved_dir, index_file)
    payload = [
        {
            "name": skill.name,
            "folder": skill.path.parent.name,
            "description": skill.description,
            "path": str(skill.path),
            "source": skill.source,
            "modified": skill.modified,
            "tags": list(skill.tags),
            "base_role": skill.base_role,
            "preferred_models": list(skill.preferred_models),
        }
        for skill in skills
    ]
    if json_output:
        print(json.dumps({"role_store": str(resolved_dir), "roles": payload}, ensure_ascii=False, indent=2))
        return

    if not skills:
        typer.echo(f"No skills found at {resolved_dir}")
        return
    for item in payload:
        desc = f" - {item['description']}" if item["description"] else ""
        modified = " [modified]" if item["modified"] else ""
        typer.echo(f"{item['name']} ({item['folder']}): {item['path']}{modified}{desc}")


@role_app.command("install-defaults", hidden=True)
def role_install_defaults_command(
    skills_dir: Optional[Path] = typer.Option(
        None,
        "--skills-dir",
        help="Managed role store directory. Defaults to ~/.nanoworker/roles.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing managed role files from bundled templates."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Install bundled default roles into the managed role store."""
    from nanoworker.config import load_local_env_file
    from nanoworker.roles import ensure_role_store

    load_local_env_file()
    store_dir, index_file = _role_store_paths(skills_dir)
    roles = ensure_role_store(SKILLS_DIR, store_dir, index_file, force=force)
    payload = {
        "store_dir": str(store_dir),
        "index_file": str(index_file),
        "roles": [{"name": role.name, "path": str(role.path)} for role in roles],
    }
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"Installed/registered roles in {store_dir}")


@role_app.command("import")
def role_import_command(
    source: Path = typer.Argument(help="Path to a SKILL.md file to copy into the managed role store."),
    role_id: Optional[str] = typer.Option(None, "--id", help="Role id to register. Defaults to frontmatter/folder."),
    base_role: Optional[str] = typer.Option(None, "--base-role", help="Routing base role metadata."),
    preferred_models: Optional[list[str]] = typer.Option(
        None,
        "--preferred-model",
        help="Preferred model profile/id metadata. Repeatable.",
    ),
    tags: Optional[list[str]] = typer.Option(None, "--tag", help="Routing/search tag metadata. Repeatable."),
    skills_dir: Optional[Path] = typer.Option(
        None,
        "--skills-dir",
        help="Managed role store directory. Defaults to ~/.nanoworker/roles.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing role id."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Explicitly import one role file into the managed role store."""
    from nanoworker.config import load_local_env_file
    from nanoworker.roles import import_role_file

    load_local_env_file()
    store_dir, index_file = _resolve_role_store(skills_dir)
    try:
        skill = import_role_file(
            source,
            store_dir,
            index_file,
            role_id=role_id,
            force=force,
            tags=tags,
            base_role=base_role,
            preferred_models=preferred_models,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    payload = _skill_payload(skill)
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"Imported role {skill.name} to {skill.path}")


@role_app.command("import-dir")
def role_import_dir_command(
    source_dir: Path = typer.Argument(help="Directory containing role folders with SKILL.md files."),
    base_role: Optional[str] = typer.Option(None, "--base-role", help="Routing base role metadata for imported roles."),
    preferred_models: Optional[list[str]] = typer.Option(
        None,
        "--preferred-model",
        help="Preferred model profile/id metadata for imported roles. Repeatable.",
    ),
    tags: Optional[list[str]] = typer.Option(None, "--tag", help="Routing/search tag metadata for imported roles. Repeatable."),
    skills_dir: Optional[Path] = typer.Option(
        None,
        "--skills-dir",
        help="Managed role store directory. Defaults to ~/.nanoworker/roles.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing role ids."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Explicitly import every */SKILL.md from a directory."""
    from nanoworker.config import load_local_env_file
    from nanoworker.roles import import_role_dir

    load_local_env_file()
    store_dir, index_file = _resolve_role_store(skills_dir)
    try:
        skills = import_role_dir(
            source_dir,
            store_dir,
            index_file,
            force=force,
            tags=tags,
            base_role=base_role,
            preferred_models=preferred_models,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    payload = [_skill_payload(skill) for skill in skills]
    if json_output:
        print(json.dumps({"roles": payload}, ensure_ascii=False, indent=2))
        return
    typer.echo(f"Imported {len(skills)} role(s) into {store_dir}")


@role_app.command("register")
def role_register_command(
    role_id: str = typer.Argument(help="Role id to register."),
    path: Path = typer.Option(..., "--path", help="Managed store path to a SKILL.md file."),
    base_role: Optional[str] = typer.Option(None, "--base-role", help="Routing base role metadata."),
    preferred_models: Optional[list[str]] = typer.Option(
        None,
        "--preferred-model",
        help="Preferred model profile/id metadata. Repeatable.",
    ),
    tags: Optional[list[str]] = typer.Option(None, "--tag", help="Routing/search tag metadata. Repeatable."),
    skills_dir: Optional[Path] = typer.Option(
        None,
        "--skills-dir",
        help="Managed role store directory. Defaults to ~/.nanoworker/roles.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Register or refresh one existing managed role path."""
    from nanoworker.config import load_local_env_file
    from nanoworker.roles import upsert_role_path

    load_local_env_file()
    store_dir, index_file = _resolve_role_store(skills_dir)
    try:
        skill = upsert_role_path(
            store_dir,
            index_file,
            path,
            role_id=role_id,
            source="registered",
            tags=tags,
            base_role=base_role,
            preferred_models=preferred_models,
        )
    except (FileNotFoundError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    payload = _skill_payload(skill)
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"Registered role {skill.name}: {skill.path}")


@role_app.command("remove")
def role_remove_command(
    name: str = typer.Argument(help="Registered role id, folder, or frontmatter name."),
    skills_dir: Optional[Path] = typer.Option(None, "--skills-dir", help="Override managed role store directory."),
    delete_file: bool = typer.Option(False, "--delete-file", help="Also delete the managed SKILL.md file."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Remove one role from the managed registry."""
    from nanoworker.config import load_local_env_file
    from nanoworker.roles import remove_registered_role

    load_local_env_file()
    store_dir, index_file = _resolve_role_store(skills_dir)
    try:
        skill = remove_registered_role(store_dir, index_file, name, delete_file=delete_file)
    except FileNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    payload = {"name": skill.name, "path": str(skill.path), "deleted_file": delete_file}
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"Removed role {skill.name} from registry")


@role_app.command("doctor")
def role_doctor_command(
    skills_dir: Optional[Path] = typer.Option(None, "--skills-dir", help="Override managed role store directory."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Check the managed role store and registry."""
    from nanoworker.config import load_local_env_file
    from nanoworker.roles import role_store_checks

    load_local_env_file()
    store_dir, index_file = _role_store_paths(skills_dir)
    checks = role_store_checks(store_dir, index_file)
    payload = [{"name": check.name, "ok": check.ok, "detail": check.detail} for check in checks]
    if json_output:
        print(json.dumps({"ok": all(check.ok for check in checks), "checks": payload}, ensure_ascii=False, indent=2))
        if not all(check.ok for check in checks):
            raise typer.Exit(code=1)
        return

    for check in checks:
        mark = "OK" if check.ok else "FAIL"
        typer.echo(f"[{mark}] {check.name}: {check.detail}")
    if not all(check.ok for check in checks):
        raise typer.Exit(code=1)


@role_app.command("show")
def role_show_command(
    name: str = typer.Argument(help="Skill folder name or frontmatter name."),
    skills_dir: Optional[Path] = typer.Option(None, "--skills-dir", help="Override managed role store directory."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Show a persistent role skill."""
    from nanoworker.config import load_local_env_file

    load_local_env_file()
    store_dir, index_file = _resolve_role_store(skills_dir)
    path = _resolve_required_skill_path(store_dir, index_file, name)
    content = path.read_text(encoding="utf-8")
    if json_output:
        print(json.dumps({"name": name, "path": str(path), "content": content}, ensure_ascii=False, indent=2))
        return
    typer.echo(content, nl=False)


@role_app.command("path")
def role_path_command(
    name: str = typer.Argument(help="Skill folder name or frontmatter name."),
    skills_dir: Optional[Path] = typer.Option(None, "--skills-dir", help="Override managed role store directory."),
) -> None:
    """Print the file path for a persistent role skill."""
    from nanoworker.config import load_local_env_file

    load_local_env_file()
    store_dir, index_file = _resolve_role_store(skills_dir)
    path = _resolve_required_skill_path(store_dir, index_file, name)
    typer.echo(str(path))


@role_app.command("edit")
def role_edit_command(
    name: str = typer.Argument(help="Skill folder name or frontmatter name."),
    skills_dir: Optional[Path] = typer.Option(None, "--skills-dir", help="Override managed role store directory."),
    editor: Optional[str] = typer.Option(None, "--editor", help="Editor command. Defaults to $EDITOR or vi."),
) -> None:
    """Open a persistent role skill in an editor for Leader-driven prompt adjustment."""
    import subprocess

    from nanoworker.config import load_local_env_file

    load_local_env_file()
    store_dir, index_file = _resolve_role_store(skills_dir)
    path = _resolve_required_skill_path(store_dir, index_file, name)
    editor_cmd = editor or os.environ.get("EDITOR") or "vi"
    command = [*shlex.split(editor_cmd), str(path)]
    code = subprocess.call(command)
    if code == 0:
        from nanoworker.roles import register_role_path

        register_role_path(store_dir, index_file, path)
    raise typer.Exit(code=code)


@role_app.command("copy")
def role_copy_command(
    source: str = typer.Argument(help="Existing skill folder name or frontmatter name."),
    target: str = typer.Argument(help="New skill folder/name."),
    skills_dir: Optional[Path] = typer.Option(None, "--skills-dir", help="Override managed role store directory."),
    force: bool = typer.Option(False, "--force", help="Overwrite the target skill if it already exists."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Copy a persistent role skill so Leader can tune the copy instead of the base role."""
    from nanoworker.config import load_local_env_file
    from nanoworker.roles import copy_skill

    load_local_env_file()
    resolved_dir, index_file = _resolve_role_store(skills_dir)
    try:
        skill = copy_skill(resolved_dir, resolved_dir, source, target, force=force)
    except (FileNotFoundError, FileExistsError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    from nanoworker.roles import register_role_path

    register_role_path(resolved_dir, index_file, skill.path)

    payload = _skill_payload(skill)
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"Copied {source} to {skill.path}")
    typer.echo(f"Use: --skill {skill.name}")


@app.command("run")
def run_command(
    name: str = typer.Argument(help="Worker name (must be defined in config)"),
    message: Optional[str] = typer.Argument(None, help="Task message for the worker"),
    workspace: str = typer.Option(..., "--workspace", "-w", help="Working directory for the worker"),
    message_file: Optional[Path] = typer.Option(
        None,
        "--message-file",
        "--task-file",
        help="Read the task message from a file. Useful for Task Packets.",
    ),
    role_file: Optional[Path] = typer.Option(
        None,
        "--role-file",
        help="Append a temporary role card or role skill to the system prompt.",
    ),
    extra_skills: Optional[list[str]] = typer.Option(
        None,
        "--skill",
        help="Append a persistent skill for this assignment. Can be passed multiple times.",
    ),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model from config"),
    use_fallbacks: bool = typer.Option(
        True,
        "--fallback/--no-fallback",
        help="Try configured model fallbacks after an LLM failure with no recorded side effects.",
    ),
    assignment_id: Optional[str] = typer.Option(
        None,
        "--assignment-id",
        help="Optional caller-provided id for tracing this immutable assignment snapshot.",
    ),
    tool_policy: Optional[str] = typer.Option(
        None,
        "--tool-policy",
        help="Override the worker tool policy for this assignment.",
    ),
    max_iterations: Optional[int] = typer.Option(None, "--max-iterations", help="Override max iterations"),
    journal: bool = typer.Option(False, "--journal", help="Write this assignment result to the JSONL journal."),
    no_journal: bool = typer.Option(False, "--no-journal", help="Disable the assignment journal for this run."),
    journal_path: Optional[Path] = typer.Option(None, "--journal-path", help="Override the journal JSONL path."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
) -> None:
    """Run a named worker to execute a task."""
    # Configure logging: stderr only, no stdout pollution
    logger.remove()
    if verbose:
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stderr, level="INFO")

    from nanoworker.config import load_config, load_local_env_file, resolve_model
    from nanoworker.journal import append_journal_entry, resolve_journal_target
    from nanoworker.llm import setup_provider_env
    from nanoworker.prompt import build_system_prompt, skill_exists
    from nanoworker.runner import output_result, run_worker
    from nanoworker.tools import TOOL_POLICIES, get_tools_for_policy, resolve_tool_policy

    if journal and no_journal:
        logger.error("Use only one of --journal or --no-journal.")
        raise typer.Exit(code=1)

    # 1. Load local env and config
    load_local_env_file()
    config = load_config()
    skills_dir = _resolve_skills_dir()

    # 2. Look up worker definition
    worker_def = config.workers.get(name)
    if worker_def is None:
        logger.error(f"Worker '{name}' not found in config. Available: {list(config.workers.keys())}")
        raise typer.Exit(code=1)

    # 3. Resolve parameters (CLI overrides config)
    requested_model = model or worker_def.model
    resolved_model = resolve_model(config, requested_model)
    resolved_max_iter = max_iterations or worker_def.max_iterations
    resolved_workspace = str(Path(workspace).resolve())
    resolved_skills = _merge_skills(worker_def.skills, tuple(extra_skills or ()))
    resolved_tool_policy = resolve_tool_policy(worker_def.role, tool_policy or worker_def.tool_policy)
    if resolved_tool_policy not in TOOL_POLICIES:
        logger.error(f"Unknown tool_policy '{resolved_tool_policy}' for worker '{name}'")
        raise typer.Exit(code=1)

    logger.info(
        f"Worker: {name} | Role: {worker_def.role} | Tool policy: {resolved_tool_policy} | "
        f"Model: {resolved_model.model}"
    )
    if resolved_model.profile:
        logger.info(f"Model profile: {resolved_model.profile}")
    if resolved_skills:
        logger.info(f"Skills: {', '.join(resolved_skills)}")
        for skill_name in resolved_skills:
            if not skill_exists(skills_dir, skill_name):
                logger.warning(f"Skill '{skill_name}' was requested but no matching SKILL.md was found")
    logger.info(f"Workspace: {resolved_workspace}")

    task = _resolve_task_message(message, message_file)
    extra_sections = _resolve_extra_sections(role_file)
    assignment = _build_assignment_snapshot(
        worker=name,
        role=worker_def.role,
        tool_policy=resolved_tool_policy,
        model=resolved_model.model,
        model_profile=resolved_model.profile,
        assignment_id=assignment_id,
        skills=resolved_skills,
        role_file=role_file,
    )

    # 4. Build tools for the assignment policy
    tools = get_tools_for_policy(resolved_tool_policy, resolved_workspace)

    # 5. Build system prompt with skills
    system_prompt = build_system_prompt(
        worker_name=name,
        role=worker_def.role,
        workspace=resolved_workspace,
        skills_dir=skills_dir,
        skill_names=resolved_skills,
        extra_sections=extra_sections,
    )

    logger.debug(f"System prompt ({len(system_prompt)} chars)")

    # 6. Run the agent loop, optionally trying configured fallbacks only before side effects.
    attempts = _model_attempts(config, requested_model=resolved_model, use_fallbacks=use_fallbacks)
    result = None
    for attempt_index, attempt_model in enumerate(attempts):
        if attempt_index:
            logger.warning(f"Trying fallback model: {attempt_model.model}")
        setup_provider_env(config, attempt_model.model)
        attempt_assignment = replace(
            assignment,
            model=attempt_model.model,
            model_profile=attempt_model.profile,
        )
        result = _run_async(
            run_worker(
                model=attempt_model.model,
                system_prompt=system_prompt,
                task=task,
                tools=tools,
                max_iterations=resolved_max_iter,
                assignment=attempt_assignment,
            )
        )
        if not _can_retry_with_fallback(result):
            break
    assert result is not None

    # 7. Persist optional journal entry, then output result
    journal_target = resolve_journal_target(
        config,
        enabled_override=_journal_override(journal, no_journal),
        path_override=journal_path,
    )
    if journal_target.enabled:
        try:
            append_journal_entry(result, journal_target.path)
            logger.info(f"Journal: {journal_target.path}")
        except Exception as e:
            logger.warning(f"Could not write assignment journal: {e}")

    output_result(result)

    raise typer.Exit(code=0 if result.success else 1)


@app.command("init")
def init_command(
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Config path to create. Defaults to ~/.nanoworker/config.json.",
    ),
    provider: str = typer.Option(
        "openai-compatible",
        "--provider",
        help="Template provider: openai-compatible, anthropic-native, or both.",
    ),
    model_id: Optional[str] = typer.Option(
        None,
        "--model-id",
        help="Base model id without the litellm provider prefix. Defaults depend on --provider.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing output file."),
) -> None:
    """Create an env-first sample ~/.nanoworker/config.json."""
    from nanoworker.config import CONFIG_FILE
    from nanoworker.templates import build_init_config

    target = output or CONFIG_FILE
    if target.exists() and not force:
        typer.echo(f"Config already exists: {target}. Use --force or choose --output.", err=True)
        raise typer.Exit(code=1)

    try:
        payload = build_init_config(provider=provider, model_id=model_id)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    _write_json_file(target, payload)
    typer.echo(f"Created {target}")
    if provider == "both":
        typer.echo(
            "Set LLM_API_KEY plus LLM_OPENAI_API_BASE and LLM_ANTHROPIC_API_BASE "
            "when the two formats need different base URLs."
        )
    else:
        typer.echo("Set LLM_API_KEY and LLM_API_BASE before running workers.")


@app.command("migrate-config")
def migrate_config_command(
    input_path: Optional[Path] = typer.Option(
        None,
        "--input",
        "-i",
        help="Config path to migrate. Defaults to ~/.nanoworker/config.json.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Write migrated config to this path instead of stdout.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite the input config in place when --output is omitted, or overwrite --output.",
    ),
    backup: bool = typer.Option(True, "--backup/--no-backup", help="Create a .bak file for in-place migration."),
    json_output: bool = typer.Option(False, "--json", help="Output config plus warnings as one JSON object."),
) -> None:
    """Migrate numbered workers and literal provider secrets to the new config shape."""
    from shutil import copy2

    from nanoworker.config import CONFIG_FILE
    from nanoworker.migrate import migrate_config

    source = input_path or CONFIG_FILE
    if not source.exists():
        typer.echo(f"Config not found: {source}", err=True)
        raise typer.Exit(code=1)

    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except Exception as e:
        typer.echo(f"Could not read JSON config {source}: {e}", err=True)
        raise typer.Exit(code=1) from e

    result = migrate_config(raw)

    if output is not None:
        if output.exists() and not force:
            typer.echo(f"Output already exists: {output}. Use --force to overwrite.", err=True)
            raise typer.Exit(code=1)
        _write_json_file(output, result.config)
        _echo_warnings(result.warnings)
        typer.echo(f"Wrote migrated config to {output}")
        return

    if force:
        if backup:
            backup_path = source.with_suffix(source.suffix + ".bak")
            copy2(source, backup_path)
            typer.echo(f"Backup written to {backup_path}", err=True)
        _write_json_file(source, result.config)
        _echo_warnings(result.warnings)
        typer.echo(f"Migrated config in place: {source}")
        return

    if json_output:
        print(json.dumps({"warnings": list(result.warnings), "config": result.config}, ensure_ascii=False, indent=2))
    else:
        _echo_warnings(result.warnings)
        print(json.dumps(result.config, ensure_ascii=False, indent=2))


@app.command("list")
def list_command(json_output: bool = typer.Option(False, "--json", help="Output JSON.")) -> None:
    """List configured worker templates and model profiles."""
    from nanoworker.config import load_config, resolve_model
    from nanoworker.tools import PRIMARY_TOOL_POLICIES, TOOL_POLICIES, resolve_tool_policy

    config = load_config()
    if json_output:
        payload = {
            "workers": {
                name: {
                    "role": worker.role,
                    "tool_policy": resolve_tool_policy(worker.role, worker.tool_policy),
                    "model": worker.model,
                    "resolved_model": resolve_model(config, worker.model).model,
                    "skills": list(worker.skills),
                    "max_iterations": worker.max_iterations,
                    "tools": [
                        tool.name
                        for tool in TOOL_POLICIES.get(resolve_tool_policy(worker.role, worker.tool_policy), ())
                    ],
                }
                for name, worker in config.workers.items()
            },
            "tool_policies": list(PRIMARY_TOOL_POLICIES),
            "models": {
                name: {
                    "model": profile.model,
                    "strengths": list(profile.strengths),
                    "preferred_roles": list(profile.preferred_roles),
                    "cost_tier": profile.cost_tier,
                    "latency_tier": profile.latency_tier,
                    "context_window": profile.context_window,
                    "fallbacks": list(profile.fallbacks),
                    "notes": profile.notes,
                }
                for name, profile in config.models.items()
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not config.workers:
        typer.echo("No workers configured in ~/.nanoworker/config.json")
    else:
        typer.echo("Workers:")
        for name, worker in config.workers.items():
            resolved = resolve_model(config, worker.model)
            profile = f" ({resolved.profile})" if resolved.profile else ""
            tool_policy = resolve_tool_policy(worker.role, worker.tool_policy)
            typer.echo(
                f"- {name}: role={worker.role}, tool_policy={tool_policy}, model={resolved.model}{profile}, "
                f"skills={','.join(worker.skills) or '-'}, max_iterations={worker.max_iterations}"
            )

    if config.models:
        typer.echo("\nModel profiles:")
        for name, profile in config.models.items():
            strengths = ",".join(profile.strengths) or "-"
            typer.echo(f"- {name}: {profile.model} strengths={strengths}")


@app.command("suggest")
def suggest_command(
    task: Optional[str] = typer.Argument(None, help="Task description to classify."),
    message_file: Optional[Path] = typer.Option(
        None,
        "--message-file",
        "--task-file",
        help="Read the task description or Task Packet from a file.",
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace to include in command hint."),
    candidates: bool = typer.Option(False, "--candidates", help="Include role-card candidate data for Leader."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Suggest a worker/model/tool-policy assignment for Leader."""
    from nanoworker.config import load_config, load_local_env_file
    from nanoworker.journal import read_feedback_entries, resolve_journal_target
    from nanoworker.planner import (
        role_candidate_to_dict,
        suggest_assignment,
        suggest_role_candidates,
        suggestion_to_dict,
    )
    from nanoworker.roles import list_registered_roles

    load_local_env_file()
    config = load_config()
    task_text = _resolve_task_message(task, message_file)
    try:
        suggestion = suggest_assignment(config, task_text, workspace=workspace)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    payload = suggestion_to_dict(suggestion)
    if candidates or json_output:
        feedback_target = resolve_journal_target(config, enabled_override=True)
        feedback_entries = tuple(read_feedback_entries(feedback_target.path, limit=100))
        role_store, role_index = _role_store_paths()
        role_infos = list_registered_roles(role_store, role_index)
        payload["candidates"] = [
            role_candidate_to_dict(candidate, task=task_text, feedback_entries=feedback_entries)
            for candidate in suggest_role_candidates(config, task_text, workspace=workspace, role_infos=role_infos)
        ]
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo(f"Task shape: {payload['task_shape']}")
    typer.echo(f"Worker: {payload['worker']} role={payload['role']}")
    typer.echo(f"Model: {payload['model']} -> {payload['resolved_model']}")
    typer.echo(f"Tool policy: {payload['tool_policy']}")
    typer.echo(f"Role card recommended: {payload['role_card_recommended']}")
    typer.echo(f"Command: {payload['command']}")
    if candidates:
        typer.echo("\nRole candidates:")
        for candidate in payload["candidates"]:
            typer.echo(
                f"- {candidate['name']}: worker={candidate['worker']} role={candidate['base_role']} "
                f"model={candidate['model']} policy={candidate['tool_policy']}"
            )
            summary = candidate.get("feedback_summary") or {}
            if summary:
                tags = ",".join(item["tag"] for item in summary.get("top_tags", ())) or "-"
                typer.echo(
                    f"  feedback summary: count={summary.get('count')} accepted={summary.get('accepted')} "
                    f"rejected={summary.get('rejected')} tags={tags}"
                )
            for feedback in candidate.get("feedback", ()):
                tags = ",".join(feedback.get("fit_tags") or ()) or "-"
                typer.echo(
                    f"  feedback: {feedback.get('target_type')}:{feedback.get('target')} "
                    f"tags={tags} - {feedback.get('leader_comment')}"
                )


@app.command("doctor")
def doctor_command(json_output: bool = typer.Option(False, "--json", help="Output JSON.")) -> None:
    """Check config, env vars, skills, and command availability."""
    from shutil import which

    from nanoworker.config import CONFIG_FILE, load_config, load_local_env_file, resolve_model
    from nanoworker.prompt import skill_exists
    from nanoworker.tools import ROLE_DEFAULT_TOOL_POLICY, TOOL_POLICIES, resolve_tool_policy

    load_local_env_file()
    config = load_config()
    skills_dir = _resolve_skills_dir()
    checks: list[dict[str, object]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("config", CONFIG_FILE.exists(), str(CONFIG_FILE))
    add("nanoworker-bin", which("nanoworker") is not None, which("nanoworker") or "not found")
    add("role-store", skills_dir.exists(), str(skills_dir))

    for provider_name, provider in config.providers.items():
        if provider.api_key_env:
            ok = bool(os.environ.get(provider.api_key_env))
            add(f"env:{provider.api_key_env}", ok, f"provider={provider_name}")
        elif provider.api_key:
            add(f"provider:{provider_name}:api_key", False, "literal key configured; use api_key_env")
        else:
            add(f"provider:{provider_name}:api_key", False, "no api_key_env or api_key")

        if provider.api_base_env:
            ok = bool(os.environ.get(provider.api_base_env))
            add(f"env:{provider.api_base_env}", ok, f"provider={provider_name}")
        elif provider.api_base:
            add(f"provider:{provider_name}:api_base", True, provider.api_base)

    for worker_name, worker in config.workers.items():
        resolved = resolve_model(config, worker.model)
        tool_policy = resolve_tool_policy(worker.role, worker.tool_policy)
        add(f"worker:{worker_name}", True, f"role={worker.role}, tool_policy={tool_policy}, model={resolved.model}")
        configured_policy = worker.tool_policy or ROLE_DEFAULT_TOOL_POLICY.get(worker.role, worker.role)
        add(f"tool-policy:{worker_name}", configured_policy in TOOL_POLICIES, configured_policy)
        for skill_name in worker.skills:
            add(f"skill:{skill_name}", skill_exists(skills_dir, skill_name), f"worker={worker_name}")

    if json_output:
        ok = all(item["ok"] for item in checks)
        print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
        if not ok:
            raise typer.Exit(code=1)
        return

    for item in checks:
        mark = "OK" if item["ok"] else "FAIL"
        typer.echo(f"[{mark}] {item['name']}: {item['detail']}")

    if not all(item["ok"] for item in checks):
        raise typer.Exit(code=1)


@app.command("journal")
def journal_command(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of entries to show."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    path: Optional[Path] = typer.Option(None, "--path", help="Override the journal JSONL path."),
    worker: Optional[str] = typer.Option(None, "--worker", help="Filter by worker template."),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by result status."),
    assignment_id: Optional[str] = typer.Option(None, "--assignment-id", help="Filter by assignment id."),
) -> None:
    """Read recent assignment journal entries."""
    from nanoworker.config import load_config, load_local_env_file
    from nanoworker.journal import read_journal_entries, resolve_journal_target

    load_local_env_file()
    config = load_config()
    target = resolve_journal_target(config, enabled_override=True, path_override=path)
    entries = read_journal_entries(
        target.path,
        limit=limit,
        worker=worker,
        status=status,
        assignment_id=assignment_id,
    )

    if json_output:
        print(json.dumps({"path": str(target.path), "entries": entries}, ensure_ascii=False, indent=2))
        return

    if not entries:
        typer.echo(f"No journal entries found at {target.path}")
        return

    for entry in entries:
        if entry.get("event") == "leader_feedback":
            tags = ",".join(entry.get("fit_tags") or ()) or "-"
            typer.echo(
                f"{entry.get('timestamp', '-')} "
                f"event=leader_feedback "
                f"target={entry.get('target', '-')} "
                f"type={entry.get('target_type', '-')} "
                f"assignment_id={entry.get('assignment_id') or '-'} "
                f"tags={tags}"
            )
            continue
        assignment = entry.get("assignment") or {}
        files_count = len(entry.get("files_changed") or ())
        tests_count = len(entry.get("tests_run") or ())
        typer.echo(
            f"{entry.get('timestamp', '-')} "
            f"status={entry.get('status', '-')} "
            f"worker={assignment.get('worker', '-')} "
            f"model={assignment.get('model', '-')} "
            f"assignment_id={assignment.get('assignment_id') or '-'} "
            f"risk={entry.get('risk_level') or '-'} "
            f"role_fit={entry.get('role_fit') or '-'} "
            f"files={files_count} tests={tests_count}"
        )


@app.command("feedback")
def feedback_command(
    target: str = typer.Argument(help="Target name, or 'list' to read feedback entries."),
    comment: Optional[str] = typer.Option(
        None,
        "--comment",
        "--leader-comment",
        help="Leader-authored evaluation or reuse note.",
    ),
    target_type: Optional[str] = typer.Option(
        None,
        "--target-type",
        help="Feedback target type: role_card, skill, base_role, model, or assignment. Defaults to role_card when recording.",
    ),
    assignment_id: Optional[str] = typer.Option(None, "--assignment-id", help="Related assignment id."),
    tag: Optional[list[str]] = typer.Option(None, "--tag", help="Fit tag such as frontend, database, api. Repeatable."),
    role_fit: Optional[str] = typer.Option(None, "--role-fit", help="Leader's role/card fit judgment."),
    model_fit: Optional[str] = typer.Option(None, "--model-fit", help="Leader's model fit judgment."),
    accepted: Optional[bool] = typer.Option(
        None,
        "--accepted/--rejected",
        help="Whether Leader accepted the assignment outcome.",
    ),
    target_filter: Optional[str] = typer.Option(None, "--target", help="Filter target when TARGET is 'list'."),
    tag_filter: Optional[str] = typer.Option(None, "--filter-tag", "--tag-filter", help="Filter fit tag when TARGET is 'list'."),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum feedback entries to show when TARGET is 'list'."),
    reuse_when: Optional[list[str]] = typer.Option(None, "--reuse-when", help="When to reuse this target. Repeatable."),
    avoid_when: Optional[list[str]] = typer.Option(None, "--avoid-when", help="When to avoid this target. Repeatable."),
    path: Optional[Path] = typer.Option(None, "--journal-path", "--path", help="Override the feedback journal path."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Record or list Leader feedback about Role Cards, skills, models, or assignments."""
    from nanoworker.config import load_config, load_local_env_file
    from nanoworker.journal import append_feedback_entry, read_feedback_entries, resolve_journal_target

    load_local_env_file()
    config = load_config()
    target_journal = resolve_journal_target(config, enabled_override=True, path_override=path)
    if target == "list":
        entries = read_feedback_entries(
            target_journal.path,
            limit=limit,
            target=target_filter,
            target_type=target_type,
            tag=tag_filter,
            assignment_id=assignment_id,
        )
        if json_output:
            print(json.dumps({"path": str(target_journal.path), "entries": entries}, ensure_ascii=False, indent=2))
            return
        if not entries:
            typer.echo(f"No feedback entries found at {target_journal.path}")
            return
        for entry in entries:
            tags = ",".join(entry.get("fit_tags") or ()) or "-"
            accepted_text = (
                "accepted" if entry.get("accepted") is True else "rejected" if entry.get("accepted") is False else "-"
            )
            typer.echo(
                f"{entry.get('timestamp', '-')} "
                f"target={entry.get('target', '-')} "
                f"type={entry.get('target_type', '-')} "
                f"assignment_id={entry.get('assignment_id') or '-'} "
                f"accepted={accepted_text} "
                f"tags={tags} "
                f"comment={entry.get('leader_comment', '')}"
            )
        return

    if comment is None or not comment.strip():
        typer.echo("Provide --comment, or use `nanoworker feedback list` to read feedback.", err=True)
        raise typer.Exit(code=1)

    try:
        entry = append_feedback_entry(
            target_journal.path,
            target=target,
            target_type=target_type or "role_card",
            leader_comment=comment,
            assignment_id=assignment_id,
            fit_tags=tuple(tag or ()),
            role_fit=role_fit,
            model_fit=model_fit,
            accepted=accepted,
            reuse_when=tuple(reuse_when or ()),
            avoid_when=tuple(avoid_when or ()),
        )
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e

    if json_output:
        print(json.dumps({"path": str(target_journal.path), "entry": entry}, ensure_ascii=False, indent=2))
        return

    typer.echo(f"Recorded feedback for {entry['target_type']}:{target} in {target_journal.path}")


@app.command("stats")
def stats_command(
    target: Optional[str] = typer.Option(None, "--target", help="Target name to summarize."),
    target_type: Optional[str] = typer.Option(
        None,
        "--target-type",
        help="Target type: role_card, skill, base_role, model, or assignment.",
    ),
    worker: Optional[str] = typer.Option(None, "--worker", help="Filter assignment worker template."),
    role: Optional[str] = typer.Option(None, "--role", help="Filter assignment base role."),
    model: Optional[str] = typer.Option(None, "--model", help="Filter assignment model/profile."),
    skill: Optional[str] = typer.Option(None, "--skill", help="Filter assignment skill."),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter feedback tag."),
    since: Optional[str] = typer.Option(None, "--since", help="Include entries at or after this ISO-8601 timestamp."),
    until: Optional[str] = typer.Option(None, "--until", help="Include entries at or before this ISO-8601 timestamp."),
    last_days: Optional[int] = typer.Option(None, "--last-days", help="Include entries from the last N days."),
    path: Optional[Path] = typer.Option(None, "--journal-path", "--path", help="Override journal JSONL path."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Aggregate assignment and Leader feedback data for Leader inspection."""
    from nanoworker.config import load_config, load_local_env_file
    from nanoworker.journal import build_journal_stats, resolve_journal_target

    load_local_env_file()
    config = load_config()
    target_journal = resolve_journal_target(config, enabled_override=True, path_override=path)
    if last_days is not None:
        if last_days <= 0:
            typer.echo("--last-days must be greater than 0", err=True)
            raise typer.Exit(code=1)
        if since is not None:
            typer.echo("Use either --since or --last-days, not both.", err=True)
            raise typer.Exit(code=1)
        since = (datetime.now(timezone.utc) - timedelta(days=last_days)).isoformat()
    try:
        payload = build_journal_stats(
            target_journal.path,
            target=target,
            target_type=target_type,
            worker=worker,
            role=role,
            model=model,
            skill=skill,
            tag=tag,
            since=since,
            until=until,
        )
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    assignments = payload["assignments"]
    feedback = payload["feedback"]
    typer.echo(f"Journal: {payload['path']}")
    typer.echo(
        f"Assignments: count={assignments['count']} success={assignments['success']} failed={assignments['failed']}"
    )
    typer.echo(f"Statuses: {_format_counts(assignments['statuses'])}")
    typer.echo(f"Risk: {_format_counts(assignments['risk_level'])}")
    typer.echo(f"Role fit: {_format_counts(assignments['role_fit'])}")
    typer.echo(f"Feedback: count={feedback['count']} accepted={feedback['accepted']} rejected={feedback['rejected']}")
    typer.echo(f"Feedback tags: {_format_counts(feedback['tags'])}")
    if feedback["recent_comments"]:
        typer.echo("Recent comments:")
        for item in feedback["recent_comments"]:
            typer.echo(f"- {item.get('target_type')}:{item.get('target')} - {item.get('leader_comment')}")


@app.command("smoke")
def smoke_command(
    name: str = typer.Argument(help="Worker template to smoke test."),
    workspace: str = typer.Option("/tmp", "--workspace", "-w", help="Workspace for the smoke test."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model/profile for this smoke test."),
    tool: bool = typer.Option(False, "--tool", help="Force a write/read tool-call smoke test."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs."),
) -> None:
    """Run a minimal LLM smoke test through a worker template."""
    message = (
        "Create a file named nanoworker-smoke.txt containing exactly: nanoworker smoke ok\n"
        "Then read it back and report Status: DONE with Files Changed and Tests Run."
        if tool
        else (
            "Do not use tools. Reply exactly with: Status: DONE\n\n"
            "Summary:\n- nanoworker smoke test passed\n\n"
            "Tests Run:\n- none: not needed\n\n"
            "Files Changed:\n- None\n\n"
            "Concerns:\n- None"
        )
    )
    run_command(
        name=name,
        message=message,
        workspace=workspace,
        message_file=None,
        role_file=None,
        extra_skills=None,
        model=model,
        assignment_id="smoke",
        use_fallbacks=True,
        tool_policy=None,
        max_iterations=5 if tool else 2,
        journal=False,
        no_journal=False,
        journal_path=None,
        verbose=verbose,
    )


def _resolve_task_message(message: str | None, message_file: Path | None) -> str:
    if message_file is None and not message:
        logger.error("Provide a task message argument or --message-file/--task-file.")
        raise typer.Exit(code=1)

    return _resolve_optional_text(message, message_file)


def _resolve_optional_text(message: str | None, message_file: Path | None) -> str:
    file_content = ""
    if message_file is not None:
        try:
            file_content = message_file.read_text(encoding="utf-8")
        except Exception as e:
            typer.echo(f"Could not read message file {message_file}: {e}", err=True)
            raise typer.Exit(code=1) from e

    if message and file_content:
        return f"{message.strip()}\n\n--- Task Packet ---\n\n{file_content.strip()}"
    if file_content:
        return file_content
    return message or ""


def _resolve_extra_sections(role_file: Path | None) -> tuple[str, ...]:
    if role_file is None:
        return ()
    try:
        return (role_file.read_text(encoding="utf-8"),)
    except Exception as e:
        logger.error(f"Could not read role file {role_file}: {e}")
        raise typer.Exit(code=1) from e


def _merge_skills(default_skills: tuple[str, ...], extra_skills: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for skill in default_skills + extra_skills:
        normalized = skill.strip()
        if normalized and normalized not in seen:
            merged.append(normalized)
            seen.add(normalized)
    return tuple(merged)


def _build_assignment_snapshot(
    worker: str,
    role: str,
    tool_policy: str,
    model: str,
    model_profile: str | None,
    assignment_id: str | None,
    skills: tuple[str, ...],
    role_file: Path | None,
):
    from nanoworker.protocol import AssignmentSnapshot

    return AssignmentSnapshot(
        worker=worker,
        base_role=role,
        tool_policy=tool_policy,
        model=model,
        assignment_id=assignment_id,
        model_profile=model_profile,
        skills=skills,
        role_file=str(role_file) if role_file is not None else None,
    )


def _model_attempts(config, requested_model, use_fallbacks: bool):
    from nanoworker.config import resolve_model

    attempts = [requested_model]
    if not use_fallbacks:
        return attempts

    seen = {requested_model.model}
    for fallback in requested_model.fallbacks:
        resolved = resolve_model(config, fallback)
        if resolved.model in seen:
            continue
        attempts.append(resolved)
        seen.add(resolved.model)
    return attempts


def _can_retry_with_fallback(result) -> bool:
    return (
        result.status == "failed"
        and result.summary.startswith("LLM call failed:")
        and not result.files_changed
    )


def _journal_override(journal: bool, no_journal: bool) -> bool | None:
    if journal:
        return True
    if no_journal:
        return False
    return None


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "-"
    return ", ".join(f"{key}={value}" for key, value in counts.items())


def _skill_payload(skill) -> dict[str, object]:
    return {
        "name": skill.name,
        "path": str(skill.path),
        "description": skill.description,
        "tags": list(skill.tags),
        "base_role": skill.base_role,
        "preferred_models": list(skill.preferred_models),
        "use": f"--skill {skill.name}",
    }


def _role_store_paths(override: Path | None = None) -> tuple[Path, Path]:
    if override is not None:
        store_dir = override.expanduser().resolve()
        return store_dir, store_dir / "index.json"

    from nanoworker.config import ROLE_INDEX_FILE, ROLE_STORE_DIR

    return ROLE_STORE_DIR.resolve(), ROLE_INDEX_FILE.resolve()


def _resolve_role_store(override: Path | None = None) -> tuple[Path, Path]:
    store_dir, index_file = _role_store_paths(override)
    store_dir.mkdir(parents=True, exist_ok=True)
    return store_dir, index_file


def _resolve_skills_dir(override: Path | None = None) -> Path:
    return _resolve_role_store(override)[0]


def _resolve_required_skill_path(store_dir: Path, index_file: Path, name: str) -> Path:
    from nanoworker.roles import resolve_registered_role_path

    path = resolve_registered_role_path(store_dir, index_file, name)
    if path is None:
        typer.echo(f"Role not found: {name} in managed store {store_dir}", err=True)
        raise typer.Exit(code=1)
    return path


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _role_dispatch_hint(
    *,
    base_role: str,
    role_file: Path | None,
    task_file: Path | None,
    model: str | None,
    skills: tuple[str, ...],
) -> str:
    worker = {
        "coder": "write",
        "debug": "debug",
        "fixer": "fix",
        "reviewer": "review",
        "tester": "verify",
        "debug-duel": "review",
    }.get(base_role, "write")
    parts = [
        "nanoworker",
        worker,
        "--workspace",
        "<workspace>",
        "--message-file",
        str(task_file) if task_file is not None else "<task-packet.md>",
        "--role-file",
        str(role_file) if role_file is not None else "<role-card.md>",
    ]
    if model:
        parts.extend(["--model", model])
    for skill in skills:
        parts.extend(["--skill", skill])
    return " ".join(shlex.quote(part) for part in parts)


def _write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text_file(path: Path, content: str, *, force: bool = False) -> None:
    if path.exists() and not force:
        typer.echo(f"Output already exists: {path}. Use --force to overwrite.", err=True)
        raise typer.Exit(code=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _echo_warnings(warnings: tuple[str, ...]) -> None:
    for warning in warnings:
        typer.echo(f"Warning: {warning}", err=True)


if __name__ == "__main__":
    app()
