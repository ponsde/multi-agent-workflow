"""Lightweight Role Card and persistent skill scaffolding."""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import unicodedata
from dataclasses import dataclass, field

from nanoworker.planner import infer_task_shape

SkillDirs = Path | Iterable[Path]


@dataclass(frozen=True)
class RoleDefaults:
    base_role: str
    preferred_model: str
    mission: str
    owns: tuple[str, ...]
    avoids: tuple[str, ...]
    methods: tuple[str, ...]
    acceptance: tuple[str, ...]


@dataclass(frozen=True)
class RoleSpec:
    name: str
    task: str = ""
    base_role: str | None = None
    preferred_model: str | None = None
    tags: tuple[str, ...] = ()
    mission: str | None = None
    owns: tuple[str, ...] = ()
    avoids: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedRoleSpec:
    name: str
    task: str
    task_shape: str
    base_role: str
    preferred_model: str
    tags: tuple[str, ...]
    mission: str
    owns: tuple[str, ...]
    avoids: tuple[str, ...]
    methods: tuple[str, ...]
    acceptance: tuple[str, ...]
    skills: tuple[str, ...]


@dataclass(frozen=True)
class SkillInfo:
    name: str
    path: Path
    frontmatter_name: str | None = None
    description: str = ""
    source: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    modified: bool = False
    tags: tuple[str, ...] = ()
    base_role: str = ""
    preferred_models: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoleStoreCheck:
    name: str
    ok: bool
    detail: str


ROLE_DEFAULTS: dict[str, RoleDefaults] = {
    "frontend": RoleDefaults(
        base_role="coder",
        preferred_model="frontend-strong model if available",
        mission="Implement the UI slice with strong attention to existing design conventions and interaction quality.",
        owns=("The UI files, components, styles, and view-state behavior named in the Task Packet.",),
        avoids=("Backend contract changes unless the Task Packet explicitly assigns them.",),
        methods=(
            "Inspect nearby UI patterns before adding new structure or styling.",
            "Cover responsive layout plus loading, empty, and error states when the surface needs them.",
            "Keep controls, text, and fixed-format UI stable across mobile and desktop sizes.",
        ),
        acceptance=(
            "The UI builds and renders without overlapping or clipped controls.",
            "Relevant tests, lint, build, or manual checks from the Task Packet pass.",
        ),
    ),
    "backend": RoleDefaults(
        base_role="coder",
        preferred_model="strong code/reasoning model if available",
        mission="Implement the backend or data slice with correct contracts, errors, and tests.",
        owns=("The service, API, data, or integration files named in the Task Packet.",),
        avoids=("Unrelated product behavior, broad schema rewrites, or frontend polish outside the assigned contract.",),
        methods=(
            "Trace existing contracts and call sites before changing behavior.",
            "Handle normal paths, edge cases, and error paths explicitly.",
            "Keep changes narrow and add focused tests where behavior changes.",
        ),
        acceptance=("Assigned behavior works through the documented interface.", "Relevant tests or build checks pass."),
    ),
    "debug": RoleDefaults(
        base_role="debug",
        preferred_model="strong code/reasoning model if available",
        mission="Diagnose and fix the defect with the smallest coherent code change.",
        owns=("The failing behavior, reproduction path, and directly related files from the Task Packet.",),
        avoids=("Feature expansion or speculative refactors unrelated to the defect.",),
        methods=(
            "Reproduce or explain the failure before editing when practical.",
            "Trace root cause rather than patching only the visible symptom.",
            "Run the narrowest useful verification after the fix.",
        ),
        acceptance=("The reported failure is fixed.", "The chosen verification command or evidence is reported."),
    ),
    "fix": RoleDefaults(
        base_role="fixer",
        preferred_model="strong code model if available",
        mission="Apply a scoped fix from known findings, failing checks, or Leader handoff notes.",
        owns=("The specific finding, failure, and directly affected files named in the Task Packet.",),
        avoids=("New diagnosis branches, feature redesign, or unrelated cleanup.",),
        methods=(
            "Confirm the finding and affected code before editing.",
            "Patch the smallest coherent surface that resolves the finding.",
            "Run the targeted failing check or closest available verification.",
        ),
        acceptance=("The assigned finding is fixed or precisely rejected with evidence.",),
    ),
    "review": RoleDefaults(
        base_role="reviewer",
        preferred_model="strong review/reasoning model if available",
        mission="Independently review the assigned change for bugs, regressions, and missing verification.",
        owns=("The diff, touched files, and contracts named in the Task Packet.",),
        avoids=("Editing files unless Leader explicitly changes the tool policy and asks for fixes.",),
        methods=(
            "Prioritize correctness, security, data loss, concurrency, and test gaps.",
            "Tie every finding to a concrete file, behavior, or missing check.",
            "Do not report stylistic preferences as bugs.",
        ),
        acceptance=("Findings are actionable and severity-ordered.", "False positives are minimized."),
    ),
    "verify": RoleDefaults(
        base_role="tester",
        preferred_model="reliable tool-use and test-reasoning model if available",
        mission="Verify the assigned behavior and report clear pass/fail evidence.",
        owns=("The verification commands, test files, and user-visible behavior named in the Task Packet.",),
        avoids=("Product code fixes unless explicitly assigned and permitted by tool policy.",),
        methods=(
            "Run the requested checks first, then narrow diagnostics if they fail.",
            "Record exact commands and outcomes.",
            "Keep any new files limited to tests or verification artifacts allowed by the Task Packet.",
        ),
        acceptance=("Verification evidence is specific enough for Leader to route the next step.",),
    ),
    "write": RoleDefaults(
        base_role="coder",
        preferred_model="strong code model if available",
        mission="Execute the assigned implementation task directly and keep the change scoped.",
        owns=("The files and behavior explicitly named in the Task Packet.",),
        avoids=("Unrelated cleanup, architecture rewrites, or decisions that belong to Leader.",),
        methods=(
            "Read the relevant local patterns before editing.",
            "Make the smallest complete change that satisfies acceptance.",
            "Run the most relevant available check before reporting done.",
        ),
        acceptance=("The Task Packet acceptance criteria are met or blockers are reported precisely.",),
    ),
}


