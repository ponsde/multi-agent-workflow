"""Config migration helpers for the lightweight worker-template model."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

DEFAULT_API_KEY_ENV = "LLM_API_KEY"
DEFAULT_API_BASE_ENV = "LLM_API_BASE"


@dataclass(frozen=True)
class MigrationResult:
    config: dict[str, Any]
    warnings: tuple[str, ...] = ()


def migrate_config(raw: dict[str, Any]) -> MigrationResult:
    """Migrate older numbered-worker config into template-oriented config."""
    migrated = copy.deepcopy(raw)
    warnings: list[str] = []

    _migrate_providers(migrated, warnings)
    _migrate_workers(migrated, warnings)

    return MigrationResult(config=migrated, warnings=tuple(warnings))


def _migrate_providers(config: dict[str, Any], warnings: list[str]) -> None:
    providers = config.get("providers")
    if not isinstance(providers, dict):
        return

    literal_bases = {
        provider.get("api_base")
        for provider in providers.values()
        if isinstance(provider, dict) and provider.get("api_base")
    }
    split_base_env = len(literal_bases) > 1

    for provider_name, provider in providers.items():
        if not isinstance(provider, dict):
            continue

        if provider.get("api_key_env") == "XIANYU_API_KEY":
            provider["api_key_env"] = DEFAULT_API_KEY_ENV
            warnings.append(f"provider {provider_name}: renamed XIANYU_API_KEY to {DEFAULT_API_KEY_ENV}")
        if provider.get("api_base_env") == "XIANYU_API_BASE":
            provider["api_base_env"] = DEFAULT_API_BASE_ENV
            warnings.append(f"provider {provider_name}: renamed XIANYU_API_BASE to {DEFAULT_API_BASE_ENV}")

        if provider.pop("api_key", None):
            provider.setdefault("api_key_env", DEFAULT_API_KEY_ENV)
            warnings.append(f"provider {provider_name}: removed literal api_key; export it as {provider['api_key_env']}")

        if provider.pop("api_base", None):
            provider.setdefault("api_base_env", _default_base_env(provider_name, split_base_env))
            warnings.append(f"provider {provider_name}: removed literal api_base; export it as {provider['api_base_env']}")


def _migrate_workers(config: dict[str, Any], warnings: list[str]) -> None:
    workers = config.get("workers")
    if not isinstance(workers, dict):
        return

    explicit_templates = {name for name in workers if name in {"write", "debug", "fix", "verify", "review"}}
    migrated_workers: dict[str, Any] = {}
    for old_name, raw_worker in workers.items():
        worker = copy.deepcopy(raw_worker) if isinstance(raw_worker, dict) else {}
        new_name = _target_worker_name(old_name)

        if new_name != old_name and new_name in explicit_templates:
            warnings.append(f"worker {old_name}: skipped because explicit template {new_name} already exists")
            continue

        if "tool_policy" not in worker:
            worker["tool_policy"] = _default_tool_policy(worker.get("role", "coder"))

        _migrate_role_and_skills(worker, old_name, new_name, warnings)

        if new_name in migrated_workers:
            warnings.append(f"worker {old_name}: skipped because it maps to existing template {new_name}")
            continue

        migrated_workers[new_name] = worker
        if new_name != old_name:
            warnings.append(f"worker {old_name}: renamed to template {new_name}")

    config["workers"] = migrated_workers


def _target_worker_name(name: str) -> str:
    if name in {"write", "debug", "fix", "verify", "review"}:
        return name
    if name == "coder" or name.startswith("coder-"):
        return "write"
    if name == "fixer" or name.startswith("fixer-") or name.startswith("fix-"):
        return "fix"
    if name in {"reviewer", "duel"} or name.startswith("reviewer-") or name.startswith("duel-") or name.startswith("debug-duel-"):
        return "review"
    if name.startswith("debug-"):
        return "debug"
    if name in {"test", "tester"} or name.startswith("tester-"):
        return "verify"
    return name


def _default_tool_policy(role: str) -> str:
    return {
        "coder": "product-write",
        "debug": "product-write",
        "fixer": "product-write",
        "reviewer": "read-only-review",
        "debug-duel": "read-only-review",
        "tester": "test-write-only",
    }.get(role, "product-write")


def _migrate_role_and_skills(worker: dict[str, Any], old_name: str, new_name: str, warnings: list[str]) -> None:
    role = worker.get("role")
    if new_name == "review" and role == "debug-duel":
        worker["role"] = "reviewer"
        warnings.append(f"worker {old_name}: migrated role debug-duel to reviewer; debug-duel skill remains available as legacy")
    elif new_name == "fix" and role not in {"fixer", None}:
        worker["role"] = "fixer"
        warnings.append(f"worker {old_name}: migrated role {role} to fixer")

    skills = worker.get("skills")
    if isinstance(skills, list):
        migrated_skills = [_migrate_skill_name(str(skill)) for skill in skills]
        if migrated_skills != skills:
            worker["skills"] = migrated_skills
            warnings.append(f"worker {old_name}: migrated legacy skill names to base role names")


def _migrate_skill_name(skill: str) -> str:
    return {
        "debug-engineer": "debug",
        "testing-engineer": "tester",
        "debug-duel": "reviewer",
    }.get(skill, skill)


def _default_base_env(provider_name: str, split_base_env: bool) -> str:
    if not split_base_env:
        return DEFAULT_API_BASE_ENV
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in provider_name).upper()
    return f"LLM_{safe_name}_API_BASE"
