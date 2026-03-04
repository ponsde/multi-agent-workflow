"""Configuration loading for nanoworker."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".nanoworker"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass(frozen=True)
class ProviderConfig:
    api_key: str = ""
    api_base: str | None = None


@dataclass(frozen=True)
class WorkerDef:
    role: str = "coder"
    model: str = "openai/gpt-5.3-codex"
    skills: tuple[str, ...] = ()
    max_iterations: int = 30


@dataclass(frozen=True)
class Config:
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    workers: dict[str, WorkerDef] = field(default_factory=dict)


def _parse_provider(raw: dict[str, Any]) -> ProviderConfig:
    return ProviderConfig(
        api_key=raw.get("api_key", ""),
        api_base=raw.get("api_base"),
    )


def _parse_worker(raw: dict[str, Any]) -> WorkerDef:
    return WorkerDef(
        role=raw.get("role", "coder"),
        model=raw.get("model", "openai/gpt-5.3-codex"),
        skills=tuple(raw.get("skills", [])),
        max_iterations=raw.get("max_iterations", 30),
    )


def load_config() -> Config:
    """Load config from ~/.nanoworker/config.json."""
    if not CONFIG_FILE.exists():
        return Config()

    raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

    providers = {
        name: _parse_provider(p)
        for name, p in raw.get("providers", {}).items()
    }

    workers = {
        name: _parse_worker(w)
        for name, w in raw.get("workers", {}).items()
    }

    return Config(providers=providers, workers=workers)