def resolve_role_spec(spec: RoleSpec) -> ResolvedRoleSpec:
    """Resolve a partial role spec into concrete Role Card fields."""
    name = spec.name.strip() or "Worker Specialist"
    task = spec.task.strip()
    task_shape = infer_task_shape(f"{name}\n{task}")
    defaults = ROLE_DEFAULTS[task_shape]
    return ResolvedRoleSpec(
        name=name,
        task=task,
        task_shape=task_shape,
        base_role=(spec.base_role or defaults.base_role).strip(),
        preferred_model=(spec.preferred_model or defaults.preferred_model).strip(),
        tags=_clean_tuple(spec.tags) or _default_tags(task_shape),
        mission=(spec.mission or defaults.mission).strip(),
        owns=_clean_tuple(spec.owns) or defaults.owns,
        avoids=_clean_tuple(spec.avoids) or defaults.avoids,
        methods=_clean_tuple(spec.methods) or defaults.methods,
        acceptance=_clean_tuple(spec.acceptance) or defaults.acceptance,
        skills=_clean_tuple(spec.skills),
    )


def build_role_card(spec: RoleSpec) -> str:
    """Build a temporary Role Card markdown document."""
    resolved = resolve_role_spec(spec)
    lines = [
        f"# Role Card: {resolved.name}",
        "",
        "Use With:",
        f"- Base role: {resolved.base_role}",
        f"- Preferred model: {resolved.preferred_model}",
    ]
    if resolved.skills:
        lines.append(f"- Extra skills: {', '.join(resolved.skills)}")

    lines.extend(
        [
            "",
            "Mission:",
            f"- {resolved.mission}",
        ]
    )
    if resolved.task:
        lines.append(f"- Task signal: {_squash(resolved.task, limit=280)}")

    lines.extend(
        [
            "",
            "Scope:",
            *_prefixed("Owns", resolved.owns),
            *_prefixed("Avoids", resolved.avoids),
            "",
            "Method:",
            *_bullets(resolved.methods),
            "",
            "Acceptance Focus:",
            *_bullets(resolved.acceptance),
            "",
            "Report:",
            "- Use the base worker status format.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_skill_doc(spec: RoleSpec, *, skill_name: str | None = None, description: str | None = None) -> str:
    """Build a persistent SKILL.md document from a role spec."""
    resolved = resolve_role_spec(spec)
    frontmatter_name = skill_name or slugify_role_name(resolved.name)
    desc = description or f"{resolved.name} behavior for reusable nanoworker assignments."
    workflow = [f"{index}. {item}" for index, item in enumerate(resolved.methods, start=1)]
    frontmatter = [
        "---",
        f"name: {_yaml_scalar(frontmatter_name)}",
        f"description: {_yaml_scalar(desc)}",
        f"base_role: {_yaml_scalar(resolved.base_role)}",
    ]
    if spec.preferred_model:
        frontmatter.append(f"preferred_models: {_yaml_scalar(spec.preferred_model)}")
    if resolved.tags:
        frontmatter.append(f"tags: {_yaml_scalar(', '.join(resolved.tags))}")
    frontmatter.append("---")
    lines = [
        *frontmatter,
        "",
        f"# {resolved.name}",
        "",
        "## Role",
        resolved.mission,
        "",
        "## Use With",
        f"- Base role: {resolved.base_role}",
        f"- Preferred model: {resolved.preferred_model}",
        "",
        "## Workflow",
        *workflow,
        "",
        "## Quality Bar",
        *_bullets(resolved.acceptance),
        "",
        "## Scope Discipline",
        *_prefixed("Owns", resolved.owns),
        *_prefixed("Avoids", resolved.avoids),
        "",
        "## Report",
        "Use the worker status format. Keep task-specific facts in the Task Packet or a temporary Role Card.",
    ]
    return "\n".join(lines) + "\n"


def slugify_role_name(name: str) -> str:
    """Convert a display role name into an ASCII skill directory/name slug."""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    return slug or "role"


def list_skills(skills_dir: Path, *, source: str = "") -> tuple[SkillInfo, ...]:
    """List skills in a skills directory."""
    if not skills_dir.exists():
        return ()
    items: list[SkillInfo] = []
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        metadata = _frontmatter(path)
        items.append(
            SkillInfo(
                name=metadata.get("name") or path.parent.name,
                path=path,
                frontmatter_name=metadata.get("name"),
                description=metadata.get("description", ""),
                source=source,
                metadata=metadata,
                tags=_metadata_values(metadata, "tags"),
                base_role=_metadata_scalar(metadata, "base_role"),
                preferred_models=_metadata_values(metadata, "preferred_models", "preferred_model"),
            )
        )
    return tuple(items)


def ensure_role_store(source_dir: Path, store_dir: Path, index_file: Path, *, force: bool = False) -> tuple[SkillInfo, ...]:
    """Ensure bundled roles are installed into the managed role store and indexed."""
    store_dir.mkdir(parents=True, exist_ok=True)
    installed = install_default_skills(source_dir, store_dir, force=force)
    if force or installed or not index_file.exists():
        return refresh_role_index(store_dir, index_file)
    return list_registered_roles(store_dir, index_file)


def refresh_role_index(store_dir: Path, index_file: Path) -> tuple[SkillInfo, ...]:
    """Explicitly rebuild the managed role index from files in the role store."""
    skills = list_skills(store_dir, source="managed")
    roles: dict[str, dict[str, object]] = {}
    for skill in skills:
        role_id = skill.name
        roles[role_id] = _role_record(store_dir, skill.path, role_id=role_id, source="managed")
    _write_index(index_file, store_dir, roles)
    return tuple(
        SkillInfo(
            name=skill.name,
            path=skill.path,
            frontmatter_name=skill.frontmatter_name,
            description=skill.description,
            source="managed",
            metadata=skill.metadata,
            modified=False,
            tags=skill.tags,
            base_role=skill.base_role,
            preferred_models=skill.preferred_models,
        )
        for skill in skills
    )


def list_registered_roles(store_dir: Path, index_file: Path) -> tuple[SkillInfo, ...]:
    """List managed roles from the registry without scanning for implicit roles."""
    index = _read_index(index_file)
    if not index:
        return ()

    roles = index.get("roles", {})
    if not isinstance(roles, dict):
        return ()

    items: list[SkillInfo] = []
    for role_id, raw in sorted(roles.items()):
        if not isinstance(raw, dict):
            continue
        path = _managed_role_path(store_dir, raw)
        if path is None or not path.exists():
            continue
        metadata = raw.get("frontmatter", {})
        if not isinstance(metadata, dict):
            metadata = _frontmatter(path)
        current_hash = _sha256_file(path)
        indexed_hash = str(raw.get("sha256", ""))
        frontmatter = {str(key): str(value) for key, value in metadata.items()}
        items.append(
            SkillInfo(
                name=str(raw.get("id") or role_id),
                path=path,
                frontmatter_name=str(frontmatter.get("name")) if frontmatter.get("name") else None,
                description=str(frontmatter.get("description", "")),
                source=str(raw.get("source", "managed")),
                metadata=frontmatter,
                modified=bool(indexed_hash and current_hash != indexed_hash),
                tags=_metadata_values(raw, "tags") or _metadata_values(frontmatter, "tags"),
                base_role=_metadata_scalar(raw, "base_role") or _metadata_scalar(frontmatter, "base_role"),
                preferred_models=_metadata_values(raw, "preferred_models")
                or _metadata_values(frontmatter, "preferred_models", "preferred_model"),
            )
        )
    return tuple(items)


def resolve_registered_role_path(store_dir: Path, index_file: Path, name: str) -> Path | None:
    """Resolve a role id/folder/frontmatter name through the managed role registry."""
    for role in list_registered_roles(store_dir, index_file):
        if name in {role.name, role.frontmatter_name, role.path.parent.name}:
            return role.path
    return None


def register_role_path(store_dir: Path, index_file: Path, path: Path) -> None:
    """Register or refresh one managed role file in the registry."""
    upsert_role_path(store_dir, index_file, path)


def upsert_role_path(
    store_dir: Path,
    index_file: Path,
    path: Path,
    *,
    role_id: str | None = None,
    source: str = "user",
    tags: Iterable[str] | None = None,
    base_role: str | None = None,
    preferred_models: Iterable[str] | None = None,
) -> SkillInfo:
    """Register or refresh one role path inside the managed store."""
    resolved = _assert_managed_role_file(store_dir, path)
    metadata = _frontmatter(resolved)
    resolved_id = _resolve_role_id(role_id, resolved, metadata)
    index = _read_index(index_file)
    roles = index.get("roles", {})
    if not isinstance(roles, dict):
        roles = {}
    previous = roles.get(resolved_id, {})
    if not isinstance(previous, dict):
        previous = {}
    record = _role_record(
        store_dir,
        resolved,
        role_id=resolved_id,
        source=source,
        previous=previous,
        tags=tags,
        base_role=base_role,
        preferred_models=preferred_models,
    )
    roles[resolved_id] = record
    _write_index(index_file, store_dir, roles)
    return SkillInfo(
        name=resolved_id,
        path=resolved,
        frontmatter_name=metadata.get("name"),
        description=metadata.get("description", ""),
        source=str(record.get("source", source)),
        metadata=metadata,
        tags=_metadata_values(record, "tags"),
        base_role=_metadata_scalar(record, "base_role"),
        preferred_models=_metadata_values(record, "preferred_models"),
    )


def import_role_file(
    source_path: Path,
    store_dir: Path,
    index_file: Path,
    *,
    role_id: str | None = None,
    force: bool = False,
    tags: Iterable[str] | None = None,
    base_role: str | None = None,
    preferred_models: Iterable[str] | None = None,
) -> SkillInfo:
    """Copy one SKILL.md into the managed store and register it."""
    source = source_path.expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"role file not found: {source_path}")

    metadata = _frontmatter(source)
    resolved_id = slugify_role_name(role_id or metadata.get("name") or source.parent.name)
    target_path = store_dir / resolved_id / "SKILL.md"
    if target_path.exists() and not force:
        raise FileExistsError(f"role already exists: {resolved_id}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if source != target_path.resolve():
        shutil.copy2(source, target_path)
    content = _replace_frontmatter_name(target_path.read_text(encoding="utf-8"), resolved_id)
    target_path.write_text(content, encoding="utf-8")
    return upsert_role_path(
        store_dir,
        index_file,
        target_path,
        role_id=resolved_id,
        source="imported",
        tags=tags,
        base_role=base_role,
        preferred_models=preferred_models,
    )


def import_role_dir(
    source_dir: Path,
    store_dir: Path,
    index_file: Path,
    *,
    force: bool = False,
    tags: Iterable[str] | None = None,
    base_role: str | None = None,
    preferred_models: Iterable[str] | None = None,
) -> tuple[SkillInfo, ...]:
    """Import every */SKILL.md from a directory into the managed store."""
    source = source_dir.expanduser().resolve()
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(f"role directory not found: {source_dir}")

    candidates = tuple(sorted(source.glob("*/SKILL.md")))
    if not candidates and (source / "SKILL.md").exists():
        candidates = (source / "SKILL.md",)
    imported: list[SkillInfo] = []
    for path in candidates:
        imported.append(
            import_role_file(
                path,
                store_dir,
                index_file,
                force=force,
                tags=tags,
                base_role=base_role,
                preferred_models=preferred_models,
            )
        )
    return tuple(imported)


def remove_registered_role(
    store_dir: Path,
    index_file: Path,
    name: str,
    *,
    delete_file: bool = False,
) -> SkillInfo:
    """Remove a registered role from the index and optionally delete its managed file."""
    index = _read_index(index_file)
    roles = index.get("roles", {})
    if not isinstance(roles, dict):
        raise FileNotFoundError(f"role not found: {name}")

    matched_id: str | None = None
    matched_info: SkillInfo | None = None
    for role_id, raw in sorted(roles.items()):
        if not isinstance(raw, dict):
            continue
        metadata = raw.get("frontmatter", {})
        if not isinstance(metadata, dict):
            metadata = {}
        path = _managed_role_path(store_dir, raw)
        names = {
            str(role_id),
            str(raw.get("id") or ""),
            str(metadata.get("name") or ""),
        }
        if path is not None:
            names.add(path.parent.name)
        if name in names:
            matched_id = str(role_id)
            matched_info = SkillInfo(
                name=str(raw.get("id") or role_id),
                path=path or Path(str(raw.get("path") or "")),
                frontmatter_name=str(metadata.get("name")) if metadata.get("name") else None,
                description=str(metadata.get("description", "")),
                source=str(raw.get("source", "")),
                metadata={str(key): str(value) for key, value in metadata.items()},
                tags=_metadata_values(raw, "tags"),
                base_role=_metadata_scalar(raw, "base_role"),
                preferred_models=_metadata_values(raw, "preferred_models"),
            )
            break
    if matched_id is None or matched_info is None:
        raise FileNotFoundError(f"role not found: {name}")

    roles.pop(matched_id, None)
    _write_index(index_file, store_dir, roles)
    if delete_file and matched_info.path.exists() and _is_relative_to(matched_info.path.resolve(), store_dir.resolve()):
        try:
            matched_info.path.unlink()
            matched_info.path.parent.rmdir()
        except OSError:
            pass
    return matched_info


def role_store_checks(store_dir: Path, index_file: Path) -> tuple[RoleStoreCheck, ...]:
    """Return diagnostics for the managed role store."""
    checks: list[RoleStoreCheck] = [
        RoleStoreCheck("role-store", store_dir.exists(), str(store_dir)),
        RoleStoreCheck("role-index", index_file.exists(), str(index_file)),
    ]
    index = _read_index(index_file)
    roles = index.get("roles", {}) if index else {}
    if roles and not isinstance(roles, dict):
        checks.append(RoleStoreCheck("role-index-format", False, "roles must be an object"))
        return tuple(checks)
    if not isinstance(roles, dict):
        roles = {}

    registered_paths: set[Path] = set()
    for role_id, raw in sorted(roles.items()):
        if not isinstance(raw, dict):
            checks.append(RoleStoreCheck(f"role:{role_id}", False, "invalid index record"))
            continue
        path = _managed_role_path(store_dir, raw)
        if path is None:
            checks.append(RoleStoreCheck(f"role:{role_id}", False, "path escapes managed store"))
            continue
        registered_paths.add(path.resolve())
        if not path.exists():
            checks.append(RoleStoreCheck(f"role:{role_id}", False, f"missing file: {path}"))
            continue
        indexed_hash = str(raw.get("sha256", ""))
        current_hash = _sha256_file(path)
        checks.append(
            RoleStoreCheck(
                f"role:{role_id}",
                not indexed_hash or indexed_hash == current_hash,
                "ok" if not indexed_hash or indexed_hash == current_hash else "hash differs; run role register/edit",
            )
        )

    for path in sorted(store_dir.glob("*/SKILL.md")) if store_dir.exists() else ():
        if path.resolve() not in registered_paths:
            checks.append(RoleStoreCheck(f"unregistered:{path.parent.name}", False, str(path)))
    return tuple(checks)


def resolve_skill_path(skills_dir: SkillDirs, name: str) -> Path | None:
    """Resolve a skill by folder name or frontmatter name."""
    for directory in _as_skill_dirs(skills_dir):
        index_file = directory / "index.json"
        if index_file.exists():
            registered = resolve_registered_role_path(directory, index_file, name)
            if registered is not None:
                return registered
        direct = directory / name / "SKILL.md"
        if direct.exists():
            return direct
        for skill in list_skills(directory):
            if skill.name == name or skill.frontmatter_name == name or skill.path.parent.name == name:
                return skill.path
    return None


def copy_skill(source_dirs: SkillDirs, target_dir: Path, source: str, target: str, *, force: bool = False) -> SkillInfo:
    """Copy one skill to a new skill folder, updating the frontmatter name."""
    source_path = resolve_skill_path(source_dirs, source)
    if source_path is None:
        raise FileNotFoundError(f"skill not found: {source}")

    target_name = slugify_role_name(target)
    target_path = target_dir / target_name / "SKILL.md"
    if target_path.exists() and not force:
        raise FileExistsError(f"skill already exists: {target_name}")

    content = source_path.read_text(encoding="utf-8")
    content = _replace_frontmatter_name(content, target_name)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    metadata = _frontmatter(target_path)
    return SkillInfo(
        name=target_name,
        path=target_path,
        frontmatter_name=target_name,
        description=metadata.get("description", ""),
        source="user",
        metadata=metadata,
        tags=_metadata_values(metadata, "tags"),
        base_role=_metadata_scalar(metadata, "base_role"),
        preferred_models=_metadata_values(metadata, "preferred_models", "preferred_model"),
    )


def install_default_skills(source_dir: Path, target_dir: Path, *, force: bool = False) -> tuple[SkillInfo, ...]:
    """Install bundled default skills into the user skills directory."""
    installed: list[SkillInfo] = []
    for source_path in sorted(source_dir.glob("*/SKILL.md")):
        target_path = target_dir / source_path.parent.name / "SKILL.md"
        if target_path.exists() and not force:
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        metadata = _frontmatter(target_path)
        installed.append(
            SkillInfo(
                name=metadata.get("name") or target_path.parent.name,
                path=target_path,
                frontmatter_name=metadata.get("name"),
                description=metadata.get("description", ""),
                source="user",
                metadata=metadata,
                tags=_metadata_values(metadata, "tags"),
                base_role=_metadata_scalar(metadata, "base_role"),
                preferred_models=_metadata_values(metadata, "preferred_models", "preferred_model"),
            )
        )
    return tuple(installed)


def _clean_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(value.strip() for value in values if value and value.strip())


def _default_tags(task_shape: str) -> tuple[str, ...]:
    return () if task_shape == "write" else (task_shape,)


def _frontmatter(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    metadata: dict[str, str] = {}
    for raw_line in content[3:end].splitlines():
        line = raw_line.strip()
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = _clean_frontmatter_value(value)
    return metadata


def _read_index(index_file: Path) -> dict[str, object]:
    if not index_file.exists():
        return {}
    try:
        raw = json.loads(index_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_index(index_file: Path, store_dir: Path, roles: dict[str, object]) -> None:
    index = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "store_dir": str(store_dir),
        "roles": roles,
    }
    index_file.parent.mkdir(parents=True, exist_ok=True)
    index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _role_record(
    store_dir: Path,
    path: Path,
    *,
    role_id: str,
    source: str,
    previous: dict[str, object] | None = None,
    tags: Iterable[str] | None = None,
    base_role: str | None = None,
    preferred_models: Iterable[str] | None = None,
) -> dict[str, object]:
    metadata = _frontmatter(path)
    now = datetime.now(timezone.utc).isoformat()
    rel_parent = path.resolve().parent.relative_to(store_dir.resolve()).as_posix()
    previous = previous or {}
    resolved_tags = (
        _clean_tuple(tuple(str(tag) for tag in tags))
        if tags is not None
        else _metadata_values(metadata, "tags") or _metadata_values(previous, "tags")
    )
    resolved_base_role = (
        (base_role or "").strip()
        or _metadata_scalar(metadata, "base_role")
        or _metadata_scalar(previous, "base_role")
    )
    resolved_preferred_models = (
        _clean_tuple(tuple(str(model) for model in preferred_models))
        if preferred_models is not None
        else _metadata_values(metadata, "preferred_models", "preferred_model")
        or _metadata_values(previous, "preferred_models")
    )
    return {
        "id": role_id,
        "folder": rel_parent,
        "path": str(path),
        "sha256": _sha256_file(path),
        "source": source,
        "created_at": str(previous.get("created_at") or now),
        "updated_at": now,
        "frontmatter": metadata,
        "tags": list(resolved_tags),
        "base_role": resolved_base_role,
        "preferred_models": list(resolved_preferred_models),
    }


def _assert_managed_role_file(store_dir: Path, path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(store_dir.resolve())
    except ValueError as e:
        raise ValueError(f"role path must be inside managed store: {store_dir}") from e
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"role file not found: {path}")
    if resolved.name != "SKILL.md":
        raise ValueError("role file must be named SKILL.md")
    return resolved


def _resolve_role_id(role_id: str | None, path: Path, metadata: dict[str, str]) -> str:
    raw_id = role_id or metadata.get("name") or path.parent.name
    return slugify_role_name(raw_id)


def _managed_role_path(store_dir: Path, raw: dict[str, object]) -> Path | None:
    folder = raw.get("folder")
    path = raw.get("path")
    candidate = store_dir / str(folder) / "SKILL.md" if folder else Path(str(path or ""))
    if path:
        candidate = Path(str(path)).expanduser()
    if not candidate.is_absolute():
        candidate = store_dir / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(store_dir.resolve())
    except ValueError:
        return None
    return resolved


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_frontmatter_value(value: str) -> str:
    return value.strip().strip("\"'")


def _metadata_scalar(metadata: dict[str, object] | dict[str, str], *keys: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        if isinstance(value, list | tuple):
            value = value[0] if value else ""
        text = str(value).strip()
        if text:
            return text
    return ""


def _metadata_values(metadata: dict[str, object] | dict[str, str], *keys: str) -> tuple[str, ...]:
    for key in keys:
        raw = metadata.get(key)
        values = _split_metadata_values(raw)
        if values:
            return values
    return ()


def _split_metadata_values(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        value = raw.strip()
        if not value:
            return ()
        if value.startswith("[") and value.endswith("]"):
            try:
                parsed = json.loads(value)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return _clean_tuple(tuple(str(item) for item in parsed))
        return _clean_tuple(tuple(part for part in re.split(r"[,;]", value)))
    if isinstance(raw, list | tuple):
        return _clean_tuple(tuple(str(item) for item in raw))
    return _clean_tuple((str(raw),))


def _replace_frontmatter_name(content: str, name: str) -> str:
    if not content.startswith("---"):
        return f"---\nname: {name}\ndescription: Copied nanoworker role skill.\n---\n\n{content}"
    end = content.find("---", 3)
    if end == -1:
        return f"---\nname: {name}\ndescription: Copied nanoworker role skill.\n---\n\n{content}"

    frontmatter = content[3:end].splitlines()
    replaced = False
    lines: list[str] = []
    for line in frontmatter:
        if line.strip().startswith("name:"):
            lines.append(f"name: {name}")
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        lines.insert(0, f"name: {name}")
    return "---\n" + "\n".join(lines).strip() + "\n---" + content[end + 3:]


def _as_skill_dirs(skills_dir: SkillDirs) -> tuple[Path, ...]:
    if isinstance(skills_dir, Path):
        return (skills_dir,)
    return tuple(Path(directory) for directory in skills_dir)


def _bullets(values: tuple[str, ...]) -> list[str]:
    return [f"- {value}" for value in values]


def _prefixed(label: str, values: tuple[str, ...]) -> list[str]:
    if len(values) == 1:
        return [f"- {label}: {values[0]}"]
    return [f"- {label}: {value}" for value in values]


def _squash(text: str, *, limit: int) -> str:
    squashed = re.sub(r"\s+", " ", text).strip()
    if len(squashed) <= limit:
        return squashed
    return squashed[: limit - 3].rstrip() + "..."


def _yaml_scalar(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if (
        compact
        and ":" not in compact
        and "#" not in compact
        and compact[0] not in "-{}[]&*!|>@`\"'"
    ):
        return compact
    return json_escape(compact)


def json_escape(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
