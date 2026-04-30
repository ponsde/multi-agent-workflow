"""Configuration loading for nanoworker."""

from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".nanoworker"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOCAL_ENV_FILE = CONFIG_DIR / "env"
ROLE_STORE_DIR = CONFIG_DIR / "roles"
ROLE_INDEX_FILE = ROLE_STORE_DIR / "index.json"


@dataclass(frozen=True)
class ProviderConfig:
    api_key: str = ""
    api_key_env: str | None = None
    api_base: str | None = None
    api_base_env: str | None = None


@dataclass(frozen=True)
class ModelProfile:
    model: str
    strengths: tuple[str, ...] = ()
    preferred_roles: tuple[str, ...] = ()
    cost_tier: str | None = None
    latency_tier: str | None = None
    context_window: int | None = None
    fallbacks: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class ResolvedModel:
    requested: str
    model: str
    profile: str | None = None
    strengths: tuple[str, ...] = ()
    preferred_roles: tuple[str, ...] = ()
    cost_tier: str | None = None
    latency_tier: str | None = None
    context_window: int | None = None
    fallbacks: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class WorkerDef:
    role: str = "coder"
    model: str = "openai/gpt-5.4"
    skills: tuple[str, ...] = ()
    tool_policy: str | None = None
    max_iterations: int = 30


@dataclass(frozen=True)
class JournalConfig:
    enabled: bool = False
    path: str | None = None


@dataclass(frozen=True)
class Config:
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    models: dict[str, ModelProfile] = field(default_factory=dict)
    workers: dict[str, WorkerDef] = field(default_factory=dict)
    journal: JournalConfig = field(default_factory=JournalConfig)


def _parse_provider(raw: dict[str, Any]) -> ProviderConfig:
    return ProviderConfig(
        api_key=raw.get("api_key", ""),
        api_key_env=raw.get("api_key_env"),
        api_base=raw.get("api_base"),
        api_base_env=raw.get("api_base_env"),
    )


def _parse_model_profile(name: str, raw: Any) -> ModelProfile:
    if isinstance(raw, str):
        raw = {"model": raw}
    if not isinstance(raw, dict):
        raw = {}
    return ModelProfile(
        model=raw.get("model", name),
        strengths=_as_tuple(raw.get("strengths", ())),
        preferred_roles=_as_tuple(raw.get("preferred_roles", ())),
        cost_tier=raw.get("cost_tier"),
        latency_tier=raw.get("latency_tier"),
        context_window=raw.get("context_window"),
        fallbacks=_as_tuple(raw.get("fallbacks", ())),
        notes=raw.get("notes", ""),
    )


def _parse_worker(raw: dict[str, Any]) -> WorkerDef:
    return WorkerDef(
        role=raw.get("role", "coder"),
        model=raw.get("model", "openai/gpt-5.4"),
        skills=_as_tuple(raw.get("skills", ())),
        tool_policy=raw.get("tool_policy"),
        max_iterations=raw.get("max_iterations", 30),
    )


def _parse_journal(raw: Any) -> JournalConfig:
    if isinstance(raw, bool):
        return JournalConfig(enabled=raw)
    if not isinstance(raw, dict):
        return JournalConfig()
    return JournalConfig(
        enabled=bool(raw.get("enabled", False)),
        path=raw.get("path"),
    )


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    return (str(value),)


def resolve_model(config: Config, requested: str) -> ResolvedModel:
    """Resolve a model profile name or raw model id into a concrete model id."""
    profile = config.models.get(requested)
    if profile is None:
        return ResolvedModel(requested=requested, model=requested)
    return ResolvedModel(
        requested=requested,
        model=profile.model,
        profile=requested,
        strengths=profile.strengths,
        preferred_roles=profile.preferred_roles,
        cost_tier=profile.cost_tier,
        latency_tier=profile.latency_tier,
        context_window=profile.context_window,
        fallbacks=profile.fallbacks,
        notes=profile.notes,
    )


def load_config() -> Config:
    """Load config from ~/.nanoworker/config.json."""
    if not CONFIG_FILE.exists():
        return Config()

    return load_config_file(CONFIG_FILE)


def load_local_env_file(path: Path = LOCAL_ENV_FILE) -> None:
    """Load ~/.nanoworker/env without overriding existing process env values."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        name, raw_value = line.split("=", 1)
        name = name.strip()
        if not name or name in os.environ:
            continue

        try:
            parsed = shlex.split(raw_value, posix=True)
        except ValueError:
            parsed = [raw_value]
        os.environ[name] = parsed[0] if parsed else ""


def load_config_file(path: Path) -> Config:
    """Load config from an explicit JSON file path."""
    raw = json.loads(path.read_text(encoding="utf-8"))

    providers = {
        name: _parse_provider(p)
        for name, p in raw.get("providers", {}).items()
    }

    models = {
        name: _parse_model_profile(name, m)
        for name, m in raw.get("models", {}).items()
    }

    workers = {
        name: _parse_worker(w)
        for name, w in raw.get("workers", {}).items()
    }

    return Config(
        providers=providers,
        models=models,
        workers=workers,
        journal=_parse_journal(raw.get("journal")),
    )
